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

CONTAINER_APP_ROOT="${FRUITSPY_APPLE_CONTAINER_APP_ROOT:-}"
if [[ -n "$CONTAINER_APP_ROOT" ]]; then
  export CONTAINER_APP_ROOT
fi

if [[ -n "$CONTAINER_APP_ROOT" ]]; then
  # launchd cannot reliably bootstrap a plist stored directly on /Volumes.
  # Keep the API plist on the system volume while its data root remains on the SSD.
  LAUNCHD_PLIST="${FRUITSPY_APPLE_CONTAINER_LAUNCHD_PLIST:-$HOME/Library/Application Support/FruitSpy/container-apiserver.plist}"
  mkdir -p "$(dirname "$LAUNCHD_PLIST")"
  if [[ -f "$CONTAINER_APP_ROOT/apiserver/apiserver.plist" ]]; then
    install -m 644 "$CONTAINER_APP_ROOT/apiserver/apiserver.plist" "$LAUNCHD_PLIST"
  fi

  SERVICE_DOMAIN="gui/$UID"
  if ! launchctl print "$SERVICE_DOMAIN/com.apple.container.apiserver" >/dev/null 2>&1; then
    launchctl bootstrap "$SERVICE_DOMAIN" "$LAUNCHD_PLIST" >/dev/null 2>&1 || true
  fi
else
  start_args=(system start)
  "$CONTAINER_BIN" "${start_args[@]}" >/dev/null 2>&1 || true
fi

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
