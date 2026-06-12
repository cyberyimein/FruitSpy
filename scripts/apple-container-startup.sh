#!/usr/bin/env zsh
set -u

export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"

LOG_DIR="$HOME/Library/Logs/FruitSpy"
mkdir -p "$LOG_DIR"
exec >> "$LOG_DIR/apple-container-startup.log" 2>&1

echo "[$(date -Iseconds)] Starting Apple container workloads"

CONTAINER_BIN="${FRUITSPY_APPLE_CONTAINER_CLI:-$(command -v container 2>/dev/null || true)}"
if [[ -z "$CONTAINER_BIN" || ! -x "$CONTAINER_BIN" ]]; then
  echo "Apple container CLI not found"
  exit 0
fi

"$CONTAINER_BIN" system start >/dev/null 2>&1 || true

ready=false
for _ in {1..30}; do
  if "$CONTAINER_BIN" system status >/dev/null 2>&1; then
    ready=true
    break
  fi
  sleep 1
done

if [[ "$ready" != true ]]; then
  echo "Apple container system did not become ready"
  exit 1
fi

workloads=(${=FRUITSPY_APPLE_CONTAINER_WORKLOADS:-kabumemo-backend})
for workload in "${workloads[@]}"; do
  [[ -n "$workload" ]] || continue
  "$CONTAINER_BIN" start "$workload" >/dev/null 2>&1 || true
done

echo "[$(date -Iseconds)] Startup complete"
