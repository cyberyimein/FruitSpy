# Apple Container Migration

This guide moves workloads from Colima to Apple container.

## Current Resource Model

Recorded on June 13, 2026 for Apple container 1.0.0:

- Apple container runs each application container in its own lightweight virtual machine.
- CPU and memory limits are configured per container with `--cpus` and `--memory`.
- Apple container does not currently provide one shared CPU/memory limit for all containers.
- Resource limits are ceilings, not reservations. FruitSpy reports live CPU usage and actual
  memory usage alongside each configured limit.
- The current `kabumemo-backend` container was created with 4 CPUs and 1 GiB of memory. Recreate
  it with `--cpus 2 --memory 2G` only when changing that existing configuration is intended.

## 1. Install And Verify

Install Apple container 1.0.0 with Homebrew, install the recommended kernel, then run:

```bash
brew install container
container system kernel set --recommended
container system start
container system version
```

The expected Apple silicon Homebrew CLI path is `/opt/homebrew/bin/container`.

Enable `container-runtime-linux` in System Settings > Privacy & Security > Local Network. If a
published port accepts connections and immediately resets them, restart the runtime after
enabling the permission:

```bash
container system stop
container system start
```

## 2. Prepare KabuMemo

Set the source and persistent-data paths for the local checkout:

```bash
export KABUMEMO_SOURCE_DIR="/path/to/kabumemo"
export KABUMEMO_DATA_DIR="$HOME/data/kabumemo"
```

The data directory should be a macOS bind mount so no Docker volume export is needed. Build the
image before stopping the old service:

```bash
cd "$KABUMEMO_SOURCE_DIR"
container build \
  --tag local/kabumemo-backend:latest \
  --file Dockerfile.server \
  .
```

Perform the cutover only when the service can briefly stop:

```bash
docker stop kabumemo-backend

container run --detach \
  --name kabumemo-backend \
  --cpus 2 \
  --memory 2G \
  --publish 9527:8000 \
  --env KABUCOUNT_DATA_DIR=/data \
  --env KABUMEMO_DIST_DIR=/frontend_dist \
  --volume "$KABUMEMO_DATA_DIR:/data" \
  local/kabumemo-backend:latest
```

Verify the service and its data:

```bash
curl -f http://127.0.0.1:9527/
container logs -n 100 kabumemo-backend
container stats --no-stream kabumemo-backend
```

## 3. Optional HanamiCli Migration

Build and create HanamiCli only if the service is still needed:

```bash
export HANAMI_SOURCE_DIR="/path/to/HanamiCli"
export HANAMI_DATA_DIR="$HANAMI_SOURCE_DIR/data"
cd "$HANAMI_SOURCE_DIR"
container build --tag local/hanamicli-app:latest --file Dockerfile .

container run --detach \
  --name hanamicli-app \
  --cpus 2 \
  --memory 2G \
  --publish 3333:3333 \
  --env-file .env \
  --volume "$HANAMI_DATA_DIR:/app/data" \
  local/hanamicli-app:latest
```

Run its bundled CLI inside the application container instead of creating a second Compose
service:

```bash
container exec hanamicli-app hanamicli --help
```

## 4. Retire Colima

After all required services have been verified, stop Colima and remove it separately if no
remaining workload needs it:

```bash
docker stop portainer
colima stop
```

Apple container 1.0 does not provide Docker Compose or Docker restart policies. FruitSpy can
show status and metrics, start, stop, restart, and read logs for Apple containers. Install the
included login agent to restore the Apple container system, KabuMemo, and FruitSpy after login:

```bash
cd /path/to/FruitSpy/scripts
./build-app.sh
./build-launcher.sh
./install-login-agent.sh
```
