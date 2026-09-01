"""Tests for the Daly client abstraction."""

from __future__ import annotations

import pytest

from custom_components.daly_bms_usb.client import (
    DalyBmsClient,
    DalyConnectionError,
    DalyProtocolError,
    DalyWriteError,
    SerialException,
)


def test_connect_and_poll_returns_normalised_snapshot(make_client, fake_bms):
    client: DalyBmsClient = make_client()
    client.connect()
    data = client.poll()
    assert data.total_voltage == 13.2
    assert data.current == 1.5
    assert data.soc_percent == 87.5
    assert data.cell_count == 4
    assert data.temp_sensor_count == 2
    assert data.cell_voltages == {1: 3.30, 2: 3.31, 3: 3.30, 4: 3.29}
    assert data.temperatures == {1: 24.0, 2: 25.0}
    assert data.charge_mos is True
    assert data.discharge_mos is True
    assert data.cell_voltage_delta == pytest.approx(0.02, abs=1e-6)
    assert data.power == pytest.approx(13.2 * 1.5, abs=1e-3)


def test_connect_propagates_serial_exception(make_client, fake_bms):
    fake_bms.raise_on_connect = SerialException("port not found")
    client = make_client()
    with pytest.raises(DalyConnectionError):
        client.connect()
    assert not client.is_connected


def test_connect_fails_when_library_returns_false(make_client, fake_bms):
    fake_bms.connect_returns = False
    client = make_client()
    with pytest.raises(DalyProtocolError):
        client.connect()


def test_poll_before_connect_raises(make_client):
    client = make_client()
    with pytest.raises(DalyConnectionError):
        client.poll()


def test_poll_when_status_missing_raises(make_client, fake_bms):
    client = make_client()
    client.connect()
    fake_bms.status_data = False  # library uses False on failure
    with pytest.raises(DalyProtocolError):
        client.poll()


def test_set_charge_mos_write_and_verify(make_client, fake_bms):
    client = make_client()
    client.connect()
    fake_bms.charge_mos = True
    confirmed = client.set_charge_mos(False)
    assert confirmed is False
    assert fake_bms.charge_mos is False


def test_set_discharge_mos_write_and_verify(make_client, fake_bms):
    client = make_client()
    client.connect()
    confirmed = client.set_discharge_mos(False)
    assert confirmed is False


def test_set_charge_mos_rejected_by_bms(make_client, fake_bms):
    client = make_client()
    client.connect()
    fake_bms.set_charge_returns = False
    with pytest.raises(DalyWriteError):
        client.set_charge_mos(False)


def test_set_charge_mos_verify_mismatch(make_client, fake_bms):
    client = make_client()
    client.connect()
    fake_bms.set_charge_actually_flips = False  # accepts but doesn't change
    with pytest.raises(DalyWriteError):
        client.set_charge_mos(False)


def test_disconnect_is_idempotent(make_client, fake_bms):
    client = make_client()
    client.disconnect()  # not connected -> no-op
    client.connect()
    client.disconnect()
    client.disconnect()
    assert not client.is_connected


def test_serial_exception_during_poll_marks_disconnected(make_client, fake_bms):
    client = make_client()
    client.connect()
    fake_bms.raise_on_call = SerialException("device gone")
    with pytest.raises(DalyConnectionError):
        client.poll()
    assert not client.is_connected


def test_power_and_delta_none_when_data_missing(make_client, fake_bms):
    client = make_client()
    client.connect()
    fake_bms.soc_data = {"total_voltage": None, "current": None, "soc_percent": None}
    fake_bms.cell_range_data = {}
    data = client.poll()
    assert data.power is None
    assert data.cell_voltage_delta is None
