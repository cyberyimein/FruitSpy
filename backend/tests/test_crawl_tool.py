from __future__ import annotations

import asyncio
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.crawl_tool import create_crawl_tool_router
from app.config import load_runtime_config
from app.services.crawl_tool import (
    CapacityExceededError,
    ContentNotExtractableError,
    CrawlBackendResult,
    CrawlToolService,
    NetworkGuard,
    NavigationTimeoutError,
    PinnedPublicResolver,
    PublicURLPolicy,
    ResponseTooLargeError,
    URLNotAllowedError,
    sanitize_markdown,
)


async def public_resolver(_hostname: str) -> tuple[str, ...]:
    return ("93.184.216.34",)


class FakeCrawlBackend:
    def __init__(self) -> None:
        self.preflight_calls = 0
        self.crawl_calls = 0
        self.result = CrawlBackendResult(
            final_url="https://example.com/article",
            title="Example",
            markdown="# Example\n\nReadable content.",
            status_code=200,
            content_type="text/html",
            html_bytes=1024,
            links_seen=3,
        )

    async def preflight(self) -> None:
        self.preflight_calls += 1

    async def crawl(self, **_kwargs) -> CrawlBackendResult:
        self.crawl_calls += 1
        return self.result


class BlockingCrawlBackend(FakeCrawlBackend):
    def __init__(self) -> None:
        super().__init__()
        self.started = asyncio.Event()
        self.release = asyncio.Event()

    async def crawl(self, **_kwargs) -> CrawlBackendResult:
        self.started.set()
        await self.release.wait()
        return await super().crawl(**_kwargs)


class TimingOutBackend(FakeCrawlBackend):
    async def crawl(self, **_kwargs) -> CrawlBackendResult:
        raise asyncio.TimeoutError


def build_service(
    backend: FakeCrawlBackend,
    *,
    max_concurrency: int = 2,
    max_queue: int = 10,
    max_response_bytes: int = 2_000_000,
) -> CrawlToolService:
    return CrawlToolService(
        backend=backend,
        enabled=True,
        default_timeout_ms=30_000,
        max_timeout_ms=60_000,
        max_concurrency=max_concurrency,
        max_queue=max_queue,
        max_redirects=5,
        max_response_bytes=max_response_bytes,
        max_html_bytes=8 * 1024 * 1024,
        policy=PublicURLPolicy(resolver=public_resolver),
    )


class PublicURLPolicyTests(unittest.IsolatedAsyncioTestCase):
    async def test_accepts_public_http_and_https_urls(self) -> None:
        policy = PublicURLPolicy(resolver=public_resolver)

        normalized = await policy.validate("HTTPS://Example.COM/path?q=1")

        self.assertEqual(normalized, "https://example.com/path?q=1")

    async def test_rejects_protocols_credentials_localhost_and_private_literals(self) -> None:
        policy = PublicURLPolicy(resolver=public_resolver)
        blocked = (
            "file:///etc/passwd",
            "data:text/plain,secret",
            "ftp://example.com/file",
            "javascript:alert(1)",
            "http://user:pass@example.com/",
            "http://localhost/",
            "http://api.localhost/",
            "http://127.0.0.1/",
            "http://169.254.169.254/",
            "http://10.0.0.1/",
            "http://172.16.0.1/",
            "http://192.168.0.1/",
            "http://[::1]/",
        )

        for url in blocked:
            with self.subTest(url=url):
                with self.assertRaises(URLNotAllowedError):
                    await policy.validate(url)

    async def test_rejects_hostname_when_any_dns_answer_is_not_public(self) -> None:
        async def mixed_resolver(_hostname: str) -> tuple[str, ...]:
            return ("93.184.216.34", "10.0.0.8")

        policy = PublicURLPolicy(resolver=mixed_resolver)

        with self.assertRaises(URLNotAllowedError):
            await policy.validate("https://mixed.example/")

    async def test_connection_resolver_rechecks_dns_and_only_returns_public_ips(self) -> None:
        calls = 0

        async def rebinding_resolver(_hostname: str) -> tuple[str, ...]:
            nonlocal calls
            calls += 1
            return ("93.184.216.34",) if calls == 1 else ("127.0.0.1",)

        policy = PublicURLPolicy(resolver=rebinding_resolver)
        await policy.validate("https://rebind.example/")

        with self.assertRaises(URLNotAllowedError):
            await PinnedPublicResolver(policy).resolve("rebind.example", 443)

    async def test_redirect_guard_revalidates_targets_and_limits_hops(self) -> None:
        policy = PublicURLPolicy(resolver=public_resolver)
        guard = NetworkGuard(
            policy=policy,
            max_redirects=1,
            initial_url="https://example.com/",
        )

        await guard.check("https://www.example.com/one", is_main_navigation=True)
        with self.assertRaises(URLNotAllowedError):
            await guard.check("https://www.example.com/two", is_main_navigation=True)

        private_guard = NetworkGuard(
            policy=policy,
            max_redirects=5,
            initial_url="https://example.com/",
        )
        with self.assertRaises(URLNotAllowedError):
            await private_guard.check("http://127.0.0.1/", is_main_navigation=True)


class CrawlToolServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_returns_anomalo_compatible_top_level_response(self) -> None:
        backend = FakeCrawlBackend()
        service = build_service(backend)
        await service.initialize()

        result = await service.crawl(url="https://example.com/", timeout_ms=30_000)

        self.assertTrue(result.ok)
        self.assertEqual(result.final_url, "https://example.com/article")
        self.assertEqual(result.markdown, "# Example\n\nReadable content.")
        self.assertEqual(result.status_code, 200)
        self.assertTrue(result.rendered)
        self.assertEqual(result.metrics.links_seen, 3)
        self.assertEqual(backend.preflight_calls, 1)

    async def test_revalidates_final_url(self) -> None:
        backend = FakeCrawlBackend()
        backend.result = CrawlBackendResult(
            final_url="http://127.0.0.1/internal",
            title="Unsafe",
            markdown="content",
            status_code=200,
            content_type="text/html",
            html_bytes=10,
            links_seen=0,
        )
        service = build_service(backend)
        await service.initialize()

        with self.assertRaises(URLNotAllowedError):
            await service.crawl(url="https://example.com/", timeout_ms=30_000)

    async def test_rejects_empty_and_oversized_markdown(self) -> None:
        backend = FakeCrawlBackend()
        service = build_service(backend, max_response_bytes=512)
        await service.initialize()

        backend.result = CrawlBackendResult(
            final_url="https://example.com/",
            title="",
            markdown="",
            status_code=200,
            content_type="text/html",
            html_bytes=10,
            links_seen=0,
        )
        with self.assertRaises(ContentNotExtractableError):
            await service.crawl(url="https://example.com/", timeout_ms=30_000)

        backend.result = CrawlBackendResult(
            final_url="https://example.com/",
            title="",
            markdown="x" * 1000,
            status_code=200,
            content_type="text/html",
            html_bytes=1000,
            links_seen=0,
        )
        with self.assertRaises(ResponseTooLargeError):
            await service.crawl(url="https://example.com/", timeout_ms=30_000)

    async def test_maps_timeout_and_rejects_excess_capacity(self) -> None:
        timeout_service = build_service(TimingOutBackend())
        await timeout_service.initialize()
        with self.assertRaises(NavigationTimeoutError):
            await timeout_service.crawl(url="https://example.com/", timeout_ms=1000)

        backend = BlockingCrawlBackend()
        service = build_service(backend, max_concurrency=1, max_queue=0)
        await service.initialize()
        first = asyncio.create_task(
            service.crawl(url="https://example.com/first", timeout_ms=30_000)
        )
        await backend.started.wait()
        with self.assertRaises(CapacityExceededError):
            await service.crawl(url="https://example.com/second", timeout_ms=30_000)
        backend.release.set()
        await first

    def test_status_exposes_readiness_and_hard_limits(self) -> None:
        service = build_service(FakeCrawlBackend())

        initial = service.status()

        self.assertEqual(initial.id, "crawl4ai")
        self.assertFalse(initial.ready)
        self.assertEqual(initial.limits.max_concurrency, 2)
        self.assertEqual(initial.limits.max_response_bytes, 2_000_000)


