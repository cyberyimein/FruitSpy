from __future__ import annotations

import json
import re
import subprocess
from typing import Any, List, Optional, Tuple

import docker
from docker.errors import DockerException

from app.models.schemas import ContainerMetrics
from app.services.docker_runtime import detect_docker_base_url, resolve_docker_cli


class DockerMetricsService:
    def __init__(self, base_url: str = "") -> None:
        self._client = None
        self._base_url = base_url

    def _get_client(self):
        if self._client is None:
            detected_base_url = detect_docker_base_url(self._base_url)
            if detected_base_url:
                self._client = docker.DockerClient(base_url=detected_base_url)
            else:
                self._client = docker.from_env()
        return self._client

    @staticmethod
    def _to_mb(value: float, unit: str) -> float:
        unit_upper = unit.upper()
        factor_map = {
            "B": 1 / (1024**2),
            "KB": 1 / 1024,
            "KIB": 1 / 1024,
            "MB": 1,
            "MIB": 1,
            "GB": 1024,
            "GIB": 1024,
            "TB": 1024 * 1024,
            "TIB": 1024 * 1024,
        }
        return value * factor_map.get(unit_upper, 1)

    def _parse_size_to_mb(self, token: str) -> float:
        match = re.match(r"^\s*([0-9]+(?:\.[0-9]+)?)\s*([A-Za-z]+)\s*$", token)
        if not match:
            return 0.0
        value = float(match.group(1))
        unit = match.group(2)
        return round(self._to_mb(value, unit), 1)

    def _collect_running_cli(self) -> Optional[List[ContainerMetrics]]:
        docker_cli = resolve_docker_cli()
        if not docker_cli:
            return None

        stats_cmd = [docker_cli, "stats", "--no-stream", "--format", "{{json .}}"]
        ps_cmd = [docker_cli, "ps", "--format", "{{.ID}}\t{{.Image}}\t{{.Status}}\t{{.Names}}"]

        try:
            stats_result = subprocess.run(stats_cmd, capture_output=True, text=True, check=False)
            ps_result = subprocess.run(ps_cmd, capture_output=True, text=True, check=False)
        except OSError:
            return None

        if stats_result.returncode != 0 or ps_result.returncode != 0:
            return None

        meta_by_id: dict[str, tuple[str, str, str]] = {}
        for line in ps_result.stdout.splitlines():
            parts = line.split("\t")
            if len(parts) != 4:
                continue
            cid, image, status, name = parts
            meta_by_id[cid[:12]] = (image, status, name)

        containers: List[ContainerMetrics] = []
        for line in stats_result.stdout.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                raw = json.loads(line)
            except json.JSONDecodeError:
                continue

            cid = str(raw.get("ID", ""))[:12]
            if not cid:
                continue

            image, status, name = meta_by_id.get(cid, ("unknown", "running", str(raw.get("Name", cid))))

            cpu_percent = float(str(raw.get("CPUPerc", "0")).replace("%", "") or 0)
            mem_percent = float(str(raw.get("MemPerc", "0")).replace("%", "") or 0)

            mem_usage = str(raw.get("MemUsage", "0MiB / 0MiB"))
            usage_parts = mem_usage.split("/")
            used_mb = self._parse_size_to_mb(usage_parts[0]) if usage_parts else 0.0
            limit_mb = self._parse_size_to_mb(usage_parts[1]) if len(usage_parts) > 1 else 0.0

            containers.append(
                ContainerMetrics(
                    id=cid,
                    name=name,
                    image=image,
                    status=status,
                    cpu_percent=round(cpu_percent, 1),
                    memory_percent=round(mem_percent, 1),
                    memory_used_mb=used_mb,
                    memory_limit_mb=limit_mb,
                )
            )

        return containers

    @staticmethod
    def _safe_div(numerator: float, denominator: float) -> float:
        if denominator <= 0:
            return 0.0
        return numerator / denominator

    def _calc_cpu_percent(self, stats: dict[str, Any]) -> float:
        cpu_stats = stats.get("cpu_stats", {})
        prev_stats = stats.get("precpu_stats", {})

        current_total = cpu_stats.get("cpu_usage", {}).get("total_usage", 0)
        prev_total = prev_stats.get("cpu_usage", {}).get("total_usage", 0)

        current_system = cpu_stats.get("system_cpu_usage", 0)
        prev_system = prev_stats.get("system_cpu_usage", 0)

        total_delta = current_total - prev_total
        system_delta = current_system - prev_system

        online_cpus = cpu_stats.get("online_cpus")
        if not online_cpus:
            percpu = cpu_stats.get("cpu_usage", {}).get("percpu_usage") or []
            online_cpus = max(len(percpu), 1)

        percent = self._safe_div(total_delta, system_delta) * online_cpus * 100.0
        return round(max(percent, 0.0), 1)

    def _calc_mem(self, stats: dict[str, Any]) -> tuple[float, float, float]:
        memory_stats = stats.get("memory_stats", {})
        usage = float(memory_stats.get("usage", 0))
        limit = float(memory_stats.get("limit", 0))

        percent = self._safe_div(usage, limit) * 100.0
        usage_mb = usage / (1024**2)
        limit_mb = limit / (1024**2)

        return round(percent, 1), round(usage_mb, 1), round(limit_mb, 1)

    def collect_running(self) -> Tuple[List[ContainerMetrics], bool, Optional[str]]:
        try:
            client = self._get_client()
            containers = client.containers.list(filters={"status": "running"})

            result: list[ContainerMetrics] = []
            for container in containers:
                stats = container.stats(stream=False)
                cpu_percent = self._calc_cpu_percent(stats)
                mem_percent, mem_used_mb, mem_limit_mb = self._calc_mem(stats)

                result.append(
                    ContainerMetrics(
                        id=container.id[:12],
                        name=(container.name or container.id[:12]),
                        image=(container.image.tags[0] if container.image.tags else container.image.short_id),
                        status=container.status or "unknown",
                        cpu_percent=cpu_percent,
                        memory_percent=mem_percent,
                        memory_used_mb=mem_used_mb,
                        memory_limit_mb=mem_limit_mb,
                    )
                )

            return result, True, None
        except DockerException as exc:
            cli_fallback = self._collect_running_cli()
            if cli_fallback is not None:
                return cli_fallback, True, None

            message = (
                "Docker daemon unreachable. Please ensure Docker Desktop is running "
                "and the active Docker context is available. "
                f"Raw error: {exc}"
            )
            return [], False, message
