from __future__ import annotations

import shutil
import subprocess
from typing import Optional


def detect_docker_base_url(explicit_base_url: str = "") -> Optional[str]:
    if explicit_base_url:
        return explicit_base_url

    # Docker CLI knows active context host even when DOCKER_HOST is not exported.
    cmd = ["docker", "context", "inspect", "--format", "{{(index .Endpoints \"docker\").Host}}"]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    except OSError:
        return None

    if result.returncode != 0:
        return None

    host = result.stdout.strip()
    return host or None


def resolve_docker_cli() -> Optional[str]:
    direct = shutil.which("docker")
    if direct:
        return direct

    # Typical macOS paths when app processes inherit a restricted PATH.
    candidates = [
        "/opt/homebrew/bin/docker",
        "/usr/local/bin/docker",
        "/usr/bin/docker",
    ]
    for path in candidates:
        if shutil.which(path):
            return path
    return None
