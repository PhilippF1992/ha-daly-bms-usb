"""Constants for the Daly BMS USB integration."""

from __future__ import annotations

from typing import Final

DOMAIN: Final = "daly_bms_usb"

CONF_SERIAL_PORT: Final = "serial_port"
CONF_MANUAL_PATH: Final = "manual_path"
CONF_POLL_INTERVAL: Final = "poll_interval"
CONF_ENABLE_WRITES: Final = "enable_writes"

MANUAL_PATH_SENTINEL: Final = "__manual__"

DEFAULT_POLL_INTERVAL: Final = 30
MIN_POLL_INTERVAL: Final = 5
MAX_POLL_INTERVAL: Final = 3600

# Daly UART serial framing is 9600 8N1 with 0.5 s timeout;
# request retries handled inside the library.
SERIAL_BAUDRATE: Final = 9600

# Bounded retries at the coordinator level - the library already
# retries internally, so we only need a small outer envelope.
COORDINATOR_MAX_BACKOFF: Final = 300
COORDINATOR_MIN_BACKOFF: Final = 10

MANUFACTURER: Final = "Daly Electronics"
MODEL_UART: Final = "LiFePO4 BMS (UART/USB)"
