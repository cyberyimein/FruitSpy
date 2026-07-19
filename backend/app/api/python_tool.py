from __future__ import annotations

import ipaddress
import secrets
from ipaddress import IPv4Network, IPv6Network
from typing import Sequence
from uuid import UUID

from fastapi import APIRouter, Header, Request
from fastapi.responses import JSONResponse, Response

from app.models.schemas import PythonExecutionRequest, PythonToolEnableRequest
from app.services.python_tool import PythonToolError, PythonToolService

DEFAULT_ALLOWED_CIDRS = ("192.168.64.0/24",)


def _compile_allowed_networks(
    allowed_cidrs: Sequence[str],
) -> tuple[IPv4Network | IPv6Network, ...]:
    networks: list[IPv4Network | IPv6Network] = [
        ipaddress.ip_network("127.0.0.0/8"),
        ipaddress.ip_network("::1/128"),
        ipaddress.ip_network("::ffff:127.0.0.0/104"),
    ]
    for cidr in allowed_cidrs:
        try:
            networks.append(ipaddress.ip_network(cidr, strict=False))
        except ValueError as exc:
            raise ValueError(f"Invalid Python Tool allowed CIDR: {cidr}") from exc
    return tuple(networks)


def _is_allowed_host(
    client_host: str,
    allowed_networks: Sequence[IPv4Network | IPv6Network],
) -> bool:
    try:
        address = ipaddress.ip_address(client_host)
    except ValueError:
        return False
    if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped:
        address = address.ipv4_mapped
    return any(address in network for network in allowed_networks if network.version == address.version)


def _is_allowed_source(
    request: Request,
    allowed_networks: Sequence[IPv4Network | IPv6Network],
) -> bool:
    client_host = request.client.host if request.client else ""
    return _is_allowed_host(client_host, allowed_networks)


def _has_valid_token(authorization: str, token: str) -> bool:
    scheme, separator, credential = authorization.partition(" ")
    return bool(
        separator == " "
        and scheme.lower() == "bearer"
        and token
        and secrets.compare_digest(credential, token)
    )


def _error_response(
    *,
    status_code: int,
    code: str,
    message: str,
    retryable: bool,
    request_id: str | None = None,
) -> JSONResponse:
    headers = {"Retry-After": "1"} if status_code == 429 else None
    return JSONResponse(
        status_code=status_code,
        headers=headers,
        content={
            "schema_version": 1,
            "request_id": request_id,
            "error": {
                "code": code,
                "message": message,
                "retryable": retryable,
            },
        },
    )


def create_python_tool_router(
    *,
    service: PythonToolService,
    token: str,
    allowed_cidrs: Sequence[str] = DEFAULT_ALLOWED_CIDRS,
) -> APIRouter:
    router = APIRouter(prefix="/api/v1/tools/python", tags=["python-tool"])
    allowed_networks = _compile_allowed_networks(allowed_cidrs)

    @router.get("")
    def python_tool_status():
        return service.status()

    @router.put("/enabled")
    def set_python_tool_enabled(
        payload: PythonToolEnableRequest,
        x_fruitspy_control: str = Header(default=""),
    ):
        if x_fruitspy_control != "1":
            return _error_response(
                status_code=403,
                code="control_header_required",
                message="Missing FruitSpy control header",
                retryable=False,
            )
        return service.set_enabled(payload.enabled)

    @router.post("/executions")
    def execute_python(
        payload: PythonExecutionRequest,
        request: Request,
        authorization: str = Header(default=""),
        idempotency_key: str = Header(default="", alias="Idempotency-Key"),
    ):
        if not _is_allowed_source(request, allowed_networks):
            return _error_response(
                status_code=403,
                code="loopback_required",
                message="Python execution source is outside the loopback or configured container network allowlist",
                retryable=False,
                request_id=idempotency_key or None,
            )

        if not token:
            return _error_response(
                status_code=503,
                code="authentication_unconfigured",
                message="FRUITSPY_PYTHON_TOOL_TOKEN is not configured",
                retryable=False,
                request_id=idempotency_key or None,
            )

        if not _has_valid_token(authorization, token):
            return _error_response(
                status_code=401,
                code="unauthorized",
                message="A valid Python Tool bearer token is required",
                retryable=False,
                request_id=idempotency_key or None,
            )

        try:
            request_id = str(UUID(idempotency_key))
        except (ValueError, AttributeError):
            return _error_response(
                status_code=422,
                code="invalid_idempotency_key",
                message="Idempotency-Key must be a UUID",
                retryable=False,
                request_id=idempotency_key or None,
            )

        try:
            return service.execute(
                request_id=request_id,
                code=payload.code,
                timeout_ms=payload.timeout_ms,
                artifacts=[item.model_dump() for item in payload.artifacts],
            )
        except PythonToolError as exc:
            return _error_response(
                status_code=exc.status_code,
                code=exc.code,
                message=str(exc),
                retryable=exc.retryable,
                request_id=request_id,
            )

    @router.get("/executions/{execution_id}/artifacts/{artifact_name}")
    def download_python_artifact(
        execution_id: str,
        artifact_name: str,
        request: Request,
        authorization: str = Header(default=""),
    ):
        if not _is_allowed_source(request, allowed_networks):
            return _error_response(
                status_code=403,
                code="loopback_required",
                message="Python artifact source is outside the loopback or configured container network allowlist",
                retryable=False,
                request_id=execution_id,
            )
        if not token:
            return _error_response(
                status_code=503,
                code="authentication_unconfigured",
                message="FRUITSPY_PYTHON_TOOL_TOKEN is not configured",
                retryable=False,
                request_id=execution_id,
            )
        if not _has_valid_token(authorization, token):
            return _error_response(
                status_code=401,
                code="unauthorized",
                message="A valid Python Tool bearer token is required",
                retryable=False,
                request_id=execution_id,
            )
        try:
            artifact = service.get_artifact(execution_id, artifact_name)
        except PythonToolError as exc:
            return _error_response(
                status_code=exc.status_code,
                code=exc.code,
                message=str(exc),
                retryable=exc.retryable,
                request_id=execution_id,
            )
        return Response(
            content=artifact.data,
            media_type=artifact.media_type,
            headers={
                "Cache-Control": "no-store",
                "Content-Disposition": f'inline; filename="{artifact.name}"',
            },
        )

    return router
