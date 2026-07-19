from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import secrets
import shutil
import subprocess
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Optional, Protocol
from urllib.parse import quote

from app.models.schemas import (
    PythonArtifactError,
    PythonArtifactResponse,
    PythonExecutionResponse,
    PythonExecutionTruncation,
    PythonToolLastExecution,
    PythonToolLimits,
    PythonToolStatus,
)

CommandRunner = Callable[..., subprocess.CompletedProcess[str]]


@dataclass(frozen=True)
class SandboxExecution:
    returncode: Optional[int]
    stdout: str
    stderr: str
    timed_out: bool = False
    artifacts: dict[str, "SandboxArtifact"] = field(default_factory=dict)
    artifact_errors: list[dict[str, str]] = field(default_factory=list)


@dataclass(frozen=True)
class SandboxArtifact:
    name: str
    media_type: str
    data: bytes


@dataclass(frozen=True)
class StoredArtifact:
    name: str
    media_type: str
    data: bytes
    expires_at: float


ProcessRunner = Callable[[list[str], str, float], SandboxExecution]


class SandboxRunner(Protocol):
    image: str

    def preflight(self) -> None: ...

    def execute(
        self,
        execution_id: str,
        code: str,
        timeout_seconds: float,
        artifacts: Optional[list[dict[str, str]]] = None,
    ) -> SandboxExecution: ...


class PythonToolError(RuntimeError):
    code = "python_tool_error"
    status_code = 500
    retryable = False


class PythonToolDisabledError(PythonToolError):
    code = "feature_disabled"
    status_code = 409


class PythonToolNotReadyError(PythonToolError):
    code = "sandbox_unavailable"
    status_code = 503


class PythonArtifactNotFoundError(PythonToolError):
    code = "artifact_not_found"
    status_code = 404


class PythonToolBusyError(PythonToolError):
    code = "sandbox_busy"
    status_code = 429
    retryable = True


class PythonToolRequestInProgressError(PythonToolError):
    code = "request_in_progress"
    status_code = 409
    retryable = True


class PythonCodeTooLargeError(PythonToolError):
    code = "code_too_large"
    status_code = 413


class PythonToolValidationError(PythonToolError):
    code = "invalid_request"
    status_code = 422


