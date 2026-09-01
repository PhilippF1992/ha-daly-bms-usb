"""Sensor platform for Daly BMS USB."""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
    PERCENTAGE,
    UnitOfElectricCurrent,
    UnitOfElectricPotential,
    UnitOfPower,
    UnitOfTemperature,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import DalyConfigEntry
from .client import DalyData
from .entity import DalyBmsEntity

_LOGGER = logging.getLogger(__name__)

_WARNED_UNEXPECTED_CELL_COUNTS: set[int] = set()


@dataclass(frozen=True, kw_only=True)
class DalySensorDescription(SensorEntityDescription):
    """Sensor description with an accessor."""

    value_fn: Callable[[DalyData], float | int | str | None]


STATIC_SENSORS: tuple[DalySensorDescription, ...] = (
    DalySensorDescription(
        key="total_voltage",
        translation_key="total_voltage",
        device_class=SensorDeviceClass.VOLTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        suggested_display_precision=2,
        value_fn=lambda d: d.total_voltage,
    ),
    DalySensorDescription(
        key="current",
        translation_key="current",
        device_class=SensorDeviceClass.CURRENT,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        suggested_display_precision=2,
        value_fn=lambda d: d.current,
    ),
    DalySensorDescription(
        key="power",
        translation_key="power",
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfPower.WATT,
        suggested_display_precision=1,
        value_fn=lambda d: d.power,
    ),
    DalySensorDescription(
        key="soc",
        translation_key="soc",
        device_class=SensorDeviceClass.BATTERY,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=PERCENTAGE,
        suggested_display_precision=1,
        value_fn=lambda d: d.soc_percent,
    ),
    DalySensorDescription(
        key="remaining_capacity",
        translation_key="remaining_capacity",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement="Ah",
        suggested_display_precision=2,
        value_fn=lambda d: d.remaining_capacity_ah,
    ),
    DalySensorDescription(
        key="cycles",
        translation_key="cycles",
        state_class=SensorStateClass.TOTAL_INCREASING,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: d.cycles,
    ),
    DalySensorDescription(
        key="cell_count",
        translation_key="cell_count",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: d.cell_count,
    ),
    DalySensorDescription(
        key="temp_sensor_count",
        translation_key="temp_sensor_count",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: d.temp_sensor_count,
    ),
    DalySensorDescription(
        key="highest_cell_voltage",
        translation_key="highest_cell_voltage",
        device_class=SensorDeviceClass.VOLTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        suggested_display_precision=3,
        value_fn=lambda d: d.highest_cell_voltage,
    ),
    DalySensorDescription(
        key="lowest_cell_voltage",
        translation_key="lowest_cell_voltage",
        device_class=SensorDeviceClass.VOLTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        suggested_display_precision=3,
        value_fn=lambda d: d.lowest_cell_voltage,
    ),
    DalySensorDescription(
        key="highest_cell_number",
        translation_key="highest_cell_number",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: d.highest_cell_number,
    ),
    DalySensorDescription(
        key="lowest_cell_number",
        translation_key="lowest_cell_number",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: d.lowest_cell_number,
    ),
    DalySensorDescription(
        key="cell_delta",
        translation_key="cell_delta",
        device_class=SensorDeviceClass.VOLTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        suggested_display_precision=3,
        value_fn=lambda d: d.cell_voltage_delta,
    ),
    DalySensorDescription(
        key="mode",
        translation_key="mode",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: d.mode,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: DalyConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Daly BMS sensors."""
    coordinator = entry.runtime_data.coordinator
    data = coordinator.data

    entities: list[SensorEntity] = [
        DalyStaticSensor(coordinator, entry.entry_id, desc) for desc in STATIC_SENSORS
    ]

    cell_count = data.cell_count if data else None
    if cell_count is not None:
        if cell_count != 4 and cell_count not in _WARNED_UNEXPECTED_CELL_COUNTS:
            _LOGGER.warning(
                "Daly BMS reports %s cells; only cell entities for reported cells will be created",
                cell_count,
            )
            _WARNED_UNEXPECTED_CELL_COUNTS.add(cell_count)
        for i in range(1, cell_count + 1):
            entities.append(DalyCellVoltageSensor(coordinator, entry.entry_id, i))

    temp_count = data.temp_sensor_count if data else None
    if temp_count is not None:
        for i in range(1, temp_count + 1):
            entities.append(DalyTemperatureSensor(coordinator, entry.entry_id, i))

    async_add_entities(entities)


class DalyStaticSensor(DalyBmsEntity, SensorEntity):
    """A static sensor mapped through an accessor."""

    entity_description: DalySensorDescription

    def __init__(
        self,
        coordinator,
        entry_id: str,
        description: DalySensorDescription,
    ) -> None:
        super().__init__(coordinator, entry_id=entry_id, key=description.key)
        self.entity_description = description

    @property
    def available(self) -> bool:
        if not super().available:
            return False
        try:
            return self.entity_description.value_fn(self.coordinator.data) is not None
        except Exception:  # noqa: BLE001 - defensive: keep entity available flag safe
            return False

    @property
    def native_value(self):
        return self.entity_description.value_fn(self.coordinator.data)


class DalyCellVoltageSensor(DalyBmsEntity, SensorEntity):
    """Individual cell voltage sensor."""

    _attr_device_class = SensorDeviceClass.VOLTAGE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = UnitOfElectricPotential.VOLT
    _attr_suggested_display_precision = 3

    def __init__(self, coordinator, entry_id: str, cell_index: int) -> None:
        super().__init__(coordinator, entry_id=entry_id, key=f"cell_{cell_index}_voltage")
        self._cell_index = cell_index
        self._attr_translation_key = "cell_voltage"
        self._attr_translation_placeholders = {"cell": str(cell_index)}

    @property
    def available(self) -> bool:
        if not super().available:
            return False
        return self._cell_index in (self.coordinator.data.cell_voltages or {})

    @property
    def native_value(self) -> float | None:
        return self.coordinator.data.cell_voltages.get(self._cell_index)


class DalyTemperatureSensor(DalyBmsEntity, SensorEntity):
    """Individual temperature sensor."""

    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_suggested_display_precision = 1

    def __init__(self, coordinator, entry_id: str, sensor_index: int) -> None:
        super().__init__(coordinator, entry_id=entry_id, key=f"temperature_{sensor_index}")
        self._sensor_index = sensor_index
        self._attr_translation_key = "temperature"
        self._attr_translation_placeholders = {"sensor": str(sensor_index)}

    @property
    def available(self) -> bool:
        if not super().available:
            return False
        return self._sensor_index in (self.coordinator.data.temperatures or {})

    @property
    def native_value(self) -> float | None:
        return self.coordinator.data.temperatures.get(self._sensor_index)
