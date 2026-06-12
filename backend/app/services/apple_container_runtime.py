from __future__ import annotations

import json
import re
import shutil
import subprocess
import threading
import time
from collections.abc import Callable
from typing import Any, Optional

from app.models.schemas import ContainerMetrics

CommandRunner = Callable[..., subprocess.CompletedProcess[str]]
Clock = Callable[[], float]


class AppleContainerRuntime:
    display_name = "Apple container"
    _container_id_pattern = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}")
    _internal_container_ids = {"buildkit"}

    def __init__(
        self,
        cli_path: str = "",
        auto_start: bool = True,
        runner: CommandRunner = subprocess.run,
        clock: Clock = time.monotonic,
    ) -> None:
        self._configured_cli_path = cli_path
        self._auto_start = auto_start
        self._runner = runner
        self._clock = clock
        self._lock = threading.RLock()
        self._cpu_samples: dict[str, tuple[float, float]] = {}

    def _resolve_cli(self) -> Optional[str]:
        if self._configured_cli_path:
            expanded = str(self._configured_cli_path)
            if "/" in expanded:
                return expanded if shutil.which(expanded) else None
            return shutil.which(expanded)

        direct = shutil.which("container")
        if direct:
            return direct

        for candidate in ("/usr/local/bin/container", "/opt/homebrew/bin/container"):
            if shutil.which(candidate):
                return candidate
        return None

    def _run(self, *args: str, timeout: int = 30) -> subprocess.CompletedProcess[str]:
        cli = self._resolve_cli()
        if not cli:
            raise RuntimeError(
                "Apple container CLI was not found. Install Apple container 1.0 or newer "
                "and ensure the container command is available on PATH."
            )

        try:
            return self._runner(
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

    @staticmethod
    def _items_from_json(text: str) -> list[dict[str, Any]]:
        payload = json.loads(text or "[]")
        if isinstance(payload, list):
            return [item for item in payload if isinstance(item, dict)]
        if isinstance(payload, dict):
            items = payload.get("items")
            if isinstance(items, list):
                return [item for item in items if isinstance(item, dict)]
            return [payload]
        return []

    @staticmethod
    def _number(payload: dict[str, Any], camel: str, snake: str) -> float:
        value = payload.get(camel, payload.get(snake, 0))
        try:
            return float(value or 0)
        except (TypeError, ValueError):
            return 0.0

    @staticmethod
    def _container_status(item: dict[str, Any]) -> str:
        status = item.get("status", "unknown")
        if isinstance(status, dict):
            return str(status.get("state", "unknown"))
        return str(status)

    @staticmethod
    def _configuration(item: dict[str, Any]) -> dict[str, Any]:
        configuration = item.get("configuration")
        return configuration if isinstance(configuration, dict) else item

    @classmethod
    def _container_id(cls, item: dict[str, Any]) -> str:
        configuration = cls._configuration(item)
        return str(item.get("id") or configuration.get("id", ""))

    @staticmethod
    def _is_internal_container(item: dict[str, Any]) -> bool:
        configuration = AppleContainerRuntime._configuration(item)
        labels = configuration.get("labels", {})
        if not isinstance(labels, dict):
            return False
        return (
            "com.apple.container.plugin" in labels
            or labels.get("com.apple.container.resource.role") == "builder"
        )

    @classmethod
    def _valid_container_id(cls, container_id: str) -> bool:
        return cls._container_id_pattern.fullmatch(container_id) is not None

    def _ensure_system_started(self) -> None:
        result = self._run("system", "start", timeout=60)
        if result.returncode != 0:
            raise RuntimeError(f"Unable to start Apple container services: {self._command_error(result)}")

    def _list_containers(self) -> list[dict[str, Any]]:
        result = self._run("list", "--all", "--format", "json")
        if result.returncode == 0:
            return self._items_from_json(result.stdout)

        if not self._auto_start:
            raise RuntimeError(self._command_error(result))

        self._ensure_system_started()
        retry = self._run("list", "--all", "--format", "json")
        if retry.returncode != 0:
            raise RuntimeError(self._command_error(retry))
        return self._items_from_json(retry.stdout)

    def _collect_stats(self) -> dict[str, dict[str, Any]]:
        result = self._run("stats", "--no-stream", "--format", "json", timeout=45)
        if result.returncode != 0:
            raise RuntimeError(self._command_error(result))
        return {
            str(item.get("id", "")): item
            for item in self._items_from_json(result.stdout)
            if item.get("id")
        }

    def _cpu_percent(self, container_id: str, cpu_usage_usec: float, sampled_at: float) -> float:
        previous = self._cpu_samples.get(container_id)
        self._cpu_samples[container_id] = (cpu_usage_usec, sampled_at)
        if not previous:
            return 0.0

        previous_usage, previous_at = previous
        elapsed = sampled_at - previous_at
        if elapsed <= 0 or cpu_usage_usec < previous_usage:
            return 0.0

        usage_delta_seconds = (cpu_usage_usec - previous_usage) / 1_000_000
        return round((usage_delta_seconds / elapsed) * 100.0, 1)

    def collect(self) -> tuple[list[ContainerMetrics], bool, Optional[str]]:
        with self._lock:
            try:
                raw_containers = self._list_containers()
                user_containers = [
                    item for item in raw_containers if not self._is_internal_container(item)
                ]
                running_ids = {
                    self._container_id(item)
                    for item in user_containers
                    if self._container_status(item) == "running"
                }
                running_ids.discard("")

                stats_by_id = self._collect_stats() if running_ids else {}
                sampled_at = self._clock()
                containers: list[ContainerMetrics] = []

                for item in user_containers:
                    configuration = self._configuration(item)

                    container_id = self._container_id(item)
                    if not container_id:
                        continue

                    status = self._container_status(item)
                    image_data = configuration.get("image", {})
                    image = (
                        str(image_data.get("reference", "unknown"))
                        if isinstance(image_data, dict)
                        else str(image_data or "unknown")
                    )
                    resources = configuration.get("resources", {})
                    if not isinstance(resources, dict):
                        resources = {}

                    stats = stats_by_id.get(container_id, {})
                    memory_used = self._number(stats, "memoryUsageBytes", "memory_usage_bytes")
                    memory_limit = self._number(stats, "memoryLimitBytes", "memory_limit_bytes")
                    if memory_limit <= 0:
                        memory_limit = self._number(resources, "memoryInBytes", "memory_in_bytes")

                    cpu_usage = self._number(stats, "cpuUsageUsec", "cpu_usage_usec")
                    cpu_percent = (
                        self._cpu_percent(container_id, cpu_usage, sampled_at)
                        if status == "running" and cpu_usage > 0
                        else 0.0
                    )
                    memory_percent = (memory_used / memory_limit * 100.0) if memory_limit > 0 else 0.0

                    containers.append(
                        ContainerMetrics(
                            id=container_id,
                            name=container_id,
                            image=image,
                            status=status,
                            cpu_percent=cpu_percent,
                            memory_percent=round(memory_percent, 1),
                            memory_used_mb=round(memory_used / (1024**2), 1),
                            memory_limit_mb=round(memory_limit / (1024**2), 1),
                        )
                    )

                active_ids = {container.id for container in containers if container.status == "running"}
                self._cpu_samples = {
                    container_id: sample
                    for container_id, sample in self._cpu_samples.items()
                    if container_id in active_ids
                }
                return containers, True, None
            except (RuntimeError, json.JSONDecodeError) as exc:
                return [], False, str(exc)

    def logs(self, container_id: str, lines: int = 200) -> dict[str, Any]:
        if not self._valid_container_id(container_id):
            return {"error": "invalid container ID"}
        if container_id in self._internal_container_ids:
            return {"error": "internal containers are not exposed by FruitSpy"}

        with self._lock:
            try:
                result = self._run("logs", "-n", str(lines), container_id)
            except RuntimeError as exc:
                return {"error": str(exc)}

            if result.returncode != 0:
                return {"error": self._command_error(result)}
            return {
                "container": container_id,
                "id": container_id,
                "lines": result.stdout.splitlines(),
            }

    def control(self, container_id: str, action: str) -> dict[str, Any]:
        if action not in {"start", "stop", "restart"}:
            raise ValueError(f"unsupported container action: {action}")
        if not self._valid_container_id(container_id):
            raise ValueError("invalid container ID")
        if container_id in self._internal_container_ids:
            raise ValueError("internal containers cannot be controlled")

        with self._lock:
            commands = [("stop", container_id), ("start", container_id)] if action == "restart" else [(action, container_id)]
            for command in commands:
                result = self._run(*command, timeout=60)
                if result.returncode != 0:
                    raise RuntimeError(self._command_error(result))
            return {"ok": True, "container": container_id, "action": action}