class PythonToolStateStore:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path).expanduser()
        self._lock = threading.Lock()

    def load_enabled(self, default: bool) -> bool:
        with self._lock:
            try:
                payload = json.loads(self.path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                return default
            value = payload.get("python_tool_enabled") if isinstance(payload, dict) else None
            return value if isinstance(value, bool) else default

    def save_enabled(self, enabled: bool) -> None:
        with self._lock:
            payload: dict[str, Any] = {}
            try:
                current = json.loads(self.path.read_text(encoding="utf-8"))
                if isinstance(current, dict):
                    payload.update(current)
            except (OSError, json.JSONDecodeError):
                pass

            payload["python_tool_enabled"] = enabled
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temp_path = self.path.with_name(f".{self.path.name}.{os.getpid()}.tmp")
            temp_path.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            os.replace(temp_path, self.path)


class ApplePythonSandboxRunner:
    _internal_network_keys = {"internal", "isinternal", "hostonly", "ishostonly"}

    def __init__(
        self,
        *,
        image: str,
        network: str,
        cpu_count: float,
        memory_mb: int,
        max_artifact_bytes: int = 2 * 1024 * 1024,
        max_artifact_total_bytes: int = 4 * 1024 * 1024,
        cli_path: str = "",
        user: str = "65532:65532",
        command_runner: CommandRunner = subprocess.run,
        process_runner: Optional[ProcessRunner] = None,
    ) -> None:
        self.image = image
        self.network = network
        self.cpu_count = cpu_count
        self.memory_mb = memory_mb
        self.max_artifact_bytes = max_artifact_bytes
        self.max_artifact_total_bytes = max_artifact_total_bytes
        self._configured_cli_path = cli_path
        self._user = user
        self._command_runner = command_runner
        self._process_runner = process_runner or self._run_process

    def _resolve_cli(self) -> str:
        if self._configured_cli_path:
            configured = self._configured_cli_path
            resolved = configured if "/" in configured and shutil.which(configured) else shutil.which(configured)
            if resolved:
                return str(resolved)
        else:
            direct = shutil.which("container")
            if direct:
                return direct
            for candidate in ("/usr/local/bin/container", "/opt/homebrew/bin/container"):
                if shutil.which(candidate):
                    return candidate
        raise RuntimeError("Apple container CLI was not found")

    def _run(self, *args: str, timeout: int = 30) -> subprocess.CompletedProcess[str]:
        cli = self._resolve_cli()
        try:
            return self._command_runner(
                [cli, *args],
                capture_output=True,
                text=True,
                check=False,
                timeout=timeout,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise RuntimeError(f"Apple container command failed: {exc}") from exc

    @staticmethod
    def _command_error(result: subprocess.CompletedProcess[str]) -> str:
        return result.stderr.strip() or result.stdout.strip() or "unknown Apple container error"

    @classmethod
    def _contains_internal_true(cls, value: Any) -> bool:
        if isinstance(value, dict):
            for key, child in value.items():
                if key.lower() in cls._internal_network_keys and child is True:
                    return True
                if key.lower() == "mode" and str(child).lower() in {"hostonly", "internal"}:
                    return True
                if cls._contains_internal_true(child):
                    return True
        elif isinstance(value, list):
            return any(cls._contains_internal_true(child) for child in value)
        return False

    def _ensure_internal_network(self) -> None:
        inspected = self._run("network", "inspect", self.network)
        if inspected.returncode == 0:
            try:
                payload = json.loads(inspected.stdout)
            except json.JSONDecodeError as exc:
                raise RuntimeError("Unable to verify that the Python sandbox network is internal") from exc
            if not self._contains_internal_true(payload):
                raise RuntimeError(
                    f"Network '{self.network}' exists but is not marked internal; refusing to use it"
                )
            return

        created = self._run(
            "network",
            "create",
            "--internal",
            "--label",
            "com.fruitspy.internal=true",
            self.network,
        )
        if created.returncode != 0:
            raise RuntimeError(
                f"Unable to create internal sandbox network: {self._command_error(created)}"
            )

    def preflight(self) -> None:
        image_result = self._run("image", "inspect", self.image, timeout=45)
        if image_result.returncode != 0:
            raise RuntimeError(
                f"Python sandbox image '{self.image}' is unavailable: {self._command_error(image_result)}"
            )
        self._ensure_internal_network()

        smoke = self.execute(
            execution_id=f"smoke-{secrets.token_hex(4)}",
            code='print("fruitspy-python-ready")',
            timeout_seconds=10,
        )
        if smoke.timed_out:
            raise RuntimeError("Python sandbox smoke test timed out")
        if smoke.returncode != 0 or smoke.stdout.strip() != "fruitspy-python-ready":
            detail = smoke.stderr.strip() or smoke.stdout.strip() or "unexpected smoke-test output"
            raise RuntimeError(f"Python sandbox smoke test failed: {detail}")

    @staticmethod
    def _artifact_script(
        code: str,
        artifact_specs: list[dict[str, str]],
        marker: str,
        max_artifact_bytes: int,
        max_artifact_total_bytes: int,
    ) -> str:
        encoded_source = base64.b64encode(code.encode("utf-8")).decode("ascii")
        encoded_specs = json.dumps(artifact_specs, ensure_ascii=True, separators=(",", ":"))
        return f'''import base64
import json
import pathlib
import sys
import traceback

_SOURCE = base64.b64decode({encoded_source!r}).decode("utf-8")
_SPECS = json.loads({encoded_specs!r})
_MARKER = {marker!r}
_MAX_ARTIFACT_BYTES = {max_artifact_bytes}
_MAX_ARTIFACT_TOTAL_BYTES = {max_artifact_total_bytes}
_exit_code = 0

try:
    exec(compile(_SOURCE, "<fruitspy>", "exec"), {{"__name__": "__main__", "__file__": "<fruitspy>"}})
except SystemExit as exc:
    if isinstance(exc.code, int):
        _exit_code = exc.code
    elif exc.code is not None:
        _exit_code = 1
except BaseException:
    traceback.print_exc()
    _exit_code = 1

_payload = {{"artifacts": [], "errors": []}}
_root = pathlib.Path("/tmp").resolve()
_total_bytes = 0
for _spec in _SPECS:
    _path_value = str(_spec.get("path", ""))
    _candidate = (_root / _path_value).resolve()
    if _candidate.parent != _root:
        _payload["errors"].append({{"path": _path_value, "error": "path_must_be_a_file_name_under_tmp"}})
        continue
    if not _candidate.is_file():
        _payload["errors"].append({{"path": _path_value, "error": "file_not_found"}})
        continue
    try:
        _data = _candidate.read_bytes()
    except OSError:
        _payload["errors"].append({{"path": _path_value, "error": "file_read_failed"}})
        continue
    if len(_data) > _MAX_ARTIFACT_BYTES:
        _payload["errors"].append({{"path": _path_value, "error": "artifact_too_large"}})
        continue
    if _total_bytes + len(_data) > _MAX_ARTIFACT_TOTAL_BYTES:
        _payload["errors"].append({{"path": _path_value, "error": "artifact_total_limit_exceeded"}})
        continue
    _total_bytes += len(_data)
    _payload["artifacts"].append({{
        "name": _path_value,
        "media_type": str(_spec.get("media_type", "application/octet-stream")),
        "data": base64.b64encode(_data).decode("ascii"),
    }})

print(_MARKER + base64.b64encode(json.dumps(_payload, separators=(",", ":")).encode("utf-8")).decode("ascii"))
sys.exit(_exit_code)
'''

    @staticmethod
    def _parse_artifact_output(
        result: SandboxExecution,
        marker: str,
    ) -> SandboxExecution:
        if result.timed_out or marker not in result.stdout:
            return result
        stdout, encoded_payload = result.stdout.rsplit(marker, 1)
        try:
            payload = json.loads(base64.b64decode(encoded_payload.strip()).decode("utf-8"))
            artifacts: dict[str, SandboxArtifact] = {}
            for item in payload.get("artifacts", []):
                name = str(item["name"])
                artifacts[name] = SandboxArtifact(
                    name=name,
                    media_type=str(item.get("media_type", "application/octet-stream")),
                    data=base64.b64decode(item["data"]),
                )
            errors = [
                {"path": str(item.get("path", "")), "error": str(item.get("error", "artifact_error"))}
                for item in payload.get("errors", [])
            ]
            return SandboxExecution(
                returncode=result.returncode,
                stdout=stdout,
                stderr=result.stderr,
                timed_out=result.timed_out,
                artifacts=artifacts,
                artifact_errors=errors,
            )
        except (ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
            return SandboxExecution(
                returncode=result.returncode,
                stdout=stdout,
                stderr=f"{result.stderr}\nFruitSpy artifact payload could not be decoded: {exc}",
                timed_out=result.timed_out,
            )

    def _command(self, execution_id: str) -> tuple[str, list[str]]:
        cli = self._resolve_cli()
        container_name = f"fruitspy-python-{execution_id.lower()}"
        cpu_count = (
            str(int(self.cpu_count))
            if float(self.cpu_count).is_integer()
            else str(self.cpu_count)
        )
        command = [
            cli,
            "run",
            "--rm",
            "--interactive",
            "--name",
            container_name,
            "--cpus",
            cpu_count,
            "--memory",
            f"{self.memory_mb}m",
            "--read-only",
            "--cap-drop",
            "ALL",
            "--user",
            self._user,
            "--network",
            self.network,
            "--no-dns",
            "--tmpfs",
            "/tmp",
            "--shm-size",
            "64m",
            "--ulimit",
            "nofile=256:256",
            "--label",
            "com.fruitspy.internal=true",
            "--label",
            f"com.fruitspy.execution={execution_id}",
            "--progress",
            "none",
            "--env",
            "PYTHONDONTWRITEBYTECODE=1",
            "--env",
            "MPLBACKEND=Agg",
            "--env",
            "HOME=/tmp",
            "--env",
            "MPLCONFIGDIR=/tmp/matplotlib",
            "--env",
            "XDG_CACHE_HOME=/tmp/.cache",
            self.image,
            "python",
            "-I",
            "-u",
            "-",
        ]
        return container_name, command

    @staticmethod
    def _run_process(command: list[str], code: str, timeout_seconds: float) -> SandboxExecution:
        try:
            process = subprocess.Popen(
                command,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
        except OSError as exc:
            raise RuntimeError(f"Unable to start Python sandbox: {exc}") from exc

        try:
            stdout, stderr = process.communicate(input=code, timeout=timeout_seconds)
            return SandboxExecution(process.returncode, stdout, stderr)
        except subprocess.TimeoutExpired:
            process.kill()
            stdout, stderr = process.communicate()
            return SandboxExecution(None, stdout, stderr, timed_out=True)

    def _force_cleanup(self, container_name: str) -> None:
        try:
            self._run("kill", container_name, timeout=10)
            self._run("delete", "--force", container_name, timeout=10)
        except RuntimeError:
            return

    def execute(
        self,
        execution_id: str,
        code: str,
        timeout_seconds: float,
        artifacts: Optional[list[dict[str, str]]] = None,
    ) -> SandboxExecution:
        container_name, command = self._command(execution_id)
        artifact_specs = artifacts or []
        marker = f"\n__FRUITSPY_ARTIFACTS_{secrets.token_hex(16)}__"
        input_code = (
            self._artifact_script(
                code,
                artifact_specs,
                marker,
                self.max_artifact_bytes,
                self.max_artifact_total_bytes,
            )
            if artifact_specs
            else code
        )
        try:
            result = self._process_runner(command, input_code, timeout_seconds)
        except Exception:
            self._force_cleanup(container_name)
            raise
        if result.timed_out:
            self._force_cleanup(container_name)
        return self._parse_artifact_output(result, marker) if artifact_specs else result


class PythonToolService:
    _cache_ttl_seconds = 600

    def __init__(
        self,
        *,
        runner: SandboxRunner,
        state_store: PythonToolStateStore,
        default_enabled: bool,
        token_configured: bool,
        timeout_seconds: int,
        max_output_chars: int,
        max_code_bytes: int,
        cpu_count: float,
        memory_mb: int,
        max_concurrency: int,
        max_artifacts: int = 4,
        max_artifact_bytes: int = 2 * 1024 * 1024,
        max_artifact_total_bytes: int = 4 * 1024 * 1024,
        artifact_ttl_seconds: int = 600,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.runner = runner
        self._state_store = state_store
        self._enabled = state_store.load_enabled(default_enabled)
        self._token_configured = token_configured
        self._timeout_seconds = timeout_seconds
        self._max_output_chars = max_output_chars
        self._max_code_bytes = max_code_bytes
        self._cpu_count = cpu_count
        self._memory_mb = memory_mb
        self._max_concurrency = max_concurrency
        self._max_artifacts = max_artifacts
        self._max_artifact_bytes = max_artifact_bytes
        self._max_artifact_total_bytes = max_artifact_total_bytes
        self._artifact_ttl_seconds = artifact_ttl_seconds
        self._clock = clock
        self._lock = threading.RLock()
        self._slots = threading.BoundedSemaphore(max_concurrency)
        self._state = "checking" if self._enabled else "disabled"
        self._error: Optional[str] = None
        self._running = 0
        self._last_execution: Optional[PythonToolLastExecution] = None
        self._inflight: set[str] = set()
        self._cache: dict[str, tuple[float, PythonExecutionResponse]] = {}
        self._artifact_cache: dict[str, tuple[float, dict[str, StoredArtifact]]] = {}

    def status(self) -> PythonToolStatus:
        with self._lock:
            return PythonToolStatus(
                enabled=self._enabled,
                state=self._state,
                ready=self._enabled and self._state in {"ready", "busy"},
                image=self.runner.image,
                limits=PythonToolLimits(
                    cpu_count=self._cpu_count,
                    memory_mb=self._memory_mb,
                    timeout_ms=self._timeout_seconds * 1000,
                    max_code_bytes=self._max_code_bytes,
                    max_output_chars=self._max_output_chars,
                    max_concurrency=self._max_concurrency,
                    max_artifacts=self._max_artifacts,
                    max_artifact_bytes=self._max_artifact_bytes,
                    max_artifact_total_bytes=self._max_artifact_total_bytes,
                    artifact_ttl_seconds=self._artifact_ttl_seconds,
                ),
                running_executions=self._running,
                last_execution=self._last_execution,
                error=self._error,
            )

    def initialize(self) -> None:
        with self._lock:
            enabled = self._enabled
        if enabled:
            self.set_enabled(True)

    def set_enabled(self, enabled: bool) -> PythonToolStatus:
        self._state_store.save_enabled(enabled)
        with self._lock:
            self._enabled = enabled
            self._error = None
            if not enabled:
                self._state = "disabling" if self._running else "disabled"
                return self.status()
            self._state = "checking"

        if not self._token_configured:
            with self._lock:
                self._state = "degraded"
                self._error = "FRUITSPY_PYTHON_TOOL_TOKEN is not configured"
                return self.status()

        try:
            self.runner.preflight()
        except RuntimeError as exc:
            with self._lock:
                self._state = "degraded"
                self._error = str(exc)
                return self.status()

        with self._lock:
            if self._enabled:
                self._state = "busy" if self._running else "ready"
            else:
                self._state = "disabling" if self._running else "disabled"
            return self.status()

    def _prune_cache(self, now: float) -> None:
        self._cache = {
            request_id: value
            for request_id, value in self._cache.items()
            if now - value[0] <= self._cache_ttl_seconds
        }
        self._artifact_cache = {
            execution_id: value
            for execution_id, value in self._artifact_cache.items()
            if value[0] > now
        }

    def _validate_artifact_requests(
        self,
        artifacts: list[dict[str, str]],
    ) -> list[dict[str, str]]:
        if len(artifacts) > self._max_artifacts:
            raise PythonToolValidationError(
                f"At most {self._max_artifacts} artifacts may be requested"
            )
        validated: list[dict[str, str]] = []
        seen: set[str] = set()
        path_pattern = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
        media_type_pattern = re.compile(r"^[A-Za-z0-9][A-Za-z0-9!#$&^_.+-]*/[A-Za-z0-9][A-Za-z0-9!#$&^_.+-]*$")
        for artifact in artifacts:
            path = str(artifact.get("path", ""))
            media_type = str(artifact.get("media_type", "application/octet-stream"))
            if (
                not path
                or path in {".", ".."}
                or Path(path).name != path
                or "\\" in path
                or not path_pattern.fullmatch(path)
                or path in seen
            ):
                raise PythonToolValidationError(
                    "Artifact path must be a unique file name directly under /tmp"
                )
            if not media_type_pattern.fullmatch(media_type):
                raise PythonToolValidationError(f"Invalid artifact media type: {media_type}")
            seen.add(path)
            validated.append({"path": path, "media_type": media_type})
        return validated

    @staticmethod
    def _truncate_streams(stdout: str, stderr: str, limit: int) -> tuple[str, str, bool, bool]:
        if len(stdout) + len(stderr) <= limit:
            return stdout, stderr, False, False

        if stdout and stderr:
            stdout_limit = min(len(stdout), limit // 2)
            stderr_limit = min(len(stderr), limit - stdout_limit)
            if stdout_limit < limit // 2:
                stderr_limit = min(len(stderr), limit - stdout_limit)
            elif stderr_limit < limit - stdout_limit:
                stdout_limit = min(len(stdout), limit - stderr_limit)
        elif stdout:
            stdout_limit, stderr_limit = limit, 0
        else:
            stdout_limit, stderr_limit = 0, limit

        return (
            stdout[:stdout_limit],
            stderr[:stderr_limit],
            len(stdout) > stdout_limit,
            len(stderr) > stderr_limit,
        )

    @staticmethod
    def _content(stdout: str, stderr: str, stdout_truncated: bool, stderr_truncated: bool) -> str:
        parts: list[str] = []
        if stdout:
            suffix = "\n... stdout truncated ..." if stdout_truncated else ""
            parts.append(f"stdout:\n{stdout}{suffix}")
        if stderr:
            suffix = "\n... stderr truncated ..." if stderr_truncated else ""
            parts.append(f"stderr:\n{stderr}{suffix}")
        return "\n\n".join(parts) or "No output."

    def execute(
        self,
        *,
        request_id: str,
        code: str,
        timeout_ms: Optional[int],
        artifacts: Optional[list[dict[str, str]]] = None,
    ) -> PythonExecutionResponse:
        code_bytes = len(code.encode("utf-8"))
        if code_bytes > self._max_code_bytes:
            raise PythonCodeTooLargeError(
                f"Python code exceeds the {self._max_code_bytes}-byte limit"
            )
        if not code.strip():
            raise PythonToolValidationError("No Python code provided")
        artifact_specs = self._validate_artifact_requests(artifacts or [])

        now = self._clock()
        with self._lock:
            self._prune_cache(now)
            cached = self._cache.get(request_id)
            if cached:
                return cached[1]
            if request_id in self._inflight:
                raise PythonToolRequestInProgressError("This request is already running")
            if not self._enabled:
                raise PythonToolDisabledError("Python Tool is disabled in FruitSpy")
            if self._state not in {"ready", "busy"}:
                raise PythonToolNotReadyError(self._error or "Python sandbox is not ready")
            self._inflight.add(request_id)

        acquired = self._slots.acquire(blocking=False)
        if not acquired:
            with self._lock:
                self._inflight.discard(request_id)
            raise PythonToolBusyError("Python sandbox concurrency limit reached")

        execution_id = f"py-{secrets.token_hex(8)}"
        effective_timeout_ms = min(
            timeout_ms if timeout_ms is not None else self._timeout_seconds * 1000,
            self._timeout_seconds * 1000,
        )
        started_at = self._clock()
        with self._lock:
            self._running += 1
            self._state = "busy"

        try:
            runner_kwargs: dict[str, Any] = {
                "execution_id": execution_id,
                "code": code,
                "timeout_seconds": effective_timeout_ms / 1000,
            }
            if artifact_specs:
                runner_kwargs["artifacts"] = artifact_specs
            execution = self.runner.execute(**runner_kwargs)
            duration_ms = max(0, round((self._clock() - started_at) * 1000))
            stdout, stderr, stdout_truncated, stderr_truncated = self._truncate_streams(
                execution.stdout,
                execution.stderr,
                self._max_output_chars,
            )
            status = "timed_out" if execution.timed_out else (
                "succeeded" if execution.returncode == 0 else "failed"
            )
            response = PythonExecutionResponse(
                request_id=request_id,
                execution_id=execution_id,
                ok=status == "succeeded",
                status=status,
                exit_code=execution.returncode,
                stdout=stdout,
                stderr=stderr,
                content=(
                    "Python sandbox timed out."
                    if execution.timed_out and not stdout and not stderr
                    else self._content(stdout, stderr, stdout_truncated, stderr_truncated)
                ),
                truncated=PythonExecutionTruncation(
                    stdout=stdout_truncated,
                    stderr=stderr_truncated,
                ),
                duration_ms=duration_ms,
                image=self.runner.image,
            )
            stored_artifacts: dict[str, StoredArtifact] = {}
            artifact_errors = list(execution.artifact_errors)
            requested_by_name = {item["path"]: item for item in artifact_specs}
            for name, artifact in execution.artifacts.items():
                requested = requested_by_name.get(name, {})
                stored_artifacts[name] = StoredArtifact(
                    name=name,
                    media_type=artifact.media_type or str(
                        requested.get("media_type", "application/octet-stream")
                    ),
                    data=artifact.data,
                    expires_at=self._clock() + self._artifact_ttl_seconds,
                )
                response.artifacts.append(
                    PythonArtifactResponse(
                        name=name,
                        media_type=stored_artifacts[name].media_type,
                        size_bytes=len(artifact.data),
                        sha256=hashlib.sha256(artifact.data).hexdigest(),
                        download_url=(
                            f"/api/v1/tools/python/executions/{execution_id}/artifacts/"
                            f"{quote(name, safe='')}"
                        ),
                    )
                )
            response.artifact_errors.extend(
                PythonArtifactError(path=item["path"], error=item["error"])
                for item in artifact_errors
            )
            with self._lock:
                self._last_execution = PythonToolLastExecution(
                    finished_at=datetime.now(timezone.utc),
                    status=status,
                    duration_ms=duration_ms,
                )
                self._cache[request_id] = (self._clock(), response)
                if stored_artifacts:
                    self._artifact_cache[execution_id] = (
                        self._clock() + self._artifact_ttl_seconds,
                        stored_artifacts,
                    )
            return response
        except RuntimeError as exc:
            with self._lock:
                self._error = str(exc)
                self._state = "degraded"
            raise PythonToolNotReadyError(str(exc)) from exc
        finally:
            with self._lock:
                self._running -= 1
                self._inflight.discard(request_id)
                if not self._enabled:
                    self._state = "disabled" if self._running == 0 else "disabling"
                elif self._error:
                    self._state = "degraded"
                else:
                    self._state = "busy" if self._running else "ready"
            self._slots.release()

    def get_artifact(self, execution_id: str, name: str) -> StoredArtifact:
        now = self._clock()
        with self._lock:
            self._prune_cache(now)
            cached = self._artifact_cache.get(execution_id)
            if not cached:
                raise PythonArtifactNotFoundError("Artifact has expired or does not exist")
            artifact = cached[1].get(name)
            if not artifact or artifact.expires_at <= now:
                raise PythonArtifactNotFoundError("Artifact has expired or does not exist")
            return artifact
