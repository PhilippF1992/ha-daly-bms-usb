# Daly BMS USB — Home Assistant custom integration

Third-party custom integration for the Daly LiFePO4 battery management system,
connected to Home Assistant via the **Daly-supplied UART-to-USB cable**.

> This is **not** an official Daly integration and **not** an official Home
> Assistant integration.

## Scope

- **Transport:** Daly UART over USB serial only.
- **Not supported:** RS485, CAN, Bluetooth, Modbus, MQTT, ESPHome bridges, and
  add-ons / external daemons. Home Assistant Core opens the port directly.
- **BMS:** Daly LiFePO4 (validated behaviourally against a 4S 12.8 V, 300 A
  BMS, but cell/temperature counts are discovered at runtime).
- **Home Assistant OS:** current stable Core / HAOS. Installs under
  `/config/custom_components/daly_bms_usb/`.

## Hardware warning

> Use the Daly-supplied UART-to-USB cable intended for this BMS. Do not connect
> the BMS UART pins directly to a Raspberry Pi USB port, and do not substitute
> an arbitrary USB-to-TTL adapter unless its connector pinout and voltage
> levels have been verified. Daly connector shapes, voltage levels, and pin
> assignments may differ between product revisions.

Enabling or disabling the charge / discharge MOS outputs can interrupt
charging or disconnect the load. Do not enable write operations unless you
understand the consequences for your system.

## Installation

### HACS

1. Add this repository as a custom repository (Integration) in HACS.
2. Install **Daly BMS USB**.
3. Restart Home Assistant.
4. Go to **Settings → Devices & services → Add integration**, search for
   *Daly BMS USB*.

### Manual

1. Copy `custom_components/daly_bms_usb/` into your `/config/custom_components/`
   directory so you end up with `/config/custom_components/daly_bms_usb/`.
2. Restart Home Assistant.
3. Add via **Settings → Devices & services → Add integration → Daly BMS USB**.

## Connecting the hardware

1. Plug the Daly UART-to-USB cable into the BMS and into the Raspberry Pi.
2. In Home Assistant, check **Settings → System → Hardware → All Hardware**
   for a new `/dev/ttyUSB*` or `/dev/ttyACM*` device.
3. Only one program may access the port. **The ESPHome / Wemos connection
   must be physically disconnected from the BMS before this integration is
   used.** Two masters on one UART is not supported by the BMS.

## Setting up the integration

The setup wizard asks for:

- **USB serial connection** — a dropdown of detected ports. Stable
  `/dev/serial/by-id/...` paths are listed and preferred. `/dev/ttyUSB*` and
  `/dev/ttyACM*` are also listed. Select **Manual path** and type a path if
  your device isn't detected.
- **Polling interval (seconds)** — default **30 s**, minimum 5 s, maximum
  3600 s. The BMS is polled synchronously; too-short intervals will time out.
- **Enable write operations** — a checkbox, **off by default**. When off, the
  integration is strictly read-only and no switches are created.

Selecting **Manual path** requires typing a full device path such as
`/dev/ttyUSB0`. The by-id path is preferred because it survives reboots and
USB port re-numbering.

### Options flow

**Settings → Devices & services → Daly BMS USB → Configure** lets you change
the polling interval and toggle write operations. Changing the write toggle
reloads the entry and adds or removes the switch entities.

To change the serial path, remove and re-add the integration — this is the
recommended pattern for this integration to avoid re-validating with the port
open in the middle of a running entry.

## Entities

All entities belong to a single device per BMS.

**Sensors:**

- Total voltage, current, power (calculated: V × I, positive = charging).
- State of charge (%), remaining capacity (Ah), cycle count.
- Cell count, temperature-sensor count (discovered at runtime).
- Highest / lowest cell voltage, highest / lowest cell number, cell voltage
  delta.
- Per-cell voltage (`Cell 1 voltage`, `Cell 2 voltage`, ...) — created based
  on the reported cell count.
- Per-temperature-sensor reading — created based on the reported sensor count.
- BMS mode.

**Binary sensors:**

- Charge MOS state, discharge MOS state (read-only).
- Charger running, load running.
- Alarm (`problem` device class) with an `errors` attribute listing active
  fault codes.

**Switches (only when write operations are enabled):**

- Charge MOS enable/disable.
- Discharge MOS enable/disable.

Each write is verified by a follow-up MOSFET status read. If the read-back
does not match the requested state, the write raises a Home Assistant error
and the entity state is not optimistically flipped.

## Behaviour when write operations are disabled

- No switch entities are created.
- No custom write services are registered.
- Read-only sensors continue to work normally.

## Troubleshooting

- **No such file / port not found** — check `Settings → System → Hardware →
  All Hardware` for the actual device path, and re-open the setup wizard so
  the port list refreshes.
- **Permission denied** — HA OS should normally have permission; make sure
  no other add-on / integration (ESPHome, older USB-serial integrations) is
  claiming the port.
- **Timeout / no response** — the BMS may be busy, the polling interval may
  be too short, or the ESPHome connection is still active on the UART pins.
- **`/dev/ttyUSB0` disappeared** — CH340/CP210x/FTDI USB-serial adapters
  sometimes re-enumerate on a different index. Prefer the
  `/dev/serial/by-id/...` path.

## Enable debug logging

Add to `configuration.yaml`:

```yaml
logger:
  logs:
    custom_components.daly_bms_usb: debug
```

Reload / restart Home Assistant. Debug logs never include raw serial frames
or the USB adapter's serial number.

## Removing the integration

**Settings → Devices & services → Daly BMS USB → ⋮ → Delete**. This closes
the serial port cleanly and removes all associated entities.

## Confirmed protocol / library limitations

- Library: [`dalybms`](https://pypi.org/project/dalybms/) `0.5.0`, MIT, archived
  upstream. Pinned in `manifest.json`. Bundles a synchronous Daly UART client.
- Verified read frames: SOC (0x90), cell-voltage range (0x91), temperature
  range (0x92), MOSFET status (0x93), status (0x94), per-cell voltage (0x95),
  per-sensor temperature (0x96), errors (0x98).
- Verified write frames: charge MOS (0xDA), discharge MOS (0xD9). Other
  library writes (`set_soc`, 0x21) are intentionally **not** exposed.
- `get_balancing_status` (0x97) is unimplemented upstream and not exposed.
- Sinowealth-based Daly variants use a different protocol and are not
  supported by this integration.
- The library returns `False` on any protocol / CRC failure and does not raise
  a typed exception — the client wrapper normalises these into
  `DalyConnectionError`, `DalyProtocolError`, and `DalyWriteError`.

## Safety notes for write operations

Enabling **charge MOS** or **discharge MOS** from Home Assistant is
equivalent to physically toggling the corresponding relay on the BMS. If
you turn the discharge MOS off while a load is running, the load will
lose power immediately. If you turn the charge MOS off while charging,
charging will stop. The integration will **not** issue any write during
setup, startup, reconnect, reload, shutdown, or diagnostics — writes only
happen from a deliberate user or automation action.
