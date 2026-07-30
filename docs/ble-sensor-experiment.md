# BLE sensor experiment

FruitSpy must run this probe on the macOS host. Apple containers do not expose the
host's CoreBluetooth interface.

The probe observes BLE advertisements only. It does not connect, pair, or write to
nearby devices.

From the repository root:

```bash
backend/.venv/bin/python backend/scripts/ble_sensor_probe.py \
  --duration 60 \
  --output runtime/ble-advertisements.jsonl
```

The first run may cause macOS to request Bluetooth access for Codex or Terminal.
Allow it under **System Settings > Privacy & Security > Bluetooth**. Make sure
Bluetooth is enabled and the sensor is close enough to the Mac.

Each output line is one JSON object containing:

- the macOS CoreBluetooth device ID and advertised name;
- RSSI and transmit power, when available;
- manufacturer data as company-ID-to-hex mappings;
- service data as service-UUID-to-hex mappings;
- advertised service UUIDs.

When the company ID is `0x0969` and service UUID `0xFD3D` identifies device type
`5`, the probe also emits a `sensor_reading` object for the SwitchBot Meter Pro
(CO2 Monitor). It contains temperature in Celsius, relative humidity, CO2 in ppm,
and battery percentage when available. The raw bytes remain in the record so the
decoded values are auditable.

Use `--match TEXT` after identifying a likely device to reduce noise. The match is
case-insensitive and searches the entire record, including payload hex. By default,
the probe suppresses advertisements whose payload is unchanged; use
`--emit-repeats` to capture every received packet.

The captured manufacturer/service bytes are the evidence needed to select and test
the sensor-specific temperature, humidity, and CO₂ decoder. Do not infer readings
from byte positions until the exact sensor model and its advertisement format are
confirmed.
