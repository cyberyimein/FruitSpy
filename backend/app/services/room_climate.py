from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Optional, Protocol

from bleak import BleakScanner
from bleak.backends.device import BLEDevice
from bleak.backends.scanner import AdvertisementData

from app.models.schemas import RoomClimateReading, RoomClimateStatus

logger = logging.getLogger("fruitspy.room-climate")

SWITCHBOT_COMPANY_ID = 0x0969
SWITCHBOT_SERVICE_UUID = "0000fd3d-0000-1000-8000-00805f9b34fb"
SWITCHBOT_METER_PRO_CO2_TYPE = ord("5")


def decode_switchbot_meter_pro_co2(
    manufacturer_data: dict[int, bytes],
    service_data: dict[str, bytes],
) -> dict[str, float | int] | None:
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

    reading: dict[str, float | int] = {
        "temperature_c": temperature_c,
        "humidity_percent": sensor_bytes[2] & 0x7F,
        "co2_ppm": co2_ppm,
    }
    if len(switchbot_service) >= 3:
        reading["battery_percent"] = switchbot_service[2] & 0x7F
    return reading


class Scanner(Protocol):
    async def start(self) -> None: ...

    async def stop(self) -> None: ...


ScannerFactory = Callable[
    [Callable[[BLEDevice, AdvertisementData], None]],
    Scanner,
]


def _default_scanner_factory(
    callback: Callable[[BLEDevice, AdvertisementData], None],
) -> Scanner:
    return BleakScanner(detection_callback=callback)


@dataclass(frozen=True)
class _ObservedReading:
    reading: RoomClimateReading
    rssi: int


class RoomClimateService:
    """Periodically scan the host BLE adapter and retain only the latest reading."""

    def __init__(
        self,
        *,
        interval_seconds: int = 300,
        scan_seconds: int = 45,
        device_id: str = "",
        scanner_factory: ScannerFactory = _default_scanner_factory,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self.interval_seconds = max(interval_seconds, 1)
        self.scan_seconds = max(scan_seconds, 1)
        self.device_id = device_id.strip().casefold()
        self._scanner_factory = scanner_factory
        self._clock = clock
        self._latest: Optional[RoomClimateReading] = None
        self._error: Optional[str] = None
        self._scanning = False
        self._last_attempt_at: Optional[float] = None
        self._next_scan_at: Optional[float] = None
        self._task: Optional[asyncio.Task[None]] = None

    @property
    def latest(self) -> Optional[RoomClimateReading]:
        return self._latest

    def status(self) -> RoomClimateStatus:
        reading = self._latest
        age_seconds = (
            max(0, int(self._clock() - reading.observed_at))
            if reading is not None
            else None
        )
        stale = age_seconds is None or age_seconds > self.interval_seconds * 2
        if self._scanning:
            state = "scanning"
        elif self._error and reading is None:
            state = "unavailable"
        elif stale:
            state = "stale"
        else:
            state = "ready"
        return RoomClimateStatus(
            state=state,
            reading=reading,
            stale=stale,
            age_seconds=age_seconds,
            interval_seconds=self.interval_seconds,
            scan_seconds=self.scan_seconds,
            last_attempt_at=self._last_attempt_at,
            next_scan_at=self._next_scan_at,
            error=self._error,
        )

    async def scan_once(self) -> Optional[RoomClimateReading]:
        best: Optional[_ObservedReading] = None

        def on_advertisement(
            device: BLEDevice,
            advertisement: AdvertisementData,
        ) -> None:
            nonlocal best
            if self.device_id and device.address.casefold() != self.device_id:
                return
            decoded = decode_switchbot_meter_pro_co2(
                advertisement.manufacturer_data,
                advertisement.service_data,
            )
            if not decoded:
                return
            reading = RoomClimateReading(
                observed_at=self._clock(),
                observed_at_iso=datetime.now(timezone.utc).isoformat(),
                device_id=device.address,
                temperature_c=float(decoded["temperature_c"]),
                humidity_percent=int(decoded["humidity_percent"]),
                co2_ppm=int(decoded["co2_ppm"]),
                battery_percent=(
                    int(decoded["battery_percent"])
                    if "battery_percent" in decoded
                    else None
                ),
                rssi=advertisement.rssi,
            )
            candidate = _ObservedReading(reading=reading, rssi=advertisement.rssi)
            if (
                best is None
                or best.reading.device_id == reading.device_id
                or candidate.rssi >= best.rssi
            ):
                best = candidate

        scanner = self._scanner_factory(on_advertisement)
        started = False
        self._scanning = True
        self._last_attempt_at = self._clock()
        self._error = None
        try:
            await scanner.start()
            started = True
            await asyncio.sleep(self.scan_seconds)
            if best is not None:
                self._latest = best.reading
            return self._latest
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            self._error = f"{type(exc).__name__}: {exc}"
            logger.warning("Room climate BLE scan failed: %s", self._error)
            return self._latest
        finally:
            if started:
                try:
                    await scanner.stop()
                except Exception as exc:
                    self._error = f"{type(exc).__name__}: {exc}"
                    logger.warning("Room climate BLE scanner stop failed: %s", self._error)
            self._scanning = False

    async def _run(self) -> None:
        while True:
            cycle_started = self._clock()
            await self.scan_once()
            delay = max(0.0, self.interval_seconds - (self._clock() - cycle_started))
            self._next_scan_at = self._clock() + delay
            await asyncio.sleep(delay)

    def start(self) -> None:
        if self._task is None or self._task.done():
            self._next_scan_at = self._clock()
            self._task = asyncio.create_task(
                self._run(),
                name="fruitspy-room-climate",
            )

    async def stop(self) -> None:
        task = self._task
        self._task = None
        self._next_scan_at = None
        if task is None:
            return
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