class CrawlMarkdownSafetyTests(unittest.TestCase):
    def test_removes_executable_html_and_dangerous_links(self) -> None:
        markdown = (
            "# Safe\n"
            "<script>alert(1)</script>"
            '<div onclick="steal()">Visible</div>\n'
            "[click](javascript:alert(1))"
        )

        cleaned = sanitize_markdown(markdown)

        self.assertNotIn("<script", cleaned)
        self.assertNotIn("onclick", cleaned)
        self.assertNotIn("javascript:", cleaned)
        self.assertIn("Visible", cleaned)


class FakeAPIService:
    def status(self) -> dict:
        return {"id": "crawl4ai", "ready": True}

    async def crawl(self, *, url: str, timeout_ms: int | None) -> dict:
        return {
            "ok": True,
            "url": url,
            "final_url": url,
            "title": "",
            "markdown": "content",
            "status_code": 200,
            "rendered": True,
        }


class CrawlToolAPITests(unittest.TestCase):
    def build_client(self, token: str = "secret") -> TestClient:
        app = FastAPI()
        app.include_router(
            create_crawl_tool_router(service=FakeAPIService(), token=token)
        )
        return TestClient(app)

    def test_requires_configured_bearer_token(self) -> None:
        client = self.build_client()

        response = client.post(
            "/api/v1/tools/crawl",
            json={"url": "https://example.com/", "wait_for": None},
        )

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()["error"]["code"], "unauthorized")

    def test_accepts_valid_request_and_optional_auth_mode(self) -> None:
        authenticated = self.build_client().post(
            "/api/v1/tools/crawl",
            headers={"Authorization": "Bearer secret"},
            json={
                "url": "https://example.com/",
                "wait_for": None,
                "timeout_ms": 30_000,
            },
        )
        unauthenticated = self.build_client(token="").post(
            "/api/v1/tools/crawl",
            json={"url": "https://example.com/"},
        )

        self.assertEqual(authenticated.status_code, 200)
        self.assertTrue(authenticated.json()["rendered"])
        self.assertEqual(unauthenticated.status_code, 200)

    def test_invalid_json_unknown_fields_and_wait_selector_return_400(self) -> None:
        client = self.build_client(token="")
        responses = (
            client.post(
                "/api/v1/tools/crawl",
                content=b"{not-json",
                headers={"Content-Type": "application/json"},
            ),
            client.post(
                "/api/v1/tools/crawl",
                json={"url": "https://example.com/", "unknown": True},
            ),
            client.post(
                "/api/v1/tools/crawl",
                json={"url": "https://example.com/", "wait_for": "#app"},
            ),
            client.post(
                "/api/v1/tools/crawl",
                content='{"url":"https://example.com/"}',
                headers={"Content-Type": "text/plain"},
            ),
        )

        for response in responses:
            self.assertEqual(response.status_code, 400)
            self.assertEqual(response.json()["error"]["code"], "invalid_request")


class CrawlToolConfigTests(unittest.TestCase):
    def test_crawl_token_falls_back_to_python_token_and_limits_are_capped(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "env.json"
            config_path.write_text(
                json.dumps(
                    {
                        "python_tool_token": "shared-token",
                        "crawl_api_token": "",
                        "crawl_max_concurrency": 999,
                        "crawl_max_queue": 999,
                        "crawl_max_html_bytes": 999_999_999,
                    }
                ),
                encoding="utf-8",
            )
            with patch.dict(
                os.environ,
                {"FRUITSPY_CONFIG_PATH": str(config_path)},
                clear=True,
            ):
                config = load_runtime_config()

        self.assertEqual(config.crawl_api_token, "shared-token")
        self.assertEqual(config.crawl_max_concurrency, 8)
        self.assertEqual(config.crawl_max_queue, 100)
        self.assertEqual(config.crawl_max_html_bytes, 10 * 1024 * 1024)


if __name__ == "__main__":
    unittest.main()
