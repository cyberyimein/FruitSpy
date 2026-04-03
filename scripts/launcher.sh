#!/usr/bin/env zsh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

if [[ -n "${FRUITSPY_ROOT:-}" ]]; then
  ROOT_DIR="$FRUITSPY_ROOT"
else
  ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
fi

if [[ "$SCRIPT_DIR" == *.app/Contents/Resources/scripts ]]; then
  DEFAULT_RUNTIME_DIR="$HOME/Library/Application Support/FruitSpy/runtime"
else
  DEFAULT_RUNTIME_DIR="$ROOT_DIR/runtime"
fi

RUNTIME_DIR="${FRUITSPY_RUNTIME_DIR:-$DEFAULT_RUNTIME_DIR}"

BACKEND_START_SCRIPT="$SCRIPT_DIR/dev-backend.sh"
if [[ ! -x "$BACKEND_START_SCRIPT" ]]; then
  BACKEND_START_SCRIPT="$ROOT_DIR/scripts/dev-backend.sh"
fi

PID_FILE="$RUNTIME_DIR/fruitspy.pid"
LOG_FILE="$RUNTIME_DIR/fruitspy.log"
PORT="${FRUITSPY_PORT:-8848}"
HEALTH_URL="http://localhost:$PORT/api/health"

mkdir -p "$RUNTIME_DIR"
export FRUITSPY_RUNTIME_DIR="$RUNTIME_DIR"

start_service() {
  if [[ -f "$PID_FILE" ]] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
    echo "already-running"
    return 0
  fi

  nohup "$BACKEND_START_SCRIPT" > "$LOG_FILE" 2>&1 &
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
