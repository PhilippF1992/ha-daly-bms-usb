"""Binary sensor platform for Daly BMS USB."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import DalyConfigEntry
from .client import DalyData
from .entity import DalyBmsEntity


@dataclass(frozen=True, kw_only=True)
class DalyBinarySensorDescription(BinarySensorEntityDescription):
    """Binary sensor description with an accessor."""

    value_fn: Callable[[DalyData], bool | None]


DESCRIPTIONS: tuple[DalyBinarySensorDescription, ...] = (
    DalyBinarySensorDescription(
        key="charge_mos_state",
        translation_key="charge_mos_state",
        device_class=BinarySensorDeviceClass.POWER,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: d.charge_mos,
    ),
    DalyBinarySensorDescription(
        key="discharge_mos_state",
        translation_key="discharge_mos_state",
        device_class=BinarySensorDeviceClass.POWER,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: d.discharge_mos,
    ),
    DalyBinarySensorDescription(
        key="charger_running",
        translation_key="charger_running",
        device_class=BinarySensorDeviceClass.RUNNING,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: d.charger_running,
    ),
    DalyBinarySensorDescription(
        key="load_running",
        translation_key="load_running",
        device_class=BinarySensorDeviceClass.RUNNING,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: d.load_running,
    ),
    DalyBinarySensorDescription(
        key="alarm",
        translation_key="alarm",
        device_class=BinarySensorDeviceClass.PROBLEM,
        value_fn=lambda d: bool(d.errors) if d.errors is not None else None,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: DalyConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Daly BMS binary sensors."""
    coordinator = entry.runtime_data.coordinator
    async_add_entities(DalyBinarySensor(coordinator, entry.entry_id, desc) for desc in DESCRIPTIONS)


class DalyBinarySensor(DalyBmsEntity, BinarySensorEntity):
    """Bindable binary sensor."""

    entity_description: DalyBinarySensorDescription

    def __init__(self, coordinator, entry_id: str, description) -> None:
        super().__init__(coordinator, entry_id=entry_id, key=description.key)
        self.entity_description = description

    @property
    def available(self) -> bool:
        if not super().available:
            return False
        try:
            return self.entity_description.value_fn(self.coordinator.data) is not None
        except Exception:  # noqa: BLE001
            return False

    @property
    def is_on(self) -> bool | None:
        return self.entity_description.value_fn(self.coordinator.data)

    @property
    def extra_state_attributes(self) -> dict[str, list[str]] | None:
        if self.entity_description.key == "alarm":
            errors = self.coordinator.data.errors if self.coordinator.data else None
            if errors:
                return {"errors": errors}
        return None
