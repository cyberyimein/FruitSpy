# FruitSpy

FruitSpy is a lightweight macOS host and Apple container dashboard for LAN use.

## What It Shows

- Host CPU, memory, and storage usage (updates on the configured refresh interval)
- Apple containers with status, live CPU usage, actual memory usage, and configured limits
- Installed host packages from npm, Homebrew, pip, and uv with search
- Per-container recent logs on demand
- Optional start, stop, and restart controls

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
- `FRUITSPY_CONTAINER_AUTO_START` (default `true`)
- `FRUITSPY_CONTAINER_CONTROL_ENABLED` (default `false`)
- `FRUITSPY_PORTAINER_URL` (optional; hidden when empty)
- `FRUITSPY_STORAGE_PATH` (default `/`)
- `FRUITSPY_LOG_LINES` (default `200`)

## Config Files

- `backend/env.json`: local private config (gitignored)
- `backend/env.temp.json`: safe template committed to repo

Optional keys in config JSON:

- `portainer_url`
- `apple_container_cli`
- `container_auto_start`
- `container_control_enabled`
- `storage_path`
- `log_lines`
- `refresh_seconds`

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

## Notes

- Apple container errors are isolated to the container panel; host metrics continue to work.
- The app is intended for trusted LAN environments without login in this version.
