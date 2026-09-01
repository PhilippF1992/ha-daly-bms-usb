"""Typed client abstraction around the synchronous dalybms library.

All Daly-specific communication lives here. The coordinator and entities
never touch the underlying library directly. All I/O calls are synchronous
and MUST be scheduled on an executor by the caller (the coordinator does).

The client keeps a single serial connection open and serialises every
call — reads and writes — through an internal threading lock, so a poll
cannot overlap with a write and two writes cannot overlap.
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field
from typing import Any

try:  # pragma: no cover - real library is present in HA
    from dalybms import DalyBMS as _DalyBMS
except Exception:  # pragma: no cover - allow tests without the lib installed
    _DalyBMS = None

try:  # pragma: no cover
    from serial import SerialException
except Exception:  # pragma: no cover

    class SerialException(Exception):  # type: ignore[no-redef]
        """Fallback when pyserial is not available in the test env."""


_LOGGER = logging.getLogger(__name__)

# Library-internal address for RS485/USB-UART Daly BMS.
_DALY_UART_ADDRESS = 4
_DEFAULT_RETRIES = 3


class DalyClientError(Exception):
    """Base error for the Daly client abstraction."""


class DalyConnectionError(DalyClientError):
    """The serial port could not be opened or was lost."""


class DalyTimeoutError(DalyClientError):
    """The BMS did not answer in time."""


class DalyProtocolError(DalyClientError):
    """The BMS returned an invalid frame or checksum."""


class DalyWriteError(DalyClientError):
    """A write command was rejected or not confirmed by the BMS."""


@dataclass(slots=True)
class DalyData:
    """Normalised, immutable snapshot of one poll cycle."""

    total_voltage: float | None = None
    current: float | None = None
    soc_percent: float | None = None
    remaining_capacity_ah: float | None = None
    cycles: int | None = None
    cell_count: int | None = None
    temp_sensor_count: int | None = None
    highest_cell_voltage: float | None = None
    lowest_cell_voltage: float | None = None
    highest_cell_number: int | None = None
    lowest_cell_number: int | None = None
    cell_voltages: dict[int, float] = field(default_factory=dict)
    temperatures: dict[int, float] = field(default_factory=dict)
    charge_mos: bool | None = None
    discharge_mos: bool | None = None
    charger_running: bool | None = None
    load_running: bool | None = None
    mode: str | None = None
    errors: list[str] = field(default_factory=list)

    @property
    def cell_voltage_delta(self) -> float | None:
        """Return max-min cell voltage in volts, if available."""
        if self.highest_cell_voltage is None or self.lowest_cell_voltage is None:
            return None
        return round(self.highest_cell_voltage - self.lowest_cell_voltage, 4)

    @property
    def power(self) -> float | None:
        """Return battery power in watts. Positive = charging, negative = discharging."""
        if self.total_voltage is None or self.current is None:
            return None
        return round(self.total_voltage * self.current, 2)


class DalyBmsClient:
    """Synchronous, thread-safe wrapper around dalybms.DalyBMS."""

    def __init__(self, port: str) -> None:
        self._port = port
        self._bms: Any | None = None
        self._lock = threading.Lock()
        # Set once at connect(); the very first successful poll populates cell/temp counts.
        self._connected = False

    # -- lifecycle ----------------------------------------------------------------

    @property
    def port(self) -> str:
        return self._port

    @property
    def is_connected(self) -> bool:
        return self._connected

    def connect(self) -> None:
        """Open the serial port and read the base status frame."""
        if _DalyBMS is None:  # pragma: no cover
            raise DalyConnectionError("dalybms library is not installed")
        with self._lock:
            if self._connected:
                return
            bms = _DalyBMS(request_retries=_DEFAULT_RETRIES, address=_DALY_UART_ADDRESS)
            try:
                # library.connect(port) opens the port AND calls get_status internally.
                ok = bms.connect(self._port)
            except SerialException as err:
                raise DalyConnectionError(f"Cannot open serial port: {err}") from err
            except OSError as err:
                raise DalyConnectionError(f"Serial port error: {err}") from err
            if ok is False:
                # library returns False for invalid response / checksum failure
                self._safe_disconnect(bms)
                raise DalyProtocolError("BMS did not return a valid status frame")
            self._bms = bms
            self._connected = True

    def disconnect(self) -> None:
        """Close the serial port."""
        with self._lock:
            if self._bms is None:
                return
            self._safe_disconnect(self._bms)
            self._bms = None
            self._connected = False

    @staticmethod
    def _safe_disconnect(bms: Any) -> None:
        try:
            bms.disconnect()
        except Exception as err:  # pragma: no cover - best effort
            _LOGGER.debug("Ignored error during Daly disconnect: %s", err)

    # -- read ---------------------------------------------------------------------

    def poll(self) -> DalyData:
        """Perform one full read cycle and return a normalised snapshot."""
        with self._lock:
            if self._bms is None or not self._connected:
                raise DalyConnectionError("Client is not connected")
            data = DalyData()
            bms = self._bms

            # status first (populates library-internal counts used by cell/temp reads)
            status = self._call(bms.get_status)
            if isinstance(status, dict):
                data.cell_count = _int_or_none(status.get("cells"))
                data.temp_sensor_count = _int_or_none(status.get("temperature_sensors"))
                data.cycles = _int_or_none(status.get("cycles"))
                data.charger_running = _bool_or_none(status.get("charger_running"))
                data.load_running = _bool_or_none(status.get("load_running"))
            else:
                # A hard status failure means every downstream read is meaningless.
                raise DalyProtocolError("get_status returned no data")

            soc = self._call(bms.get_soc)
            if isinstance(soc, dict):
                data.total_voltage = _float_or_none(soc.get("total_voltage"))
                data.current = _float_or_none(soc.get("current"))
                data.soc_percent = _float_or_none(soc.get("soc_percent"))

            cell_range = self._call(bms.get_cell_voltage_range)
            if isinstance(cell_range, dict):
                data.highest_cell_voltage = _float_or_none(cell_range.get("highest_voltage"))
                data.lowest_cell_voltage = _float_or_none(cell_range.get("lowest_voltage"))
                data.highest_cell_number = _int_or_none(cell_range.get("highest_cell"))
                data.lowest_cell_number = _int_or_none(cell_range.get("lowest_cell"))

            mos = self._call(bms.get_mosfet_status)
            if isinstance(mos, dict):
                data.charge_mos = _bool_or_none(mos.get("charging_mosfet"))
                data.discharge_mos = _bool_or_none(mos.get("discharging_mosfet"))
                data.remaining_capacity_ah = _float_or_none(mos.get("capacity_ah"))
                data.mode = _str_or_none(mos.get("mode"))

            cells = self._call(bms.get_cell_voltages)
            if isinstance(cells, dict):
                data.cell_voltages = {int(k): float(v) for k, v in cells.items() if _is_number(v)}

            temps = self._call(bms.get_temperatures)
            if isinstance(temps, dict):
                data.temperatures = {int(k): float(v) for k, v in temps.items() if _is_number(v)}

            errors = self._call(bms.get_errors)
            if isinstance(errors, list):
                data.errors = [str(e) for e in errors]

            return data

    def read_mosfet_status(self) -> tuple[bool | None, bool | None]:
        """Read only the MOSFET status frame (used to verify a write)."""
        with self._lock:
            if self._bms is None:
                raise DalyConnectionError("Client is not connected")
            mos = self._call(self._bms.get_mosfet_status)
            if not isinstance(mos, dict):
                raise DalyProtocolError("Could not read MOSFET status")
            return (
                _bool_or_none(mos.get("charging_mosfet")),
                _bool_or_none(mos.get("discharging_mosfet")),
            )

    # -- write --------------------------------------------------------------------

    def set_charge_mos(self, on: bool) -> bool:
        """Enable or disable the charge MOSFET. Returns the confirmed state."""
        return self._set_mos(kind="charge", on=on)

    def set_discharge_mos(self, on: bool) -> bool:
        """Enable or disable the discharge MOSFET. Returns the confirmed state."""
        return self._set_mos(kind="discharge", on=on)

    def _set_mos(self, *, kind: str, on: bool) -> bool:
        with self._lock:
            if self._bms is None:
                raise DalyConnectionError("Client is not connected")
            bms = self._bms
            method = bms.set_charge_mosfet if kind == "charge" else bms.set_discharge_mosfet
            try:
                result = method(on=on)
            except SerialException as err:
                raise DalyConnectionError(f"Serial error during write: {err}") from err
            if result is False:
                raise DalyWriteError(f"BMS rejected {kind} MOSFET command")
            # Verify by reading MOSFET status back.
            mos = self._call(bms.get_mosfet_status)
            if not isinstance(mos, dict):
                raise DalyProtocolError("Could not verify MOSFET status after write")
            key = "charging_mosfet" if kind == "charge" else "discharging_mosfet"
            confirmed = _bool_or_none(mos.get(key))
            if confirmed is None:
                raise DalyProtocolError(f"{kind} MOSFET state missing in verification frame")
            if confirmed != on:
                raise DalyWriteError(f"{kind} MOSFET state did not change to requested value")
            return confirmed

    # -- helpers ------------------------------------------------------------------

    def _call(self, fn: Any) -> Any:
        """Invoke a library read, translating known errors."""
        try:
            return fn()
        except SerialException as err:
            self._connected = False
            raise DalyConnectionError(f"Serial error: {err}") from err
        except OSError as err:
            self._connected = False
            raise DalyConnectionError(f"OS error on serial port: {err}") from err


def _is_number(v: Any) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _float_or_none(v: Any) -> float | None:
    if _is_number(v):
        return float(v)
    return None


def _int_or_none(v: Any) -> int | None:
    if isinstance(v, bool):
        return None
    if isinstance(v, int):
        return v
    if isinstance(v, float):
        return int(v)
    return None


def _bool_or_none(v: Any) -> bool | None:
    if isinstance(v, bool):
        return v
    if v in (0, 1):
        return bool(v)
    return None


def _str_or_none(v: Any) -> str | None:
    if isinstance(v, str) and v:
        return v
    return None
