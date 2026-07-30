from __future__ import annotations

import unittest
from types import SimpleNamespace

from scripts.ble_sensor_probe import (
    advertisement_record,
    decode_switchbot_meter_pro_co2,
    payload_fingerprint,
    record_matches,
)


class BleSensorProbeTests(unittest.TestCase):
    def test_advertisement_record_serializes_binary_payloads(self) -> None:
        device = SimpleNamespace(address="device-uuid", name="fallback")
        advertisement = SimpleNamespace(
            local_name="Living Room",
            rssi=-61,
            tx_power=None,
            manufacturer_data={2409: bytes.fromhex("0102ff")},
            service_data={"FD3D": bytes.fromhex("a0b1")},
            service_uuids=["FD3D"],
        )

        record = advertisement_record(device, advertisement)

        self.assertEqual(record["device_id"], "device-uuid")
        self.assertEqual(record["name"], "Living Room")
        self.assertEqual(record["manufacturer_data"], {"0x0969": "0102ff"})
        self.assertEqual(record["service_data"], {"fd3d": "a0b1"})
        self.assertEqual(record["service_uuids"], ["fd3d"])

    def test_match_searches_names_identifiers_and_payloads(self) -> None:
        record = {
            "name": "Meter Pro",
            "device_id": "ABC",
            "manufacturer_data": {"0x0969": "cafe"},
        }

        self.assertTrue(record_matches(record, "meter"))
        self.assertTrue(record_matches(record, "CAFE"))
        self.assertFalse(record_matches(record, "kitchen"))

    def test_fingerprint_ignores_timestamp_and_signal_strength(self) -> None:
        first = {"observed_at": "one", "rssi": -50, "service_data": {"x": "01"}}
        second = {"observed_at": "two", "rssi": -80, "service_data": {"x": "01"}}

        self.assertEqual(payload_fingerprint(first), payload_fingerprint(second))

    def test_decodes_captured_switchbot_meter_pro_co2_payload(self) -> None:
        reading = decode_switchbot_meter_pro_co2(
            {0x0969: bytes.fromhex("b0e9fe7a87de9b64079b3b000a021d00")},
            {
                "0000fd3d-0000-1000-8000-00805f9b34fb": bytes.fromhex(
                    "350064"
                )
            },
        )

        self.assertEqual(
            reading,
            {
                "sensor_type": "switchbot_meter_pro_co2",
                "temperature_c": 27.7,
                "humidity_percent": 59,
                "co2_ppm": 541,
                "battery_percent": 100,
            },
        )

    def test_does_not_guess_model_without_co2_service_type(self) -> None:
        reading = decode_switchbot_meter_pro_co2(
            {0x0969: bytes.fromhex("b0e9fe7a87de9b64079b3b000a021d00")},
            {},
        )

        self.assertIsNone(reading)


if __name__ == "__main__":
    unittest.main()
