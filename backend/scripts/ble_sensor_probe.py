#!/usr/bin/env python3
"""Passively observe BLE advertisement payloads without connecting to devices."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from collections.abc import Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from bleak import BleakScanner
from bleak.backends.device import BLEDevice
from bleak.backends.scanner import AdvertisementData

SWITCHBOT_COMPANY_ID = 0x0969
SWITCHBOT_SERVICE_UUID = "0000fd3d-0000-1000-8000-00805f9b34fb"
SWITCHBOT_METER_PRO_CO2_TYPE = ord("5")


def decode_switchbot_meter_pro_co2(
    manufacturer_data: dict[int, bytes],
    service_data: dict[str, bytes],
) -> dict[str, Any] | None:
    """Decode a SwitchBot Meter Pro CO2 advertisement when both frames are present."""
    payload = manufacturer_data.get(SWITCHBOT_COMPANY_ID)
    switchbot_service = next(
        (
            value
            for uuid, value in service_data.items()
            if uuid.lower() == SWITCHBOT_SERVICE_UUID
        ),
        None,
    )
    if (
        payload is None
        or len(payload) < 15
        or switchbot_service is None
        or not switchbot_service
        or switchbot_service[0] & 0x7F != SWITCHBOT_METER_PRO_CO2_TYPE
    ):
        return None

    sensor_bytes = payload[8:11]
    sign = 1 if sensor_bytes[1] & 0x80 else -1
    temperature_c = sign * (
        (sensor_bytes[1] & 0x7F) + ((sensor_bytes[0] & 0x0F) / 10)
    )
    co2_ppm = int.from_bytes(payload[13:15], byteorder="big")
    if co2_ppm > 9999:
        return None

    reading: dict[str, Any] = {
        "sensor_type": "switchbot_meter_pro_co2",
        "temperature_c": temperature_c,
        "humidity_percent": sensor_bytes[2] & 0x7F,
        "co2_ppm": co2_ppm,
    }
    if len(switchbot_service) >= 3:
        reading["battery_percent"] = switchbot_service[2] & 0x7F
    return reading


def advertisement_record(
    device: BLEDevice,
    advertisement: AdvertisementData,
) -> dict[str, Any]:
    """Convert Bleak's platform objects into a stable, JSON-serializable record."""
    record = {
        "observed_at": datetime.now(timezone.utc).isoformat(),
        "device_id": device.address,
        "name": advertisement.local_name or device.name,
        "rssi": advertisement.rssi,
        "tx_power": advertisement.tx_power,
        "manufacturer_data": {
            f"0x{company_id:04x}": payload.hex()
            for company_id, payload in sorted(advertisement.manufacturer_data.items())
        },
        "service_data": {
            service_uuid.lower(): payload.hex()
            for service_uuid, payload in sorted(advertisement.service_data.items())
        },
        "service_uuids": sorted(uuid.lower() for uuid in advertisement.service_uuids),
    }
    reading = decode_switchbot_meter_pro_co2(
        advertisement.manufacturer_data,
        advertisement.service_data,
    )
    if reading:
        record["sensor_reading"] = reading
    return record


def record_matches(record: dict[str, Any], search: str | None) -> bool:
    if not search:
        return True
    needle = search.casefold()
    searchable = json.dumps(record, ensure_ascii=False, sort_keys=True).casefold()
    return needle in searchable


def payload_fingerprint(record: dict[str, Any]) -> str:
    """Ignore timestamp and RSSI so an unchanged beacon does not flood the output."""
    stable_fields = {
        key: value
        for key, value in record.items()
        if key not in {"observed_at", "rssi"}
    }
    return json.dumps(stable_fields, sort_keys=True, separators=(",", ":"))


async def scan(
    duration: float,
    search: str | None,
    output_path: Path | None,
    emit_repeats: bool,
) -> tuple[int, int]:
    seen_devices: set[str] = set()
    last_payloads: dict[str, str] = {}
    emitted = 0
    output_file = None

    if output_path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_file = output_path.open("a", encoding="utf-8")

    def on_advertisement(
        device: BLEDevice,
        advertisement: AdvertisementData,
    ) -> None:
        nonlocal emitted
        record = advertisement_record(device, advertisement)
        seen_devices.add(device.address)
        if not record_matches(record, search):
            return

        fingerprint = payload_fingerprint(record)
        if not emit_repeats and last_payloads.get(device.address) == fingerprint:
            return
        last_payloads[device.address] = fingerprint

        line = json.dumps(record, ensure_ascii=False, sort_keys=True)
        print(line, flush=True)
        if output_file:
            output_file.write(f"{line}\n")
            output_file.flush()
        emitted += 1

    scanner = BleakScanner(detection_callback=on_advertisement)
    try:
        await scanner.start()
        await asyncio.sleep(duration)
    finally:
        try:
            await scanner.stop()
        finally:
            if output_file:
                output_file.close()

    return len(seen_devices), emitted


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Observe nearby BLE advertisements and print JSON Lines. "
            "The probe never connects to or writes to a device."
        )
    )
    parser.add_argument(
        "--duration",
        type=float,
        default=30,
        help="scan duration in seconds (default: 30)",
    )
    parser.add_argument(
        "--match",
        help="case-insensitive filter over name, ID, UUIDs, and payload hex",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="also append matching records to this JSONL file",
    )
    parser.add_argument(
        "--emit-repeats",
        action="store_true",
        help="emit every advertisement, including unchanged payloads",
    )
    args = parser.parse_args(argv)
    if args.duration <= 0:
        parser.error("--duration must be greater than zero")
    return args


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    print(
        f"Scanning for {args.duration:g}s"
        f"{f' (matching {args.match!r})' if args.match else ''}…",
        file=sys.stderr,
        flush=True,
    )
    try:
        discovered, emitted = asyncio.run(
            scan(
                duration=args.duration,
                search=args.match,
                output_path=args.output,
                emit_repeats=args.emit_repeats,
            )
        )
    except KeyboardInterrupt:
        print("Scan cancelled.", file=sys.stderr)
        return 130
    except Exception as exc:
        print(f"BLE scan failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        print(
            "On macOS, enable Bluetooth and grant Bluetooth access to Codex or Terminal "
            "in System Settings > Privacy & Security > Bluetooth.",
            file=sys.stderr,
        )
        return 1

    print(
        f"Scan complete: saw {discovered} device(s), emitted {emitted} record(s).",
        file=sys.stderr,
    )
    return 0 if discovered else 2


if __name__ == "__main__":
    raise SystemExit(main())
