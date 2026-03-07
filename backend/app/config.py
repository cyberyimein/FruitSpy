from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict


@dataclass
class RuntimeConfig:
    portainer_url: str
    docker_base_url: str
    storage_path: str
    log_lines: int
    refresh_seconds: int


PROJECT_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = PROJECT_ROOT / "backend"


def _load_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def load_runtime_config() -> RuntimeConfig:
    config_path = Path(os.getenv("FRUITSPY_CONFIG_PATH", str(BACKEND_ROOT / "env.json")))
    config_data = _load_json(config_path)
    if not config_data:
        config_data = _load_json(BACKEND_ROOT / "env.temp.json")

    portainer_url = os.getenv("FRUITSPY_PORTAINER_URL", str(config_data.get("portainer_url", "http://localhost:9000")))
    docker_base_url = os.getenv("FRUITSPY_DOCKER_BASE_URL", str(config_data.get("docker_base_url", "")))
    storage_path = os.getenv("FRUITSPY_STORAGE_PATH", str(config_data.get("storage_path", "/")))

    try:
        log_lines = int(os.getenv("FRUITSPY_LOG_LINES", str(config_data.get("log_lines", 200))))
    except ValueError:
        log_lines = 200

    try:
        refresh_seconds = int(os.getenv("FRUITSPY_REFRESH_SECONDS", str(config_data.get("refresh_seconds", 1))))
    except ValueError:
        refresh_seconds = 1

    return RuntimeConfig(
        portainer_url=portainer_url,
        docker_base_url=docker_base_url,
        storage_path=storage_path,
        log_lines=log_lines,
        refresh_seconds=max(refresh_seconds, 1),
    )
