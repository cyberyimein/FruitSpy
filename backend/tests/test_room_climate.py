from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from app.models.schemas import RoomClimateReading
from app.services.room_climate import (
    RoomClimateService,
    decode_switchbot_meter_pro_co2,
)


OLDER_CAPTURED_PAYLOAD = bytes.fromhex("b0e9fe7a87de9d64039b3b000a021d00")
CAPTURED_PAYLOAD = bytes.fromhex("b0e9fe7a87de9d64039b3a000a021d00")
CAPTURED_SERVICE = bytes.fromhex("350064")


class FakeScanner:
    def __init__(self, callback) -> None:
        self.callback = callback
        self.stopped = False

    async def start(self) -> None:
        device = SimpleNamespace(address="sensor-id")
        older_advertisement = SimpleNamespace(
            manufacturer_data={0x0969: OLDER_CAPTURED_PAYLOAD},
            service_data={
                "0000fd3d-0000-1000-8000-00805f9b34fb": CAPTURED_SERVICE
            },
            rssi=-38,
        )
        latest_advertisement = SimpleNamespace(
            manufacturer_data={0x0969: CAPTURED_PAYLOAD},
            service_data={
                "0000fd3d-0000-1000-8000-00805f9b34fb": CAPTURED_SERVICE
            },
            rssi=-43,
        )
        self.callback(device, older_advertisement)
        self.callback(device, latest_advertisement)

    async def stop(self) -> None:
        self.stopped = True


class RoomClimateTests(unittest.IsolatedAsyncioTestCase):
    def test_decodes_captured_meter_pro_co2_reading(self) -> None:
        reading = decode_switchbot_meter_pro_co2(
            {0x0969: CAPTURED_PAYLOAD},
            {"0000fd3d-0000-1000-8000-00805f9b34fb": CAPTURED_SERVICE},
        )

        self.assertEqual(
            reading,
            {
                "temperature_c": 27.3,
                "humidity_percent": 58,
                "co2_ppm": 541,
                "battery_percent": 100,
            },
        )

    async def test_scan_replaces_latest_reading_without_persisting_history(self) -> None:
        service = RoomClimateService(
            interval_seconds=300,
            scan_seconds=1,
            scanner_factory=FakeScanner,
            clock=lambda: 1_000.0,
        )

        with patch(
            "app.services.room_climate.asyncio.sleep",
            new=AsyncMock(return_value=None),
        ):
            await service.scan_once()

        status = service.status()
        self.assertEqual(status.state, "ready")
        self.assertEqual(status.reading.temperature_c, 27.3)
        self.assertEqual(status.reading.humidity_percent, 58)
        self.assertEqual(status.reading.co2_ppm, 541)
        self.assertEqual(status.age_seconds, 0)

    def test_reading_becomes_stale_after_two_intervals(self) -> None:
        now = [1_000.0]
        service = RoomClimateService(
            interval_seconds=300,
            scan_seconds=45,
            clock=lambda: now[0],
        )
        service._latest = RoomClimateReading(
            observed_at=1_000.0,
            observed_at_iso="2026-07-30T11:24:34+00:00",
            device_id="sensor-id",
            temperature_c=27.3,
            humidity_percent=58,
            co2_ppm=541,
            battery_percent=100,
            rssi=-40,
        )

        now[0] = 1_601.0

        self.assertTrue(service.status().stale)


if __name__ == "__main__":
    unittest.main()
