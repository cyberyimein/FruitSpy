# FruitSpy

FruitSpy is a lightweight macOS host and Apple container dashboard for LAN use.

## What It Shows

- Host CPU, memory, and storage usage (updates on the configured refresh interval)
- Apple containers with status, live CPU usage, actual memory usage, and configured limits
- Installed host packages from npm, Homebrew, pip, and uv with search
- Per-container recent logs on demand
- Optional start, stop, and restart controls
- A local Python Tool relay that executes Anomalo requests from loopback or an allowlisted container network
- Optional short-lived `/tmp` artifact downloads for plots and small result files

## Architecture

- Backend: FastAPI + WebSocket (`backend/app`)
- Frontend: React + Vite (`frontend`)
- Launcher: macOS menu bar app (`launcher`)

The app is designed to run directly on the macOS host (not in Docker) so host metrics are accurate.

## Runtime Requirements

- Apple silicon Mac
- macOS 26 or newer
- [Apple container](https://github.com/apple/container) 1.0 or newer

Install Apple container with Homebrew, then install its recommended Linux kernel and start it:

```bash
brew install container
container system kernel set --recommended
container system start
container system version
```

FruitSpy can automatically start the Apple container system service when the CLI is installed.
On first use, allow `container-runtime-linux` under System Settings > Privacy & Security >
Local Network. Published ports can accept and then reset connections until the runtime is
restarted after this permission is enabled.

## Quick Start (Dev)

```bash
cd frontend && npm install && npm run build
cd ../scripts && chmod +x dev-backend.sh launcher.sh build-app.sh build-launcher.sh
./dev-backend.sh
```

Open `http://localhost:8848`.

## Build Launcher App

```bash
cd scripts
./build-launcher.sh
```

This creates `dist/FruitSpy.app`.

Double-click `dist/FruitSpy.app` to one-click start service and open dashboard.

## Full Build Pipeline

```bash
cd scripts
./build-app.sh
./build-launcher.sh
./install-login-agent.sh
```

The login agents install FruitSpy under `~/Applications`, start the Apple container system,
restore `kabumemo-backend`, and keep the FruitSpy backend running after login.

## One-click Release Package

```bash
cd scripts
./package-oneclick.sh
```

This creates `dist/FruitSpy-oneclick.zip` containing a self-contained `FruitSpy.app` bundle.

On first launch, the packaged app creates its writable runtime state under `~/Library/Application Support/FruitSpy/runtime`.
The launcher no longer depends on the repository checkout, but it still expects a local `python3` installation so it can create an isolated virtual environment.

## Launcher Controls

The menu bar app provides:

- Start Service
- Stop Service
- Open Dashboard
- Quit

## Environment Variables

- `FRUITSPY_PORT` (default `8848`)
- `FRUITSPY_APPLE_CONTAINER_CLI` (optional explicit CLI path)
- `FRUITSPY_APPLE_CONTAINER_APP_ROOT` (optional Apple container application-data root)
- `FRUITSPY_APPLE_CONTAINER_LAUNCHD_PLIST` (optional system-volume API launchd plist path)
- `FRUITSPY_CONTAINER_AUTO_START` (default `true`)
- `FRUITSPY_CONTAINER_CONTROL_ENABLED` (default `false`)
- `FRUITSPY_STORAGE_PATH` (default `/`)
- `FRUITSPY_LOG_LINES` (default `200`)
- `FRUITSPY_PYTHON_TOOL_ENABLED` (default `false`)
- `FRUITSPY_PYTHON_TOOL_TOKEN` (required before Python Tool can become ready)
- `FRUITSPY_PYTHON_TOOL_ALLOWED_CIDRS` (default `192.168.64.0/24`; comma-separated; loopback is always allowed)
- `FRUITSPY_PYTHON_SANDBOX_IMAGE` (default `anomalo-python:latest`)
- `FRUITSPY_PYTHON_SANDBOX_NETWORK` (default `fruitspy-python-internal`)
- `FRUITSPY_PYTHON_SANDBOX_TIMEOUT_SECONDS` (default `10`)
- `FRUITSPY_PYTHON_SANDBOX_MAX_OUTPUT_CHARS` (default `12000`)
- `FRUITSPY_PYTHON_SANDBOX_MAX_CODE_BYTES` (default `65536`)
- `FRUITSPY_PYTHON_SANDBOX_CPU_COUNT` (default `1`)
- `FRUITSPY_PYTHON_SANDBOX_MEMORY_MB` (default `256`)
- `FRUITSPY_PYTHON_SANDBOX_MAX_CONCURRENCY` (default `1`)
- `FRUITSPY_PYTHON_SANDBOX_MAX_ARTIFACTS` (default `4`)
- `FRUITSPY_PYTHON_SANDBOX_MAX_ARTIFACT_BYTES` (default `2097152`)
- `FRUITSPY_PYTHON_SANDBOX_MAX_ARTIFACT_TOTAL_BYTES` (default `4194304`)
- `FRUITSPY_PYTHON_SANDBOX_ARTIFACT_TTL_SECONDS` (default `600`)

## Config Files

- `backend/env.json`: local private config (gitignored)
- `backend/env.temp.json`: safe template committed to repo

Optional keys in config JSON:

- `apple_container_cli`
- `apple_container_app_root`
- `apple_container_launchd_plist`
- `container_auto_start`
- `container_control_enabled`
- `storage_path`
- `log_lines`
- `refresh_seconds`
- `python_tool_enabled`
- `python_tool_token`
- `python_tool_allowed_cidrs` (default `192.168.64.0/24`; loopback is always allowed)
- `python_sandbox_image`
- `python_sandbox_network`
- `python_sandbox_timeout_seconds`
- `python_sandbox_max_output_chars`
- `python_sandbox_max_code_bytes`
- `python_sandbox_cpu_count`
- `python_sandbox_memory_mb`
- `python_sandbox_max_concurrency`

Container controls are disabled in the committed template because FruitSpy currently has no
authentication and listens on the LAN. Enable them only on a trusted network. Control requests
are same-origin and require a FruitSpy-specific header to reduce cross-site request risk.

## Moving Off Colima

Apple container does not import Colima's Docker state. Recreate each workload with the Apple
`container build`, `container create`, or `container run` commands, and copy persistent data
before stopping Colima. Host bind mounts are the simplest migration path because the data
remains directly accessible from macOS.

FruitSpy itself no longer requires Docker Engine, the Docker socket, Docker Compose, or Portainer.
See [docs/apple-container-migration.md](docs/apple-container-migration.md) for the migration
commands for example workloads.

## Python Tool Relay

The API page contains a Python Tool card. When enabled, it accepts authenticated requests from
Anomalo on the same Mac, starts a fresh Apple container for each request, captures stdout/stderr,
then removes the container. The execution endpoint accepts loopback and the explicitly configured
`python_tool_allowed_cidrs` networks; the dashboard itself remains available on the LAN.

Build the sandbox image in Apple container's image store and configure the same random token in
FruitSpy and Anomalo before enabling the card. See
[docs/python-tool-api.md](docs/python-tool-api.md) for setup and protocol details.

## Notes

- Apple container errors are isolated to the container panel; host metrics continue to work.
- The app is intended for trusted LAN environments without login in this version.
