"""Shared pytest fixtures for the Daly BMS USB integration.

These tests exercise our own client/coordinator/config-flow logic in
isolation, mocking the underlying `dalybms` library. They do not require
the Home Assistant test framework so they can run against a plain Python
install (and inside the HA-dev container that ships with `homeassistant`).
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest

# Ensure the repository root is on sys.path so `custom_components.daly_bms_usb`
# imports resolve when running pytest from the repo root.
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


class FakeDalyBMS:
    """Behavioural mock of dalybms.DalyBMS.

    Reproduces the concrete return-value shapes we depend on.
    """

    def __init__(
        self,
        *,
        request_retries: int = 3,
        address: int = 4,
        logger: Any | None = None,
    ) -> None:
        self.request_retries = request_retries
        self.address = address
        self._logger = logger
        self.port: str | None = None
        self.connected = False
        # Failure switches
        self.connect_returns: bool = True
        self.raise_on_connect: Exception | None = None
        self.raise_on_call: Exception | None = None
        # Mutable state
        self.charge_mos: bool = True
        self.discharge_mos: bool = True
        self.set_charge_returns: bool = True
        self.set_discharge_returns: bool = True
        self.set_charge_actually_flips: bool = True
        self.set_discharge_actually_flips: bool = True
        # Data payloads
        self.status_data: dict[str, Any] | None = {
            "cells": 4,
            "temperature_sensors": 2,
            "charger_running": True,
            "load_running": True,
            "cycles": 12,
            "states": {},
        }
        self.soc_data: dict[str, Any] | None = {
            "total_voltage": 13.2,
            "current": 1.5,
            "soc_percent": 87.5,
        }
        self.cell_range_data: dict[str, Any] | None = {
            "highest_voltage": 3.31,
            "lowest_voltage": 3.29,
            "highest_cell": 2,
            "lowest_cell": 4,
        }
        self.mos_data: dict[str, Any] | None = {
            "mode": "charge",
            "charging_mosfet": True,
            "discharging_mosfet": True,
            "capacity_ah": 90.5,
        }
        self.cell_voltages_data: dict[int, float] = {1: 3.30, 2: 3.31, 3: 3.30, 4: 3.29}
        self.temperatures_data: dict[int, float] = {1: 24.0, 2: 25.0}
        self.errors_data: list[str] = []

    # -- lifecycle ------------------------------------------------------------
    def connect(self, port: str) -> bool:
        if self.raise_on_connect:
            raise self.raise_on_connect
        self.port = port
        self.connected = True
        return self.connect_returns

    def disconnect(self) -> None:
        self.connected = False

    def _maybe_raise(self) -> None:
        if self.raise_on_call:
            raise self.raise_on_call

    # -- reads ---------------------------------------------------------------
    def get_status(self):
        self._maybe_raise()
        return self.status_data

    def get_soc(self):
        self._maybe_raise()
        return self.soc_data

    def get_cell_voltage_range(self):
        self._maybe_raise()
        return self.cell_range_data

    def get_temperature_range(self):
        self._maybe_raise()
        return {
            "highest_temperature": 26,
            "lowest_temperature": 24,
            "highest_sensor": 1,
            "lowest_sensor": 2,
        }

    def get_mosfet_status(self):
        self._maybe_raise()
        if self.mos_data is None:
            return None
        return {
            **self.mos_data,
            "charging_mosfet": self.charge_mos,
            "discharging_mosfet": self.discharge_mos,
        }

    def get_cell_voltages(self):
        self._maybe_raise()
        return dict(self.cell_voltages_data)

    def get_temperatures(self):
        self._maybe_raise()
        return dict(self.temperatures_data)

    def get_errors(self):
        self._maybe_raise()
        return list(self.errors_data)

    # -- writes --------------------------------------------------------------
    def set_charge_mosfet(self, on: bool = True) -> bool:
        if not self.set_charge_returns:
            return False
        if self.set_charge_actually_flips:
            self.charge_mos = bool(on)
        return True

    def set_discharge_mosfet(self, on: bool = True) -> bool:
        if not self.set_discharge_returns:
            return False
        if self.set_discharge_actually_flips:
            self.discharge_mos = bool(on)
        return True


@pytest.fixture()
def fake_bms():
    return FakeDalyBMS()


@pytest.fixture(autouse=True)
def _patch_dalybms(monkeypatch, fake_bms):
    """Swap dalybms.DalyBMS for our fake across the whole client module."""
    import custom_components.daly_bms_usb.client as client_mod

    holder: dict[str, Any] = {"instance": fake_bms}

    def _factory(*args, **kwargs):
        # Ignore constructor args, always return the shared fake.
        return holder["instance"]

    monkeypatch.setattr(client_mod, "_DalyBMS", _factory)
    return holder


@pytest.fixture()
def make_client():
    from custom_components.daly_bms_usb.client import DalyBmsClient

    def _make(port: str = "/dev/ttyUSB0") -> DalyBmsClient:
        return DalyBmsClient(port=port)

    return _make
