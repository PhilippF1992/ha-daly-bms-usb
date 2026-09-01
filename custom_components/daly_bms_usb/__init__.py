"""The Daly BMS USB integration."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .client import DalyBmsClient
from .const import (
    CONF_ENABLE_WRITES,
    CONF_POLL_INTERVAL,
    CONF_SERIAL_PORT,
    DEFAULT_POLL_INTERVAL,
)
from .coordinator import DalyBmsCoordinator

_LOGGER = logging.getLogger(__name__)

READ_PLATFORMS: list[Platform] = [Platform.SENSOR, Platform.BINARY_SENSOR]
WRITE_PLATFORMS: list[Platform] = [Platform.SWITCH]


@dataclass
class DalyRuntimeData:
    """Runtime data attached to the config entry."""

    coordinator: DalyBmsCoordinator
    write_enabled: bool


type DalyConfigEntry = ConfigEntry[DalyRuntimeData]


async def async_setup_entry(hass: HomeAssistant, entry: DalyConfigEntry) -> bool:
    """Set up a Daly BMS USB config entry."""
    port: str = entry.data[CONF_SERIAL_PORT]
    poll_interval: int = entry.options.get(
        CONF_POLL_INTERVAL,
        entry.data.get(CONF_POLL_INTERVAL, DEFAULT_POLL_INTERVAL),
    )
    write_enabled: bool = bool(
        entry.options.get(
            CONF_ENABLE_WRITES,
            entry.data.get(CONF_ENABLE_WRITES, False),
        )
    )

    client = DalyBmsClient(port=port)
    coordinator = DalyBmsCoordinator(
        hass,
        config_entry=entry,
        client=client,
        poll_interval_seconds=poll_interval,
        entry_title=entry.title,
    )

    await coordinator.async_config_entry_first_refresh()

    entry.runtime_data = DalyRuntimeData(coordinator=coordinator, write_enabled=write_enabled)

    platforms = list(READ_PLATFORMS)
    if write_enabled:
        platforms.extend(WRITE_PLATFORMS)
    await hass.config_entries.async_forward_entry_setups(entry, platforms)

    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: DalyConfigEntry) -> bool:
    """Unload a Daly BMS USB config entry."""
    runtime = entry.runtime_data
    platforms = list(READ_PLATFORMS)
    if runtime.write_enabled:
        platforms.extend(WRITE_PLATFORMS)
    unload_ok = await hass.config_entries.async_unload_platforms(entry, platforms)
    if unload_ok:
        await runtime.coordinator.async_shutdown_client()
    return unload_ok


async def _async_update_listener(hass: HomeAssistant, entry: DalyConfigEntry) -> None:
    """Reload the config entry when options change."""
    await hass.config_entries.async_reload(entry.entry_id)
