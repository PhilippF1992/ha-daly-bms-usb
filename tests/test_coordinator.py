"""Coordinator / lifecycle tests.

These require the homeassistant test framework. They are skipped if HA is
not importable in the test environment.
"""

from __future__ import annotations

import asyncio

import pytest

pytest.importorskip("homeassistant")

from homeassistant.core import HomeAssistant  # noqa: E402
from homeassistant.helpers.update_coordinator import UpdateFailed  # noqa: E402

from custom_components.daly_bms_usb.client import (  # noqa: E402
    DalyBmsClient,
    DalyConnectionError,
)
from custom_components.daly_bms_usb.coordinator import DalyBmsCoordinator  # noqa: E402


@pytest.fixture()
async def hass_instance():
    hass = HomeAssistant(config_dir="/tmp/daly-tests")
    yield hass
    await hass.async_stop()


@pytest.mark.asyncio
async def test_first_refresh_populates_data(hass_instance, fake_bms):
    client = DalyBmsClient(port="/dev/ttyUSB0")
    coord = DalyBmsCoordinator(
        hass_instance,
        config_entry=None,
        client=client,
        poll_interval_seconds=30,
        entry_title="test",
    )
    await coord.async_refresh()
    assert coord.data is not None
    assert coord.data.cell_count == 4
    assert coord.last_success_at is not None


@pytest.mark.asyncio
async def test_disconnect_makes_update_fail(hass_instance, fake_bms):
    client = DalyBmsClient(port="/dev/ttyUSB0")
    coord = DalyBmsCoordinator(
        hass_instance,
        config_entry=None,
        client=client,
        poll_interval_seconds=30,
        entry_title="test",
    )
    await coord.async_refresh()

    fake_bms.raise_on_call = DalyConnectionError("gone")
    with pytest.raises(UpdateFailed):
        await coord._async_update_data()  # noqa: SLF001


@pytest.mark.asyncio
async def test_reconnect_restores_success(hass_instance, fake_bms):
    client = DalyBmsClient(port="/dev/ttyUSB0")
    coord = DalyBmsCoordinator(
        hass_instance,
        config_entry=None,
        client=client,
        poll_interval_seconds=30,
        entry_title="test",
    )
    await coord.async_refresh()
    fake_bms.raise_on_call = DalyConnectionError("temporary")
    with pytest.raises(UpdateFailed):
        await coord._async_update_data()  # noqa: SLF001
    fake_bms.raise_on_call = None
    data = await coord._async_update_data()  # noqa: SLF001
    assert data.cell_count == 4


@pytest.mark.asyncio
async def test_shutdown_closes_client(hass_instance, fake_bms):
    client = DalyBmsClient(port="/dev/ttyUSB0")
    coord = DalyBmsCoordinator(
        hass_instance,
        config_entry=None,
        client=client,
        poll_interval_seconds=30,
        entry_title="test",
    )
    await coord.async_refresh()
    await coord.async_shutdown_client()
    assert not client.is_connected


@pytest.mark.asyncio
async def test_write_and_poll_are_serialised(hass_instance, fake_bms):
    """A write must not overlap with a poll."""
    client = DalyBmsClient(port="/dev/ttyUSB0")
    coord = DalyBmsCoordinator(
        hass_instance,
        config_entry=None,
        client=client,
        poll_interval_seconds=30,
        entry_title="test",
    )
    await coord.async_refresh()

    order: list[str] = []

    async def poll():
        async with coord.io_lock:
            order.append("poll-start")
            await asyncio.sleep(0.01)
            order.append("poll-end")

    async def write():
        async with coord.io_lock:
            order.append("write-start")
            await asyncio.sleep(0.01)
            order.append("write-end")

    await asyncio.gather(poll(), write())
    # Whichever ran first must complete before the other starts.
    assert order[0].endswith("start")
    assert order[1].endswith("end")
    assert order[0].split("-")[0] == order[1].split("-")[0]
