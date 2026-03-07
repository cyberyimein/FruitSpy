#!/usr/bin/env zsh
set -euo pipefail

if [[ -n "${FRUITSPY_ROOT:-}" ]]; then
  ROOT_DIR="$FRUITSPY_ROOT"
else
  ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
fi
PID_FILE="$ROOT_DIR/runtime/fruitspy.pid"
LOG_FILE="$ROOT_DIR/runtime/fruitspy.log"
PORT="${FRUITSPY_PORT:-8848}"
HEALTH_URL="http://localhost:$PORT/api/health"

mkdir -p "$ROOT_DIR/runtime"

start_service() {
  if [[ -f "$PID_FILE" ]] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
    echo "already-running"
    return 0
  fi

  nohup "$ROOT_DIR/scripts/dev-backend.sh" > "$LOG_FILE" 2>&1 &
  echo "$!" > "$PID_FILE"

  local attempts=0
  local max_attempts=60
  until curl -fsS "$HEALTH_URL" >/dev/null 2>&1; do
    if ! kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
      echo "failed"
      return 1
    fi
    attempts=$((attempts + 1))
    if [[ "$attempts" -ge "$max_attempts" ]]; then
      echo "timeout"
      return 1
    fi
    sleep 0.5
  done

  echo "started"
}

stop_service() {
  if [[ -f "$PID_FILE" ]]; then
    PID="$(cat "$PID_FILE")"
    if kill -0 "$PID" 2>/dev/null; then
      kill "$PID"
    fi
    rm -f "$PID_FILE"
  fi
  echo "stopped"
}

status_service() {
  if [[ -f "$PID_FILE" ]] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
    echo "running"
  else
    echo "stopped"
  fi
}

open_panel() {
  open "http://localhost:$PORT"
}

case "${1:-}" in
  start)
    start_service
    ;;
  stop)
    stop_service
    ;;
  status)
    status_service
    ;;
  open)
    open_panel
    ;;
  *)
    echo "usage: launcher.sh {start|stop|status|open}"
    exit 1
    ;;
esac
