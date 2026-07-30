from __future__ import annotations

import base64
import json
import secrets
from typing import Any
from urllib.parse import urlsplit

from fastapi import APIRouter, Header, Request
from fastapi.responses import JSONResponse, Response

from app.models.schemas import RoomClimateMcpModeRequest
from app.services.room_climate_mcp import (
    LEGACY_PROTOCOL_VERSION,
    MODERN_PROTOCOL_VERSION,
    TOOL_NAME,
    RoomClimateMcpService,
)


def _jsonrpc_error(
    request_id: Any,
    code: int,
    message: str,
    *,
    status_code: int = 200,
    data: dict[str, Any] | None = None,
) -> JSONResponse:
    error: dict[str, Any] = {"code": code, "message": message}
    if data is not None:
        error["data"] = data
    return JSONResponse(
        status_code=status_code,
        content={"jsonrpc": "2.0", "id": request_id, "error": error},
    )


def _has_valid_token(authorization: str, token: str) -> bool:
    scheme, separator, credential = authorization.partition(" ")
    return bool(
        separator == " "
        and scheme.lower() == "bearer"
        and token
        and secrets.compare_digest(credential, token)
    )


def _origin_is_allowed(request: Request) -> bool:
    origin = request.headers.get("origin")
    if not origin:
        return True
    try:
        parsed = urlsplit(origin)
    except ValueError:
        return False
    return (
        parsed.scheme in {"http", "https"}
        and parsed.netloc.casefold() == request.headers.get("host", "").casefold()
    )


def _decode_header_value(value: str) -> str | None:
    if value.startswith("=?base64?") and value.endswith("?="):
        try:
            encoded = value[len("=?base64?") : -2]
            return base64.b64decode(encoded, validate=True).decode("utf-8")
        except (ValueError, UnicodeDecodeError):
            return None
    return value


def _modern_validation_error(
    request: Request,
    payload: dict[str, Any],
) -> str | None:
    method = payload.get("method")
    params = payload.get("params")
    params = params if isinstance(params, dict) else {}
    meta = params.get("_meta")
    meta = meta if isinstance(meta, dict) else {}
    body_version = meta.get("io.modelcontextprotocol/protocolVersion")
    header_version = request.headers.get("mcp-protocol-version")
    if header_version != body_version:
        return "MCP-Protocol-Version header does not match request _meta"
    if request.headers.get("mcp-method") != method:
        return "Mcp-Method header does not match request method"
    if method == "tools/call":
        header_name = request.headers.get("mcp-name")
        decoded_name = _decode_header_value(header_name) if header_name else None
        if decoded_name != params.get("name"):
            return "Mcp-Name header does not match tool name"
    client_info = meta.get("io.modelcontextprotocol/clientInfo")
    if client_info is not None and not isinstance(client_info, dict):
        return "request _meta clientInfo is malformed"
    if not isinstance(meta.get("io.modelcontextprotocol/clientCapabilities"), dict):
        return "request _meta is missing clientCapabilities"
    accept = request.headers.get("accept", "")
    if "application/json" not in accept or "text/event-stream" not in accept:
        return "Accept header must include application/json and text/event-stream"
    return None


