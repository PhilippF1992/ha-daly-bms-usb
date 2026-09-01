"""Shared entity base for Daly BMS USB."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, MANUFACTURER, MODEL_UART
from .coordinator import DalyBmsCoordinator


class DalyBmsEntity(CoordinatorEntity[DalyBmsCoordinator]):
    """Base entity: sets DeviceInfo and unique id namespace."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: DalyBmsCoordinator,
        *,
        entry_id: str,
        key: str,
    ) -> None:
        super().__init__(coordinator)
        self._entry_id = entry_id
        self._attr_unique_id = f"{entry_id}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry_id)},
            manufacturer=MANUFACTURER,
            model=MODEL_UART,
            name="Daly BMS",
        )
