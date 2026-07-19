from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict


@dataclass
class RuntimeConfig:
    apple_container_cli: str
    apple_container_app_root: str
    apple_container_launchd_plist: str
    container_auto_start: bool
    container_control_enabled: bool
    storage_path: str
    log_lines: int
    refresh_seconds: int
    python_tool_enabled: bool
    python_tool_token: str
    python_tool_allowed_cidrs: tuple[str, ...]
    python_sandbox_image: str
    python_sandbox_network: str
    python_sandbox_timeout_seconds: int
    python_sandbox_max_output_chars: int
    python_sandbox_max_code_bytes: int
    python_sandbox_cpu_count: float
    python_sandbox_memory_mb: int
    python_sandbox_max_concurrency: int
    python_sandbox_max_artifacts: int
    python_sandbox_max_artifact_bytes: int
    python_sandbox_max_artifact_total_bytes: int
    python_sandbox_artifact_ttl_seconds: int
    python_tool_state_path: str


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

    apple_container_cli = os.getenv(
        "FRUITSPY_APPLE_CONTAINER_CLI",
        str(config_data.get("apple_container_cli", "")),
    )
    apple_container_app_root = os.getenv(
        "FRUITSPY_APPLE_CONTAINER_APP_ROOT",
        str(config_data.get("apple_container_app_root", "")),
    )
    apple_container_launchd_plist = os.getenv(
        "FRUITSPY_APPLE_CONTAINER_LAUNCHD_PLIST",
        str(config_data.get("apple_container_launchd_plist", "")),
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

    python_tool_enabled = _bool_value(
        os.getenv("FRUITSPY_PYTHON_TOOL_ENABLED", config_data.get("python_tool_enabled", False)),
        False,
    )
    python_tool_token = os.getenv(
        "FRUITSPY_PYTHON_TOOL_TOKEN",
        str(config_data.get("python_tool_token", "")),
    ).strip()
    allowed_cidr_value = os.getenv(
        "FRUITSPY_PYTHON_TOOL_ALLOWED_CIDRS",
        config_data.get("python_tool_allowed_cidrs", ["192.168.64.0/24"]),
    )
    if isinstance(allowed_cidr_value, str):
        python_tool_allowed_cidrs = tuple(
            item.strip() for item in allowed_cidr_value.split(",") if item.strip()
        )
    elif isinstance(allowed_cidr_value, (list, tuple)):
        python_tool_allowed_cidrs = tuple(
            str(item).strip() for item in allowed_cidr_value if str(item).strip()
        )
    else:
        python_tool_allowed_cidrs = ("192.168.64.0/24",)
    if not python_tool_allowed_cidrs:
        python_tool_allowed_cidrs = ("192.168.64.0/24",)
    python_sandbox_image = os.getenv(
        "FRUITSPY_PYTHON_SANDBOX_IMAGE",
        str(config_data.get("python_sandbox_image", "anomalo-python:latest")),
    ).strip()
    python_sandbox_network = os.getenv(
        "FRUITSPY_PYTHON_SANDBOX_NETWORK",
        str(config_data.get("python_sandbox_network", "fruitspy-python-internal")),
    ).strip()

    def int_setting(env_name: str, config_name: str, default: int) -> int:
        try:
            return int(os.getenv(env_name, str(config_data.get(config_name, default))))
        except (TypeError, ValueError):
            return default

    try:
        python_sandbox_cpu_count = float(
            os.getenv(
                "FRUITSPY_PYTHON_SANDBOX_CPU_COUNT",
                str(config_data.get("python_sandbox_cpu_count", 1)),
            )
        )
    except (TypeError, ValueError):
        python_sandbox_cpu_count = 1.0

    runtime_dir = Path(os.getenv("FRUITSPY_RUNTIME_DIR", str(PROJECT_ROOT / "runtime")))
    python_tool_state_path = os.getenv(
        "FRUITSPY_PYTHON_TOOL_STATE_PATH",
        str(config_data.get("python_tool_state_path", runtime_dir / "state.json")),
    )

    return RuntimeConfig(
        apple_container_cli=apple_container_cli,
        apple_container_app_root=apple_container_app_root,
        apple_container_launchd_plist=apple_container_launchd_plist,
        container_auto_start=container_auto_start,
        container_control_enabled=container_control_enabled,
        storage_path=storage_path,
        log_lines=log_lines,
        refresh_seconds=max(refresh_seconds, 1),
        python_tool_enabled=python_tool_enabled,
        python_tool_token=python_tool_token,
        python_tool_allowed_cidrs=python_tool_allowed_cidrs,
        python_sandbox_image=python_sandbox_image or "anomalo-python:latest",
        python_sandbox_network=python_sandbox_network or "fruitspy-python-internal",
        python_sandbox_timeout_seconds=max(
            int_setting("FRUITSPY_PYTHON_SANDBOX_TIMEOUT_SECONDS", "python_sandbox_timeout_seconds", 10),
            1,
        ),
        python_sandbox_max_output_chars=max(
            int_setting("FRUITSPY_PYTHON_SANDBOX_MAX_OUTPUT_CHARS", "python_sandbox_max_output_chars", 12000),
            256,
        ),
        python_sandbox_max_code_bytes=max(
            int_setting("FRUITSPY_PYTHON_SANDBOX_MAX_CODE_BYTES", "python_sandbox_max_code_bytes", 65536),
            256,
        ),
        python_sandbox_cpu_count=max(python_sandbox_cpu_count, 0.1),
        python_sandbox_memory_mb=max(
            int_setting("FRUITSPY_PYTHON_SANDBOX_MEMORY_MB", "python_sandbox_memory_mb", 256),
            64,
        ),
        python_sandbox_max_concurrency=max(
            int_setting("FRUITSPY_PYTHON_SANDBOX_MAX_CONCURRENCY", "python_sandbox_max_concurrency", 1),
            1,
        ),
        python_sandbox_max_artifacts=max(
            int_setting("FRUITSPY_PYTHON_SANDBOX_MAX_ARTIFACTS", "python_sandbox_max_artifacts", 4),
            0,
        ),
        python_sandbox_max_artifact_bytes=max(
            int_setting(
                "FRUITSPY_PYTHON_SANDBOX_MAX_ARTIFACT_BYTES",
                "python_sandbox_max_artifact_bytes",
                2 * 1024 * 1024,
            ),
            1024,
        ),
        python_sandbox_max_artifact_total_bytes=max(
            int_setting(
                "FRUITSPY_PYTHON_SANDBOX_MAX_ARTIFACT_TOTAL_BYTES",
                "python_sandbox_max_artifact_total_bytes",
                4 * 1024 * 1024,
            ),
            1024,
        ),
        python_sandbox_artifact_ttl_seconds=max(
            int_setting(
                "FRUITSPY_PYTHON_SANDBOX_ARTIFACT_TTL_SECONDS",
                "python_sandbox_artifact_ttl_seconds",
                600,
            ),
            1,
        ),
        python_tool_state_path=python_tool_state_path,
    )
