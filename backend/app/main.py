from __future__ import annotations

import asyncio
import os
import time
from pathlib import Path

from fastapi import FastAPI, Header, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api.python_tool import create_python_tool_router
from app.config import load_runtime_config
from app.models.schemas import PackageInventory, Snapshot
from app.services.apple_container_runtime import AppleContainerRuntime
from app.services.host_metrics import HostMetricsService
from app.services.package_inventory import PackageInventoryService
from app.services.python_tool import (
    ApplePythonSandboxRunner,
    PythonToolService,
    PythonToolStateStore,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = PROJECT_ROOT / "backend"


def resolve_frontend_dist() -> Path:
    override = os.getenv("FRUITSPY_FRONTEND_DIST")
    if override:
        return Path(override).expanduser().resolve()

    candidates = [
        BACKEND_ROOT / "frontend_dist",
        PROJECT_ROOT / "frontend_dist",
    ]
    for path in candidates:
        if (path / "index.html").exists():
            return path
    return candidates[0]


FRONTEND_DIST = resolve_frontend_dist()
RUNTIME_CONFIG = load_runtime_config()

host_service = HostMetricsService(storage_path=RUNTIME_CONFIG.storage_path)
container_service = AppleContainerRuntime(
    cli_path=RUNTIME_CONFIG.apple_container_cli,
    app_root=RUNTIME_CONFIG.apple_container_app_root,
    launchd_plist=RUNTIME_CONFIG.apple_container_launchd_plist,
    auto_start=RUNTIME_CONFIG.container_auto_start,
)
package_inventory_service = PackageInventoryService()
python_sandbox_runner = ApplePythonSandboxRunner(
    image=RUNTIME_CONFIG.python_sandbox_image,
    network=RUNTIME_CONFIG.python_sandbox_network,
    cpu_count=RUNTIME_CONFIG.python_sandbox_cpu_count,
    memory_mb=RUNTIME_CONFIG.python_sandbox_memory_mb,
    max_artifact_bytes=RUNTIME_CONFIG.python_sandbox_max_artifact_bytes,
    max_artifact_total_bytes=RUNTIME_CONFIG.python_sandbox_max_artifact_total_bytes,
    cli_path=RUNTIME_CONFIG.apple_container_cli,
)
python_tool_service = PythonToolService(
    runner=python_sandbox_runner,
    state_store=PythonToolStateStore(RUNTIME_CONFIG.python_tool_state_path),
    default_enabled=RUNTIME_CONFIG.python_tool_enabled,
    token_configured=bool(RUNTIME_CONFIG.python_tool_token),
    timeout_seconds=RUNTIME_CONFIG.python_sandbox_timeout_seconds,
    max_output_chars=RUNTIME_CONFIG.python_sandbox_max_output_chars,
    max_code_bytes=RUNTIME_CONFIG.python_sandbox_max_code_bytes,
    cpu_count=RUNTIME_CONFIG.python_sandbox_cpu_count,
    memory_mb=RUNTIME_CONFIG.python_sandbox_memory_mb,
    max_concurrency=RUNTIME_CONFIG.python_sandbox_max_concurrency,
    max_artifacts=RUNTIME_CONFIG.python_sandbox_max_artifacts,
    max_artifact_bytes=RUNTIME_CONFIG.python_sandbox_max_artifact_bytes,
    max_artifact_total_bytes=RUNTIME_CONFIG.python_sandbox_max_artifact_total_bytes,
    artifact_ttl_seconds=RUNTIME_CONFIG.python_sandbox_artifact_ttl_seconds,
)

app = FastAPI(title="FruitSpy")
app.include_router(
    create_python_tool_router(
        service=python_tool_service,
        token=RUNTIME_CONFIG.python_tool_token,
        allowed_cidrs=RUNTIME_CONFIG.python_tool_allowed_cidrs,
    )
)


@app.on_event("startup")
async def initialize_python_tool() -> None:
    await asyncio.to_thread(python_tool_service.initialize)


def collect_snapshot() -> Snapshot:
    host = host_service.collect()
    containers, runtime_available, runtime_error = container_service.collect()
    return Snapshot(
        timestamp=time.time(),
        host=host,
        containers=containers,
        runtime_name=container_service.display_name,
        runtime_available=runtime_available,
        runtime_error=runtime_error,
    )


@app.get("/api/health")
def health() -> dict:
    return {"ok": True, "time": time.time()}


@app.get("/api/config")
def config() -> dict:
    return {
        "runtime_name": container_service.display_name,
        "container_control_enabled": RUNTIME_CONFIG.container_control_enabled,
        "refresh_seconds": RUNTIME_CONFIG.refresh_seconds,
        "logs_tail_default": RUNTIME_CONFIG.log_lines,
    }


@app.get("/api/snapshot")
def snapshot() -> Snapshot:
    return collect_snapshot()


@app.get("/api/logs/{container_id}")
def container_logs(
    container_id: str,
    tail: int = Query(default=RUNTIME_CONFIG.log_lines, ge=20, le=1000),
) -> dict:
    return container_service.logs(container_id=container_id, lines=tail)


@app.post("/api/containers/{container_id}/{action}")
def control_container(
    container_id: str,
    action: str,
    x_fruitspy_control: str = Header(default=""),
) -> dict:
    if not RUNTIME_CONFIG.container_control_enabled:
        raise HTTPException(status_code=403, detail="Container controls are disabled")
    if x_fruitspy_control != "1":
        raise HTTPException(status_code=403, detail="Missing FruitSpy control header")
    try:
        return container_service.control(container_id=container_id, action=action)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.get("/api/packages")
def package_inventory() -> PackageInventory:
    return package_inventory_service.collect()


@app.websocket("/ws/dashboard")
async def ws_dashboard(ws: WebSocket) -> None:
    await ws.accept()
    try:
        while True:
            started_at = time.monotonic()
            payload = (await asyncio.to_thread(collect_snapshot)).model_dump()
            await ws.send_json(payload)
            elapsed = time.monotonic() - started_at
            await asyncio.sleep(max(RUNTIME_CONFIG.refresh_seconds - elapsed, 0.1))
    except WebSocketDisconnect:
        return


if FRONTEND_DIST.exists():
    app.mount("/assets", StaticFiles(directory=str(FRONTEND_DIST / "assets")), name="assets")


@app.get("/favicon.svg")
def favicon_svg():
    icon_path = FRONTEND_DIST / "favicon.svg"
    if icon_path.exists():
        return FileResponse(icon_path)
    return {"message": "favicon not found"}


@app.get("/favicon.ico")
def favicon_ico():
    icon_path = FRONTEND_DIST / "favicon.ico"
    if icon_path.exists():
        return FileResponse(icon_path)
    # Fall back to svg if ico is not provided.
    svg_path = FRONTEND_DIST / "favicon.svg"
    if svg_path.exists():
        return FileResponse(svg_path)
    return {"message": "favicon not found"}


@app.get("/apple-touch-icon.png")
def apple_touch_icon():
    icon_path = FRONTEND_DIST / "apple-touch-icon.png"
    if icon_path.exists():
        return FileResponse(icon_path)
    svg_path = FRONTEND_DIST / "favicon.svg"
    if svg_path.exists():
        return FileResponse(svg_path)
    return {"message": "icon not found"}


@app.get("/{full_path:path}")
def spa_entry(full_path: str):
    index_html = FRONTEND_DIST / "index.html"
    if index_html.exists():
        return FileResponse(index_html)
    return {
        "message": "Frontend build not found. Run scripts/build-app.sh first.",
        "requested": full_path,
    }
