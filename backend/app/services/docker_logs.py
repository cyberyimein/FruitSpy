from __future__ import annotations

import subprocess

import docker
from docker.errors import DockerException, NotFound

from app.services.docker_runtime import detect_docker_base_url, resolve_docker_cli


class DockerLogsService:
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

    def _tail_cli(self, container_id: str, lines: int = 200) -> dict:
        docker_cli = resolve_docker_cli()
        if not docker_cli:
            return {"error": "docker command not found"}

        cmd = [docker_cli, "logs", "--tail", str(lines), "--timestamps", container_id]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, check=False)
        except OSError:
            return {"error": "docker command execution failed"}
        if result.returncode != 0:
            return {"error": result.stderr.strip() or result.stdout.strip() or "docker logs failed"}
        return {
            "container": container_id,
            "id": container_id[:12],
            "lines": result.stdout.splitlines(),
        }

    def tail(self, container_id: str, lines: int = 200) -> dict:
        try:
            client = self._get_client()
            container = client.containers.get(container_id)
            raw = container.logs(tail=lines, timestamps=True)
            text = raw.decode("utf-8", errors="replace")
            return {
                "container": container.name,
                "id": container.id[:12],
                "lines": text.splitlines(),
            }
        except NotFound:
            return {"error": f"container not found: {container_id}"}
        except DockerException as exc:
            cli = self._tail_cli(container_id=container_id, lines=lines)
            if "error" not in cli:
                return cli
            return {
                "error": (
                    "Docker logs unavailable. Please ensure Docker Desktop is running and "
                    f"the context is valid. Raw error: {exc}"
                )
            }
