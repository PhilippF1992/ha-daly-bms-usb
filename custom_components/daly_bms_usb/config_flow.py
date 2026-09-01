"""Config and options flow for the Daly BMS USB integration."""

from __future__ import annotations

import logging
import os
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.selector import (
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
)

from .client import (
    DalyBmsClient,
    DalyConnectionError,
    DalyProtocolError,
    DalyTimeoutError,
    DalyWriteError,
)
from .const import (
    CONF_ENABLE_WRITES,
    CONF_MANUAL_PATH,
    CONF_POLL_INTERVAL,
    CONF_SERIAL_PORT,
    DEFAULT_POLL_INTERVAL,
    DOMAIN,
    MANUAL_PATH_SENTINEL,
    MAX_POLL_INTERVAL,
    MIN_POLL_INTERVAL,
)

_LOGGER = logging.getLogger(__name__)


BY_ID_DIR = "/dev/serial/by-id"


def _list_serial_ports_sync(
    by_id_dir: str = BY_ID_DIR,
    _comports=None,
) -> list[dict[str, str]]:
    """Return a de-duplicated, stable-path-preferred list of serial ports.

    Uses pyserial's list_ports, and adds any /dev/serial/by-id/ entries that
    resolve to a ttyUSB*/ttyACM* device, preferring the by-id path.
    """
    if _comports is None:
        try:
            from serial.tools import list_ports
        except Exception:  # pragma: no cover
            return []
        _comports = list_ports.comports

    ports: list[dict[str, str]] = []
    seen_real: dict[str, dict[str, str]] = {}
    for p in _comports():
        info = {
            "path": p.device,
            "manufacturer": (p.manufacturer or "").strip(),
            "product": (p.product or "").strip(),
            "vid": f"{p.vid:04x}" if p.vid else "",
            "pid": f"{p.pid:04x}" if p.pid else "",
        }
        seen_real[os.path.realpath(p.device)] = info

    by_id_realpaths: set[str] = set()
    if os.path.isdir(by_id_dir):
        for entry in sorted(os.listdir(by_id_dir)):
            full = os.path.join(by_id_dir, entry)
            try:
                real = os.path.realpath(full)
            except OSError:
                continue
            by_id_realpaths.add(real)
            info = dict(seen_real.get(real, {"path": full}))
            info["path"] = full
            ports.append(info)

    for real, info in seen_real.items():
        if real not in by_id_realpaths:
            ports.append(info)

    return ports


def _label_for_port(info: dict[str, str]) -> str:
    parts = [info["path"]]
    if info.get("manufacturer"):
        parts.append(info["manufacturer"])
    if info.get("product"):
        parts.append(info["product"])
    if info.get("vid") and info.get("pid"):
        parts.append(f"{info['vid']}:{info['pid']}")
    return " — ".join(parts)


async def _async_validate_connection(
    hass: HomeAssistant, port: str
) -> tuple[str | None, dict[str, str] | None]:
    """Open the port, do a read-only poll, close it. Returns (error_code, unique_data)."""
    client = DalyBmsClient(port=port)

    def _validate() -> None:
        client.connect()
        try:
            client.poll()
        finally:
            client.disconnect()

    try:
        await hass.async_add_executor_job(_validate)
    except DalyConnectionError as err:
        msg = str(err).lower()
        if "permission" in msg:
            return "permission_denied", None
        if "no such file" in msg or "not found" in msg:
            return "port_not_found", None
        if "busy" in msg or "already in use" in msg or "in use" in msg:
            return "port_in_use", None
        return "cannot_connect", None
    except DalyTimeoutError:
        return "timeout", None
    except DalyProtocolError:
        return "invalid_response", None
    except DalyWriteError:  # pragma: no cover - not reachable, kept for safety
        return "invalid_response", None
    except Exception:  # noqa: BLE001 - keep raw text out of user-facing messages
        _LOGGER.exception("Unexpected error validating Daly BMS connection")
        return "unknown", None
    return None, {"port": port}


def _normalise_path(path: str) -> str:
    """Resolve symlinks (e.g. /dev/serial/by-id/... -> /dev/ttyUSB0) for de-dup."""
    try:
        return os.path.realpath(path)
    except OSError:
        return path


class DalyBmsConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Daly BMS USB."""

    VERSION = 1

    def __init__(self) -> None:
        self._ports: list[dict[str, str]] = []
        self._selected_port: str | None = None

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """First step: pick a port + interval + writes-enabled flag."""
        errors: dict[str, str] = {}

        # Refresh discovered ports every time the form is shown.
        self._ports = await self.hass.async_add_executor_job(_list_serial_ports_sync)

        options = {info["path"]: _label_for_port(info) for info in self._ports}
        options[MANUAL_PATH_SENTINEL] = "Manual path"

        if user_input is not None:
            selected = user_input[CONF_SERIAL_PORT]
            manual_path = (user_input.get(CONF_MANUAL_PATH) or "").strip()

            if selected == MANUAL_PATH_SENTINEL:
                if not manual_path:
                    errors[CONF_MANUAL_PATH] = "manual_path_required"
                    port = None
                else:
                    port = manual_path
            else:
                port = selected

            if port and not errors:
                await self.async_set_unique_id(_normalise_path(port))
                self._abort_if_unique_id_configured()

                error_code, _ = await _async_validate_connection(self.hass, port)
                if error_code:
                    errors["base"] = error_code
                else:
                    return self.async_create_entry(
                        title=f"Daly BMS ({os.path.basename(port)})",
                        data={
                            CONF_SERIAL_PORT: port,
                        },
                        options={
                            CONF_POLL_INTERVAL: int(user_input[CONF_POLL_INTERVAL]),
                            CONF_ENABLE_WRITES: bool(user_input[CONF_ENABLE_WRITES]),
                        },
                    )

        schema = vol.Schema(
            {
                vol.Required(
                    CONF_SERIAL_PORT,
                    default=(user_input or {}).get(
                        CONF_SERIAL_PORT,
                        next(iter(options)) if options else MANUAL_PATH_SENTINEL,
                    ),
                ): vol.In(options),
                vol.Optional(
                    CONF_MANUAL_PATH,
                    default=(user_input or {}).get(CONF_MANUAL_PATH, ""),
                ): str,
                vol.Required(
                    CONF_POLL_INTERVAL,
                    default=(user_input or {}).get(CONF_POLL_INTERVAL, DEFAULT_POLL_INTERVAL),
                ): NumberSelector(
                    NumberSelectorConfig(
                        min=MIN_POLL_INTERVAL,
                        max=MAX_POLL_INTERVAL,
                        step=1,
                        mode=NumberSelectorMode.BOX,
                        unit_of_measurement="s",
                    )
                ),
                vol.Required(
                    CONF_ENABLE_WRITES,
                    default=(user_input or {}).get(CONF_ENABLE_WRITES, False),
                ): bool,
            }
        )

        return self.async_show_form(
            step_id="user",
            data_schema=schema,
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return DalyBmsOptionsFlow()


class DalyBmsOptionsFlow(OptionsFlow):
    """Options: change polling interval and toggle writes.

    The flow framework injects ``self.config_entry`` for us — do not assign it
    in __init__ (property is read-only on current HA versions).
    """

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        current_interval = self.config_entry.options.get(
            CONF_POLL_INTERVAL,
            self.config_entry.data.get(CONF_POLL_INTERVAL, DEFAULT_POLL_INTERVAL),
        )
        current_writes = self.config_entry.options.get(
            CONF_ENABLE_WRITES,
            self.config_entry.data.get(CONF_ENABLE_WRITES, False),
        )

        if user_input is not None:
            interval = int(user_input[CONF_POLL_INTERVAL])
            if interval < MIN_POLL_INTERVAL or interval > MAX_POLL_INTERVAL:
                errors[CONF_POLL_INTERVAL] = "invalid_interval"
            if not errors:
                return self.async_create_entry(
                    title="",
                    data={
                        CONF_POLL_INTERVAL: interval,
                        CONF_ENABLE_WRITES: bool(user_input[CONF_ENABLE_WRITES]),
                    },
                )

        schema = vol.Schema(
            {
                vol.Required(CONF_POLL_INTERVAL, default=current_interval): NumberSelector(
                    NumberSelectorConfig(
                        min=MIN_POLL_INTERVAL,
                        max=MAX_POLL_INTERVAL,
                        step=1,
                        mode=NumberSelectorMode.BOX,
                        unit_of_measurement="s",
                    )
                ),
                vol.Required(CONF_ENABLE_WRITES, default=current_writes): bool,
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema, errors=errors)
