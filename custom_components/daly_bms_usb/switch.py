"""Switch platform for Daly BMS USB (charge / discharge MOSFET control).

Every switch re-checks the runtime write-enabled flag *immediately before*
sending. Even if the entity is somehow still resident after writes were
disabled, its async_turn_on/off will raise before touching the port.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from homeassistant.components.switch import SwitchEntity, SwitchEntityDescription
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import DalyConfigEntry
from .client import DalyClientError, DalyWriteError
from .entity import DalyBmsEntity

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, kw_only=True)
class DalySwitchDescription(SwitchEntityDescription):
    kind: str  # "charge" | "discharge"


DESCRIPTIONS: tuple[DalySwitchDescription, ...] = (
    DalySwitchDescription(
        key="charge_mos",
        translation_key="charge_mos_switch",
        kind="charge",
    ),
    DalySwitchDescription(
        key="discharge_mos",
        translation_key="discharge_mos_switch",
        kind="discharge",
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: DalyConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Daly BMS switches.

    Only reachable when writes are enabled; guarded again per-entity anyway.
    """
    if not entry.runtime_data.write_enabled:
        return
    coordinator = entry.runtime_data.coordinator
    async_add_entities(DalyMosSwitch(entry, coordinator, desc) for desc in DESCRIPTIONS)


class DalyMosSwitch(DalyBmsEntity, SwitchEntity):
    """MOSFET switch. On failure, revert or mark unavailable, never claim success."""

    entity_description: DalySwitchDescription

    def __init__(
        self,
        entry: DalyConfigEntry,
        coordinator,
        description: DalySwitchDescription,
    ) -> None:
        super().__init__(coordinator, entry_id=entry.entry_id, key=description.key)
        self.entity_description = description
        self._entry = entry

    @property
    def available(self) -> bool:
        if not super().available:
            return False
        return self._current_state() is not None

    @property
    def is_on(self) -> bool | None:
        return self._current_state()

    def _current_state(self) -> bool | None:
        data = self.coordinator.data
        if data is None:
            return None
        return data.charge_mos if self.entity_description.kind == "charge" else data.discharge_mos

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self._async_set(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._async_set(False)

    async def _async_set(self, on: bool) -> None:
        # Runtime re-check: writes could have been turned off since setup.
        if not self._entry.runtime_data.write_enabled:
            raise HomeAssistantError("Write operations are disabled for this Daly BMS integration")

        coordinator = self.coordinator
        kind = self.entity_description.kind

        async with coordinator.io_lock:
            client = coordinator.client
            try:
                confirmed = await self.hass.async_add_executor_job(
                    client.set_charge_mos if kind == "charge" else client.set_discharge_mos,
                    on,
                )
            except DalyWriteError as err:
                _LOGGER.error("Daly %s MOS write failed: %s", kind, err)
                raise HomeAssistantError(f"Daly BMS rejected the {kind} MOSFET command") from err
            except DalyClientError as err:
                _LOGGER.error("Daly %s MOS write error: %s", kind, err)
                raise HomeAssistantError(
                    f"Communication error while writing {kind} MOSFET"
                ) from err

            if confirmed != on:
                # Should not happen — client already verifies — but be defensive.
                raise HomeAssistantError(
                    f"Daly BMS reported unexpected {kind} MOSFET state after write"
                )

        # Kick off a refresh so all entities pick up the new state promptly.
        await coordinator.async_request_refresh()
