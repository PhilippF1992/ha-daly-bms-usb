"""Tests for the diagnostics module."""

from __future__ import annotations

import pytest

pytest.importorskip("homeassistant")

from custom_components.daly_bms_usb.diagnostics import _sanitize_path


def test_sanitize_path_hides_serial_number_in_by_id():
    p = "/dev/serial/by-id/usb-1a86_USB_Serial_ABCD1234-if00-port0"
    out = _sanitize_path(p)
    assert out is not None
    assert "ABCD1234" not in out
    assert out.startswith("usb-1a86")


def test_sanitize_path_keeps_tty_basename():
    assert _sanitize_path("/dev/ttyUSB0") == "ttyUSB0"


def test_sanitize_path_none_passthrough():
    assert _sanitize_path(None) is None
    assert _sanitize_path("") == ""
