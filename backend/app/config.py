from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict


@dataclass
class RuntimeConfig:
    portainer_url: str
    apple_container_cli: str
    container_auto_start: bool
    container_control_enabled: bool
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


def _bool_value(value: Any, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "on"}:
            return True
        if normalized in {"0", "false", "no", "off"}:
            return False
    return default


def load_runtime_config() -> RuntimeConfig:
    config_path = Path(os.getenv("FRUITSPY_CONFIG_PATH", str(BACKEND_ROOT / "env.json")))
    config_data = _load_json(config_path)
    if not config_data:
        config_data = _load_json(BACKEND_ROOT / "env.temp.json")

    portainer_url = os.getenv("FRUITSPY_PORTAINER_URL", str(config_data.get("portainer_url", "")))
    apple_container_cli = os.getenv(
        "FRUITSPY_APPLE_CONTAINER_CLI",
        str(config_data.get("apple_container_cli", "")),
    )
    container_auto_start = _bool_value(
        os.getenv("FRUITSPY_CONTAINER_AUTO_START", config_data.get("container_auto_start", True)),
        True,
    )
    container_control_enabled = _bool_value(
        os.getenv(
            "FRUITSPY_CONTAINER_CONTROL_ENABLED",
            config_data.get("container_control_enabled", False),
        ),
        False,
    )
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
        apple_container_cli=apple_container_cli,
        container_auto_start=container_auto_start,
        container_control_enabled=container_control_enabled,
        storage_path=storage_path,
        log_lines=log_lines,
        refresh_seconds=max(refresh_seconds, 1),
    )
