from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.room_climate_mcp import create_room_climate_mcp_router
from app.models.schemas import RoomClimateReading
from app.services.room_climate import RoomClimateService
from app.services.room_climate_mcp import (
    LEGACY_PROTOCOL_VERSION,
    MODERN_PROTOCOL_VERSION,
    RoomClimateMcpService,
    RoomClimateMcpStateStore,
)


def modern_headers(method: str, name: str | None = None) -> dict[str, str]:
    headers = {
        "Accept": "application/json, text/event-stream",
        "MCP-Protocol-Version": MODERN_PROTOCOL_VERSION,
        "Mcp-Method": method,
    }
    if name:
        headers["Mcp-Name"] = name
    return headers


def modern_params() -> dict:
    return {
        "_meta": {
            "io.modelcontextprotocol/protocolVersion": MODERN_PROTOCOL_VERSION,
            "io.modelcontextprotocol/clientInfo": {
                "name": "test-client",
                "version": "1.0",
            },
            "io.modelcontextprotocol/clientCapabilities": {},
        }
    }


class RoomClimateMcpTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        climate = RoomClimateService(clock=lambda: 1_010.0)
        climate._latest = RoomClimateReading(
            observed_at=1_000.0,
            observed_at_iso="2026-07-30T11:24:34+00:00",
            device_id="sensor-id",
            temperature_c=27.3,
            humidity_percent=58,
            co2_ppm=541,
            battery_percent=100,
            rssi=-40,
        )
        self.service = RoomClimateMcpService(
            climate=climate,
            state_store=RoomClimateMcpStateStore(
                Path(self.temporary.name) / "state.json"
            ),
            authentication_configured=False,
        )
        self.service.initialize()
        app = FastAPI()
        app.include_router(
            create_room_climate_mcp_router(service=self.service, token="")
        )
        self.client = TestClient(app)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_defaults_to_modern_protocol_and_supports_discovery(self) -> None:
        payload = {
            "jsonrpc": "2.0",
            "id": "discover",
            "method": "server/discover",
            "params": modern_params(),
        }

        response = self.client.post(
            "/api/v1/tools/room-climate/mcp",
            headers=modern_headers("server/discover"),
            json=payload,
        )

        self.assertEqual(response.status_code, 200)
        result = response.json()["result"]
        self.assertEqual(result["resultType"], "complete")
        self.assertEqual(result["supportedVersions"], [MODERN_PROTOCOL_VERSION])

    def test_modern_tool_call_returns_structured_current_reading(self) -> None:
        params = modern_params()
        params.update({"name": "get_room_climate", "arguments": {}})

        response = self.client.post(
            "/api/v1/tools/room-climate/mcp",
            headers=modern_headers("tools/call", "get_room_climate"),
            json={
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": params,
            },
        )

        result = response.json()["result"]
        self.assertEqual(result["resultType"], "complete")
        self.assertEqual(result["structuredContent"]["co2_ppm"], 541)
        self.assertEqual(result["structuredContent"]["age_seconds"], 10)

    def test_modern_protocol_rejects_mismatched_routing_headers(self) -> None:
        response = self.client.post(
            "/api/v1/tools/room-climate/mcp",
            headers=modern_headers("tools/list"),
            json={
                "jsonrpc": "2.0",
                "id": 3,
                "method": "server/discover",
                "params": modern_params(),
            },
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"]["code"], -32020)

    def test_modern_protocol_allows_omitted_optional_client_info(self) -> None:
        params = modern_params()
        params["_meta"].pop("io.modelcontextprotocol/clientInfo")

        response = self.client.post(
            "/api/v1/tools/room-climate/mcp",
            headers=modern_headers("tools/list"),
            json={
                "jsonrpc": "2.0",
                "id": 4,
                "method": "tools/list",
                "params": params,
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["result"]["resultType"], "complete")

    def test_modern_protocol_rejects_malformed_client_info(self) -> None:
        params = modern_params()
        params["_meta"]["io.modelcontextprotocol/clientInfo"] = "not-an-object"

        response = self.client.post(
            "/api/v1/tools/room-climate/mcp",
            headers=modern_headers("tools/list"),
            json={
                "jsonrpc": "2.0",
                "id": 5,
                "method": "tools/list",
                "params": params,
            },
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"]["code"], -32020)

    def test_switches_to_legacy_initialize_lifecycle(self) -> None:
        self.service.set_protocol_mode("legacy")

        initialize = self.client.post(
            "/api/v1/tools/room-climate/mcp",
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": LEGACY_PROTOCOL_VERSION,
                    "capabilities": {},
                    "clientInfo": {"name": "legacy-client", "version": "1.0"},
                },
            },
        )
        tool_list = self.client.post(
            "/api/v1/tools/room-climate/mcp",
            headers={"MCP-Protocol-Version": LEGACY_PROTOCOL_VERSION},
            json={
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/list",
                "params": {},
            },
        )

        self.assertEqual(initialize.status_code, 200)
        self.assertEqual(
            initialize.json()["result"]["protocolVersion"],
            LEGACY_PROTOCOL_VERSION,
        )
        self.assertNotIn("resultType", tool_list.json()["result"])


if __name__ == "__main__":
    unittest.main()
