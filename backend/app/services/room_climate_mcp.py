from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Literal

from app.models.schemas import RoomClimateMcpStatus
from app.services.room_climate import RoomClimateService
from app.services.shared_state import JsonStateFile

MODERN_PROTOCOL_VERSION = "2026-07-28"
LEGACY_PROTOCOL_VERSION = "2025-11-25"
TOOL_NAME = "get_room_climate"

ProtocolMode = Literal["modern", "legacy"]


class RoomClimateMcpStateStore:
    def __init__(self, path: str | Path) -> None:
        self._state = JsonStateFile(path)
        self.path = self._state.path

    def load_mode(self, default: ProtocolMode = "modern") -> ProtocolMode:
        value = self._state.read().get("room_climate_mcp_protocol_mode")
        return value if value in {"modern", "legacy"} else default

    def save_mode(self, mode: ProtocolMode) -> None:
        self._state.set("room_climate_mcp_protocol_mode", mode)


class RoomClimateMcpService:
    def __init__(
        self,
        *,
        climate: RoomClimateService,
        state_store: RoomClimateMcpStateStore,
        authentication_configured: bool,
    ) -> None:
        self.climate = climate
        self.state_store = state_store
        self.authentication_configured = authentication_configured
        self.protocol_mode: ProtocolMode = "modern"

    def initialize(self) -> None:
        self.protocol_mode = self.state_store.load_mode("modern")

    @property
    def protocol_version(self) -> str:
        if self.protocol_mode == "modern":
            return MODERN_PROTOCOL_VERSION
        return LEGACY_PROTOCOL_VERSION

    def set_protocol_mode(self, mode: ProtocolMode) -> RoomClimateMcpStatus:
        self.state_store.save_mode(mode)
        self.protocol_mode = mode
        return self.status()

    def status(self) -> RoomClimateMcpStatus:
        return RoomClimateMcpStatus(
            protocol_mode=self.protocol_mode,
            protocol_version=self.protocol_version,
            authentication_configured=self.authentication_configured,
            climate=self.climate.status(),
        )

    @staticmethod
    def tool_definition() -> dict[str, Any]:
        return {
            "name": TOOL_NAME,
            "title": "Current room climate",
            "description": (
                "Return FruitSpy's latest local SwitchBot room temperature, "
                "relative humidity, CO2 concentration, battery level, and sample age."
            ),
            "inputSchema": {
                "type": "object",
                "additionalProperties": False,
            },
            "outputSchema": {
                "type": "object",
                "properties": {
                    "available": {"type": "boolean"},
                    "stale": {"type": "boolean"},
                    "observed_at": {"type": ["string", "null"]},
                    "age_seconds": {"type": ["integer", "null"]},
                    "temperature_c": {"type": ["number", "null"]},
                    "humidity_percent": {"type": ["integer", "null"]},
                    "co2_ppm": {"type": ["integer", "null"]},
                    "battery_percent": {"type": ["integer", "null"]},
                },
                "required": [
                    "available",
                    "stale",
                    "observed_at",
                    "age_seconds",
                    "temperature_c",
                    "humidity_percent",
                    "co2_ppm",
                    "battery_percent",
                ],
                "additionalProperties": False,
            },
            "annotations": {
                "readOnlyHint": True,
                "destructiveHint": False,
                "idempotentHint": True,
                "openWorldHint": False,
            },
        }

    def current_climate_payload(self) -> dict[str, Any]:
        status = self.climate.status()
        reading = status.reading
        return {
            "available": reading is not None,
            "stale": status.stale,
            "observed_at": reading.observed_at_iso if reading else None,
            "age_seconds": status.age_seconds,
            "temperature_c": reading.temperature_c if reading else None,
            "humidity_percent": reading.humidity_percent if reading else None,
            "co2_ppm": reading.co2_ppm if reading else None,
            "battery_percent": reading.battery_percent if reading else None,
        }

    def call_tool_result(self, *, modern: bool) -> dict[str, Any]:
        payload = self.current_climate_payload()
        result: dict[str, Any] = {
            "content": [
                {
                    "type": "text",
                    "text": json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
                }
            ],
            "structuredContent": payload,
            "isError": not payload["available"],
        }
        if modern:
            result["resultType"] = "complete"
        return result
