"""Runtime write-permission tests for the switch platform.

Exercises the guard that prevents an existing switch object from writing
after ``enable_writes`` is toggled off.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

pytest.importorskip("homeassistant")

from homeassistant.exceptions import HomeAssistantError  # noqa: E402

from custom_components.daly_bms_usb.switch import (  # noqa: E402
    DESCRIPTIONS,
    DalyMosSwitch,
)


def _make_switch(*, write_enabled: bool):
    entry = SimpleNamespace(
        entry_id="entry-1",
        runtime_data=SimpleNamespace(coordinator=None, write_enabled=write_enabled),
    )
    coord = MagicMock()
    coord.data = SimpleNamespace(charge_mos=True, discharge_mos=True)
    coord.io_lock = MagicMock()
    coord.io_lock.__aenter__ = AsyncMock(return_value=None)
    coord.io_lock.__aexit__ = AsyncMock(return_value=None)
    coord.client.set_charge_mos = MagicMock(return_value=False)
    coord.client.set_discharge_mos = MagicMock(return_value=False)
    coord.async_request_refresh = AsyncMock()
    entry.runtime_data.coordinator = coord
    switch = DalyMosSwitch(entry, coord, DESCRIPTIONS[0])
    switch.hass = MagicMock()
    switch.hass.async_add_executor_job = AsyncMock(return_value=False)
    return entry, coord, switch


@pytest.mark.asyncio
async def test_write_blocked_when_disabled_at_runtime():
    entry, coord, switch = _make_switch(write_enabled=True)
    # Simulate the user disabling writes AFTER the entity was created.
    entry.runtime_data.write_enabled = False
    with pytest.raises(HomeAssistantError):
        await switch.async_turn_off()
    coord.client.set_charge_mos.assert_not_called()


@pytest.mark.asyncio
async def test_write_uses_executor_and_refreshes():
    entry, coord, switch = _make_switch(write_enabled=True)
    switch.hass.async_add_executor_job = AsyncMock(return_value=False)  # confirmed = False
    await switch.async_turn_off()
    switch.hass.async_add_executor_job.assert_awaited_once()
    coord.async_request_refresh.assert_awaited_once()


@pytest.mark.asyncio
async def test_write_raises_on_verify_mismatch():
    entry, coord, switch = _make_switch(write_enabled=True)
    # Requested True, confirmed False → HomeAssistantError.
    switch.hass.async_add_executor_job = AsyncMock(return_value=False)
    with pytest.raises(HomeAssistantError):
        await switch.async_turn_on()