def create_room_climate_mcp_router(
    *,
    service: RoomClimateMcpService,
    token: str,
) -> APIRouter:
    router = APIRouter(prefix="/api/v1/tools/room-climate", tags=["room-climate-mcp"])

    @router.get("")
    def room_climate_mcp_status():
        return service.status()

    @router.put("/protocol-mode")
    def set_protocol_mode(
        payload: RoomClimateMcpModeRequest,
        x_fruitspy_control: str = Header(default=""),
    ):
        if x_fruitspy_control != "1":
            return JSONResponse(
                status_code=403,
                content={"error": {"message": "Missing FruitSpy control header"}},
            )
        return service.set_protocol_mode(payload.protocol_mode)

    @router.post("/mcp")
    async def mcp_endpoint(
        request: Request,
        authorization: str = Header(default=""),
    ):
        if not _origin_is_allowed(request):
            return _jsonrpc_error(None, -32000, "Invalid Origin", status_code=403)
        if token and not _has_valid_token(authorization, token):
            return _jsonrpc_error(None, -32000, "Unauthorized", status_code=401)
        try:
            body = await request.body()
            if len(body) > 64 * 1024:
                raise ValueError
            payload = json.loads(body)
            if not isinstance(payload, dict):
                raise ValueError
        except (json.JSONDecodeError, UnicodeDecodeError, ValueError):
            return _jsonrpc_error(None, -32700, "Parse error", status_code=400)

        request_id = payload.get("id")
        method = payload.get("method")
        params = payload.get("params")
        params = params if isinstance(params, dict) else {}
        if payload.get("jsonrpc") != "2.0" or not isinstance(method, str):
            return _jsonrpc_error(request_id, -32600, "Invalid Request", status_code=400)

        if service.protocol_mode == "modern":
            validation_error = _modern_validation_error(request, payload)
            if validation_error:
                return _jsonrpc_error(
                    request_id,
                    -32020,
                    f"Header mismatch: {validation_error}",
                    status_code=400,
                )
            requested_version = request.headers.get("mcp-protocol-version")
            if requested_version != MODERN_PROTOCOL_VERSION:
                return _jsonrpc_error(
                    request_id,
                    -32022,
                    "Unsupported protocol version",
                    status_code=400,
                    data={
                        "supported": [MODERN_PROTOCOL_VERSION],
                        "requested": requested_version,
                    },
                )
            modern = True
        else:
            requested_version = request.headers.get("mcp-protocol-version")
            if method != "initialize" and requested_version not in {
                None,
                LEGACY_PROTOCOL_VERSION,
            }:
                return _jsonrpc_error(
                    request_id,
                    -32602,
                    "Unsupported protocol version",
                    status_code=400,
                    data={
                        "supported": [LEGACY_PROTOCOL_VERSION],
                        "requested": requested_version,
                    },
                )
            modern = False

        if modern and method == "server/discover":
            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": {
                    "resultType": "complete",
                    "supportedVersions": [MODERN_PROTOCOL_VERSION],
                    "capabilities": {"tools": {}},
                    "_meta": {
                        "io.modelcontextprotocol/serverInfo": {
                            "name": "fruitspy-room-climate",
                            "version": "1.0.0",
                        }
                    },
                    "instructions": (
                        "Use get_room_climate for FruitSpy's latest local room reading."
                    ),
                    "ttlMs": 300000,
                    "cacheScope": "private",
                },
            }

        if not modern and method == "initialize":
            client_version = params.get("protocolVersion")
            if client_version != LEGACY_PROTOCOL_VERSION:
                return _jsonrpc_error(
                    request_id,
                    -32602,
                    "Unsupported protocol version",
                    data={
                        "supported": [LEGACY_PROTOCOL_VERSION],
                        "requested": client_version,
                    },
                )
            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": {
                    "protocolVersion": LEGACY_PROTOCOL_VERSION,
                    "capabilities": {"tools": {}},
                    "serverInfo": {
                        "name": "fruitspy-room-climate",
                        "version": "1.0.0",
                    },
                    "instructions": (
                        "Use get_room_climate for FruitSpy's latest local room reading."
                    ),
                },
            }

        if not modern and method == "notifications/initialized":
            return Response(status_code=202)

        if not modern and method == "ping":
            return {"jsonrpc": "2.0", "id": request_id, "result": {}}

        if method == "tools/list":
            result: dict[str, Any] = {"tools": [service.tool_definition()]}
            if modern:
                result.update(
                    {
                        "resultType": "complete",
                        "ttlMs": 300000,
                        "cacheScope": "private",
                    }
                )
            return {"jsonrpc": "2.0", "id": request_id, "result": result}

        if method == "tools/call":
            if params.get("name") != TOOL_NAME:
                return _jsonrpc_error(request_id, -32602, "Unknown tool")
            arguments = params.get("arguments", {})
            if not isinstance(arguments, dict) or arguments:
                return _jsonrpc_error(
                    request_id,
                    -32602,
                    "get_room_climate does not accept arguments",
                )
            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": service.call_tool_result(modern=modern),
            }

        return _jsonrpc_error(
            request_id,
            -32601,
            "Method not found",
            status_code=404 if modern else 200,
        )

    @router.get("/mcp")
    @router.delete("/mcp")
    def unsupported_mcp_method():
        return Response(status_code=405, headers={"Allow": "POST"})

    return router
