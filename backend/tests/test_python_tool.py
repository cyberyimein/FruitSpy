from __future__ import annotations

import subprocess
import tempfile
import threading
import unittest
from pathlib import Path

from app.api.python_tool import _compile_allowed_networks, _is_allowed_host
from app.services.python_tool import (
    ApplePythonSandboxRunner,
    PythonCodeTooLargeError,
    PythonToolBusyError,
    PythonToolDisabledError,
    PythonToolService,
    PythonToolStateStore,
    PythonToolValidationError,
    SandboxArtifact,
    SandboxExecution,
)


class FakeSandboxRunner:
    image = "local/python@sha256:test"

    def __init__(self) -> None:
        self.preflight_calls = 0
        self.execution_calls = 0
        self.next_execution = SandboxExecution(0, "2\n", "")

    def preflight(self) -> None:
        self.preflight_calls += 1

    def execute(
        self,
        execution_id: str,
        code: str,
        timeout_seconds: float,
        artifacts: list[dict[str, str]] | None = None,
    ) -> SandboxExecution:
        self.execution_calls += 1
        return self.next_execution


class BlockingSandboxRunner(FakeSandboxRunner):
    def __init__(self) -> None:
        super().__init__()
        self.started = threading.Event()
        self.release = threading.Event()

    def execute(
        self,
        execution_id: str,
        code: str,
        timeout_seconds: float,
        artifacts: list[dict[str, str]] | None = None,
    ) -> SandboxExecution:
        self.started.set()
        self.release.wait(timeout=2)
        return super().execute(execution_id, code, timeout_seconds, artifacts)


