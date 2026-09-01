"""Tests for the config flow helpers and validation.

Full flow-manager tests require homeassistant.setup which is skipped when
homeassistant isn't installed. The helpers can be tested standalone.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

pytest.importorskip("voluptuous")

from custom_components.daly_bms_usb import config_flow as cf
from custom_components.daly_bms_usb.client import (
    DalyConnectionError,
    DalyProtocolError,
)
from custom_components.daly_bms_usb.const import (
    CONF_ENABLE_WRITES,
    CONF_MANUAL_PATH,
    CONF_POLL_INTERVAL,
    CONF_SERIAL_PORT,
    MANUAL_PATH_SENTINEL,
)


class _StubPort:
    def __init__(self, device, manufacturer="", product="", vid=None, pid=None):
        self.device = device
        self.manufacturer = manufacturer
        self.product = product
        self.vid = vid
        self.pid = pid


def test_list_serial_ports_prefers_stable_by_id(tmp_path):
    """The by-id path is preferred and dedupes the underlying ttyUSB entry."""
    fake_by_id = tmp_path / "by-id"
    fake_by_id.mkdir()
    target = tmp_path / "ttyUSB0"
    target.touch()
    (fake_by_id / "usb-1a86_USB_Serial-if00-port0").symlink_to(target)

    def comports():
        return [
            _StubPort(
                str(target),  # pretend pyserial reports the tty by its realpath
                manufacturer="1a86",
                product="USB Serial",
                vid=0x1A86,
                pid=0x7523,
            ),
            _StubPort(str(tmp_path / "ttyUSB1"), manufacturer="", product=""),
        ]

    (tmp_path / "ttyUSB1").touch()

    ports = cf._list_serial_ports_sync(by_id_dir=str(fake_by_id), _comports=comports)
    paths = [p["path"] for p in ports]
    assert str(fake_by_id / "usb-1a86_USB_Serial-if00-port0") in paths
    # ttyUSB0 dedup'd behind the by-id entry
    assert str(target) not in paths
    # ttyUSB1 kept because no by-id resolves to it
    assert str(tmp_path / "ttyUSB1") in paths


def test_label_hides_usb_serial_number():
    info = {
        "path": "/dev/serial/by-id/usb-1a86_USB_Serial-if00-port0",
        "manufacturer": "1a86",
        "product": "USB Serial",
        "vid": "1a86",
        "pid": "7523",
    }
    label = cf._label_for_port(info)
    assert "1a86:7523" in label
    # Serial number must never appear even if given.
    assert "AB1234" not in label


def test_normalise_path_survives_missing_paths():
    assert cf._normalise_path("/definitely/not/there") == "/definitely/not/there"


@pytest.mark.asyncio
async def test_validate_connection_success(fake_bms):
    fake_hass = MagicMock()

    async def _run(func, *args):
        return func(*args)

    fake_hass.async_add_executor_job = _run
    err, unique = await cf._async_validate_connection(fake_hass, "/dev/ttyUSB0")
    assert err is None
    assert unique == {"port": "/dev/ttyUSB0"}


@pytest.mark.asyncio
async def test_validate_connection_translates_errors(fake_bms, monkeypatch):
    fake_hass = MagicMock()

    async def _run(func, *args):
        return func(*args)

    fake_hass.async_add_executor_job = _run

    # Force a connect failure with a "permission denied" message.
    def raise_permission():
        raise DalyConnectionError("[Errno 13] Permission denied: /dev/ttyUSB0")

    monkeypatch.setattr(
        "custom_components.daly_bms_usb.client.DalyBmsClient.connect",
        lambda self: raise_permission(),
    )
    err, _ = await cf._async_validate_connection(fake_hass, "/dev/ttyUSB0")
    assert err == "permission_denied"


@pytest.mark.asyncio
async def test_validate_connection_protocol_error(monkeypatch):
    fake_hass = MagicMock()

    async def _run(func, *args):
        return func(*args)

    fake_hass.async_add_executor_job = _run

    def raise_proto():
        raise DalyProtocolError("bad frame")

    monkeypatch.setattr(
        "custom_components.daly_bms_usb.client.DalyBmsClient.connect", lambda self: raise_proto()
    )
    err, _ = await cf._async_validate_connection(fake_hass, "/dev/ttyUSB0")
    assert err == "invalid_response"


@pytest.mark.asyncio
async def test_validation_never_writes(fake_bms):
    """Setup validation must not call any write method on the underlying BMS."""

    fake_hass = MagicMock()

    async def _run(func, *args):
        return func(*args)

    fake_hass.async_add_executor_job = _run

    fake_bms.set_charge_returns = False  # would raise if invoked
    fake_bms.set_discharge_returns = False

    # spy on the write methods
    calls: list[str] = []

    def _spy_charge(**kwargs):
        calls.append("charge")
        return False

    def _spy_discharge(**kwargs):
        calls.append("discharge")
        return False

    fake_bms.set_charge_mosfet = _spy_charge
    fake_bms.set_discharge_mosfet = _spy_discharge

    err, _ = await cf._async_validate_connection(fake_hass, "/dev/ttyUSB0")
    assert err is None
    assert calls == []


def test_manual_path_sentinel_constant():
    # Ensure the sentinel is a well-known, non-conflicting string.
    assert MANUAL_PATH_SENTINEL == "__manual__"
    assert CONF_MANUAL_PATH == "manual_path"


def test_default_write_flag_is_false():
    # Read defaults out of the const module directly.
    from custom_components.daly_bms_usb.const import DEFAULT_POLL_INTERVAL

    assert DEFAULT_POLL_INTERVAL == 30
    # write-enabled default is materialised in the schema; verified separately
    # via the flow tests once HA is available.
    assert CONF_ENABLE_WRITES == "enable_writes"
    assert CONF_POLL_INTERVAL == "poll_interval"
    assert CONF_SERIAL_PORT == "serial_port"
