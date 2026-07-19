from __future__ import annotations

import json
import logging
import secrets

from fastapi import APIRouter, Header, Request
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from app.models.schemas import CrawlRequest
from app.services.crawl_tool import CrawlToolError, CrawlToolService

logger = logging.getLogger("fruitspy.crawl")


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
) -> JSONResponse:
    headers = {"Retry-After": "1"} if status_code == 429 else None
    return JSONResponse(
        status_code=status_code,
        headers=headers,
        content={
            "ok": False,
            "error": {
                "code": code,
                "message": message,
                "retryable": retryable,
            },
        },
    )


def create_crawl_tool_router(*, service: CrawlToolService, token: str) -> APIRouter:
    router = APIRouter(prefix="/api/v1/tools/crawl", tags=["crawl-tool"])

    @router.get("/status")
    def crawl_status():
        return service.status()

    @router.post("")
    async def crawl(
        request: Request,
        authorization: str = Header(default=""),
    ):
        if token and not _has_valid_token(authorization, token):
            return _error_response(
                status_code=401,
                code="unauthorized",
                message="A valid Crawl API bearer token is required",
                retryable=False,
            )

        try:
            media_type = request.headers.get("content-type", "").split(";", 1)[0].lower()
            if media_type != "application/json":
                raise ValueError("content type must be application/json")
            body = await request.body()
            if len(body) > 16 * 1024:
                raise ValueError("request body is too large")
            raw_payload = json.loads(body)
            if not isinstance(raw_payload, dict):
                raise ValueError("request body must be a JSON object")
            payload = CrawlRequest.model_validate(raw_payload)
        except (json.JSONDecodeError, UnicodeDecodeError, ValidationError, ValueError):
            return _error_response(
                status_code=400,
                code="invalid_request",
                message="Request must match the Crawl API v1 JSON schema",
                retryable=False,
            )

        try:
            return await service.crawl(
                url=payload.url,
                timeout_ms=payload.timeout_ms,
            )
        except CrawlToolError as exc:
            return _error_response(
                status_code=exc.status_code,
                code=exc.code,
                message=str(exc),
                retryable=exc.retryable,
            )
        except Exception:
            logger.exception("Unexpected Crawl API failure")
            return _error_response(
                status_code=500,
                code="crawl_error",
                message="Crawler failed unexpectedly",
                retryable=True,
            )

    return router