class PythonToolServiceTests(unittest.TestCase):
    def build_service(
        self,
        temp_dir: str,
        runner: FakeSandboxRunner,
        *,
        default_enabled: bool = False,
        token_configured: bool = True,
        max_concurrency: int = 1,
    ) -> PythonToolService:
        return PythonToolService(
            runner=runner,
            state_store=PythonToolStateStore(Path(temp_dir) / "state.json"),
            default_enabled=default_enabled,
            token_configured=token_configured,
            timeout_seconds=10,
            max_output_chars=12,
            max_code_bytes=64,
            cpu_count=1,
            memory_mb=256,
            max_concurrency=max_concurrency,
        )

    def test_enable_preflights_and_persists_state(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            runner = FakeSandboxRunner()
            service = self.build_service(temp_dir, runner)

            status = service.set_enabled(True)

            self.assertTrue(status.enabled)
            self.assertTrue(status.ready)
            self.assertEqual(status.state, "ready")
            self.assertEqual(runner.preflight_calls, 1)
            self.assertTrue(
                PythonToolStateStore(Path(temp_dir) / "state.json").load_enabled(False)
            )

    def test_missing_token_keeps_enabled_feature_degraded(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            runner = FakeSandboxRunner()
            service = self.build_service(temp_dir, runner, token_configured=False)

            status = service.set_enabled(True)

            self.assertEqual(status.state, "degraded")
            self.assertIn("TOKEN", status.error or "")
            self.assertEqual(runner.preflight_calls, 0)

    def test_execution_result_is_cached_by_request_id(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            runner = FakeSandboxRunner()
            service = self.build_service(temp_dir, runner)
            service.set_enabled(True)

            first = service.execute(request_id="request-1", code="print(1 + 1)", timeout_ms=None)
            second = service.execute(request_id="request-1", code="print(999)", timeout_ms=None)

            self.assertTrue(first.ok)
            self.assertEqual(first.stdout, "2\n")
            self.assertEqual(second.execution_id, first.execution_id)
            self.assertEqual(runner.execution_calls, 1)

    def test_failed_and_timed_out_code_are_execution_results(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            runner = FakeSandboxRunner()
            service = self.build_service(temp_dir, runner)
            service.set_enabled(True)

            runner.next_execution = SandboxExecution(1, "", "syntax error with details")
            failed = service.execute(request_id="request-2", code="broken", timeout_ms=None)
            runner.next_execution = SandboxExecution(None, "", "", timed_out=True)
            timed_out = service.execute(request_id="request-3", code="while True: pass", timeout_ms=50)

            self.assertFalse(failed.ok)
            self.assertEqual(failed.status, "failed")
            self.assertTrue(failed.truncated.stderr)
            self.assertFalse(timed_out.ok)
            self.assertEqual(timed_out.status, "timed_out")
            self.assertEqual(timed_out.content, "Python sandbox timed out.")

    def test_artifacts_are_cached_and_exposed_as_download_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            runner = FakeSandboxRunner()
            runner.next_execution = SandboxExecution(
                0,
                "plot ready\n",
                "",
                artifacts={
                    "plot.png": SandboxArtifact(
                        name="plot.png",
                        media_type="image/png",
                        data=b"png-bytes",
                    )
                },
            )
            service = self.build_service(temp_dir, runner)
            service.set_enabled(True)

            result = service.execute(
                request_id="artifact-request",
                code="print('plot')",
                timeout_ms=None,
                artifacts=[{"path": "plot.png", "media_type": "image/png"}],
            )

            self.assertEqual(len(result.artifacts), 1)
            self.assertEqual(result.artifacts[0].name, "plot.png")
            self.assertEqual(result.artifacts[0].size_bytes, 9)
            self.assertEqual(service.get_artifact(result.execution_id, "plot.png").data, b"png-bytes")

    def test_artifact_paths_must_be_flat_tmp_file_names(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            runner = FakeSandboxRunner()
            service = self.build_service(temp_dir, runner)
            service.set_enabled(True)

            with self.assertRaises(PythonToolValidationError):
                service.execute(
                    request_id="unsafe-artifact",
                    code="print(1)",
                    timeout_ms=None,
                    artifacts=[{"path": "../secret.txt"}],
                )

    def test_disabled_large_and_busy_requests_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            runner = BlockingSandboxRunner()
            service = self.build_service(temp_dir, runner)

            with self.assertRaises(PythonToolDisabledError):
                service.execute(request_id="disabled", code="print(1)", timeout_ms=None)

            service.set_enabled(True)
            with self.assertRaises(PythonCodeTooLargeError):
                service.execute(request_id="large", code="x" * 65, timeout_ms=None)

            first_result: list[object] = []
            thread = threading.Thread(
                target=lambda: first_result.append(
                    service.execute(request_id="first", code="print(1)", timeout_ms=None)
                )
            )
            thread.start()
            self.assertTrue(runner.started.wait(timeout=1))
            with self.assertRaises(PythonToolBusyError):
                service.execute(request_id="second", code="print(2)", timeout_ms=None)
            runner.release.set()
            thread.join(timeout=2)
            self.assertEqual(len(first_result), 1)


class ApplePythonSandboxRunnerTests(unittest.TestCase):
    def test_preflight_and_execution_enforce_server_owned_sandbox_options(self) -> None:
        commands: list[list[str]] = []
        process_calls: list[tuple[list[str], str, float]] = []

        def command_runner(args, **kwargs):
            commands.append(args)
            if args[1:4] == ["network", "inspect", "fruitspy-python-internal"]:
                return subprocess.CompletedProcess(args, 0, '{"mode": "hostOnly"}', "")
            return subprocess.CompletedProcess(args, 0, "{}", "")

        def process_runner(command: list[str], code: str, timeout: float) -> SandboxExecution:
            process_calls.append((command, code, timeout))
            if "fruitspy-python-ready" in code:
                return SandboxExecution(0, "fruitspy-python-ready\n", "")
            return SandboxExecution(0, "42\n", "")

        runner = ApplePythonSandboxRunner(
            image="local/python@sha256:test",
            network="fruitspy-python-internal",
            cpu_count=1,
            memory_mb=256,
            cli_path="container",
            command_runner=command_runner,
            process_runner=process_runner,
        )

        runner.preflight()
        result = runner.execute("py-test", "print(42)", 3)

        self.assertEqual(result.stdout, "42\n")
        execution_command, input_code, timeout = process_calls[-1]
        self.assertNotIn(input_code, execution_command)
        self.assertEqual(timeout, 3)
        for required in (
            "--read-only",
            "--cap-drop",
            "ALL",
            "--network",
            "fruitspy-python-internal",
            "--no-dns",
            "--user",
            "65532:65532",
        ):
            self.assertIn(required, execution_command)
        self.assertTrue(any(command[1:3] == ["image", "inspect"] for command in commands))

    def test_timeout_forces_container_cleanup(self) -> None:
        commands: list[list[str]] = []

        def command_runner(args, **kwargs):
            commands.append(args)
            return subprocess.CompletedProcess(args, 0, "", "")

        runner = ApplePythonSandboxRunner(
            image="local/python@sha256:test",
            network="fruitspy-python-internal",
            cpu_count=1,
            memory_mb=256,
            cli_path="container",
            command_runner=command_runner,
            process_runner=lambda command, code, timeout: SandboxExecution(
                None, "", "", timed_out=True
            ),
        )

        runner.execute("py-timeout", "while True: pass", 1)

        self.assertTrue(any(command[1:3] == ["kill", "fruitspy-python-py-timeout"] for command in commands))
        self.assertTrue(any(command[1:4] == ["delete", "--force", "fruitspy-python-py-timeout"] for command in commands))


class PythonToolSourceAllowlistTests(unittest.TestCase):
    def test_loopback_and_configured_container_cidr_are_allowed(self) -> None:
        networks = _compile_allowed_networks(("192.168.64.0/24",))

        self.assertTrue(_is_allowed_host("127.0.0.1", networks))
        self.assertTrue(_is_allowed_host("::1", networks))
        self.assertTrue(_is_allowed_host("192.168.64.42", networks))
        self.assertTrue(_is_allowed_host("::ffff:192.168.64.42", networks))
        self.assertFalse(_is_allowed_host("192.168.65.42", networks))

    def test_invalid_cidr_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            _compile_allowed_networks(("not-a-network",))


if __name__ == "__main__":
    unittest.main()
