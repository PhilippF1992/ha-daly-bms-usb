"""Diagnostics support for Daly BMS USB."""

from __future__ import annotations

import os
from typing import Any

from homeassistant.core import HomeAssistant

from . import DalyConfigEntry
from .const import (
    CONF_ENABLE_WRITES,
    CONF_POLL_INTERVAL,
    CONF_SERIAL_PORT,
    DEFAULT_POLL_INTERVAL,
)

REDACT = {"serial_number", "serial", "usb_serial"}


def _sanitize_path(path: str | None) -> str | None:
    """Return only the basename of the device path — no directories, no serials."""
    if not path:
        return path
    base = os.path.basename(path)
    # by-id names often embed the USB serial number; only keep the leading
    # descriptive part.
    if "_" in base and base.startswith("usb-"):
        return base.split("_")[0] + "_…"
    return base


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: DalyConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    runtime = entry.runtime_data
    coordinator = runtime.coordinator
    data = coordinator.data

    from importlib.metadata import PackageNotFoundError, version

    try:
        lib_version: str | None = version("dalybms")
    except PackageNotFoundError:  # pragma: no cover
        lib_version = None

    coord_data: dict[str, Any] = {}
    if data is not None:
        coord_data = {
            "total_voltage": data.total_voltage,
            "current": data.current,
            "power": data.power,
            "soc_percent": data.soc_percent,
            "remaining_capacity_ah": data.remaining_capacity_ah,
            "cycles": data.cycles,
            "cell_count": data.cell_count,
            "temperature_sensor_count": data.temp_sensor_count,
            "highest_cell_voltage": data.highest_cell_voltage,
            "lowest_cell_voltage": data.lowest_cell_voltage,
            "cell_voltage_delta": data.cell_voltage_delta,
            "cell_voltages": data.cell_voltages,
            "temperatures": data.temperatures,
            "charge_mos": data.charge_mos,
            "discharge_mos": data.discharge_mos,
            "charger_running": data.charger_running,
            "load_running": data.load_running,
            "mode": data.mode,
            "error_count": len(data.errors),
        }

    return {
        "integration_version": "0.1.0",
        "library": {"name": "dalybms", "version": lib_version},
        "config": {
            CONF_SERIAL_PORT: _sanitize_path(entry.data.get(CONF_SERIAL_PORT)),
            CONF_POLL_INTERVAL: entry.options.get(
                CONF_POLL_INTERVAL,
                entry.data.get(CONF_POLL_INTERVAL, DEFAULT_POLL_INTERVAL),
            ),
            CONF_ENABLE_WRITES: bool(
                entry.options.get(
                    CONF_ENABLE_WRITES,
                    entry.data.get(CONF_ENABLE_WRITES, False),
                )
            ),
        },
        "runtime": {
            "last_success_at": (
                coordinator.last_success_at.isoformat() if coordinator.last_success_at else None
            ),
            "last_update_success": coordinator.last_update_success,
            "update_interval_seconds": (
                coordinator.update_interval.total_seconds() if coordinator.update_interval else None
            ),
        },
        "data": coord_data,
    }
