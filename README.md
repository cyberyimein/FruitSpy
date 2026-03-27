# FruitSpy

FruitSpy is a lightweight macOS host and Docker runtime dashboard for LAN use.

## What It Shows

- Host CPU, memory, and storage usage (updates every second)
- Running Docker containers with CPU and memory usage (updates every second)
- Installed host packages from npm, Homebrew, pip, and uv with search
- Per-container recent logs on demand
- One-click jump to Portainer

## Architecture

- Backend: FastAPI + WebSocket (`backend/app`)
- Frontend: React + Vite (`frontend`)
- Launcher: macOS menu bar app (`launcher`)

The app is designed to run directly on the macOS host (not in Docker) so host metrics are accurate.

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
```

## One-click Release Package

```bash
cd scripts
./package-oneclick.sh
```

This creates `dist/FruitSpy-oneclick.zip` containing `FruitSpy.app`.

## Launcher Controls

The menu bar app provides:

- Start Service
- Stop Service
- Open Dashboard
- Quit

## Environment Variables

- `FRUITSPY_PORT` (default `8848`)
- `FRUITSPY_PORTAINER_URL` (default `http://localhost:9000`)
- `FRUITSPY_STORAGE_PATH` (default `/`)
- `FRUITSPY_LOG_LINES` (default `200`)

## Config Files

- `backend/env.json`: local private config (gitignored)
- `backend/env.temp.json`: safe template committed to repo

Current local default in `backend/env.json` can point Portainer to your LAN host, for example:

- `http://<your-host-ip>:9000`

Optional keys in config JSON:

- `portainer_url`
- `docker_base_url` (for example `unix:///Users/<user>/.docker/run/docker.sock`)
- `storage_path`
- `log_lines`
- `refresh_seconds`

## Notes

- Docker errors are isolated to the container panel; host metrics continue to work.
- The app is intended for trusted LAN environments without login in this version.
