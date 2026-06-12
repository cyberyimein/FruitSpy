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
BACKEND_AGENT_LABEL="com.fruitspy.backend"
BACKEND_AGENT_PATH="$HOME/Library/LaunchAgents/$BACKEND_AGENT_LABEL.plist"
BACKEND_AGENT_DOMAIN="gui/$UID"

mkdir -p "$RUNTIME_DIR"
export FRUITSPY_RUNTIME_DIR="$RUNTIME_DIR"

read_pid() {
  if [[ ! -f "$PID_FILE" ]]; then
    return 1
  fi

  local pid
  IFS= read -r pid < "$PID_FILE" || return 1
  if [[ ! "$pid" =~ '^[0-9]+$' ]]; then
    return 1
  fi
  echo "$pid"
}

pid_is_alive() {
  local pid="$1"
  kill -0 "$pid" 2>/dev/null
}

pid_matches_fruitspy_backend() {
  local pid="$1"
  local command
  command="$(ps -p "$pid" -o command= 2>/dev/null || true)"

  [[ "$command" == *"uvicorn"* ]] || return 1
  [[ "$command" == *"app.main:app"* ]] || return 1
  [[ "$command" == *"--port $PORT"* ]] || return 1
  [[ "$command" == *"$ROOT_DIR"* || "$command" == *"$RUNTIME_DIR"* ]]
}

mark_pid_stale() {
  if [[ ! -f "$PID_FILE" ]]; then
    return 0
  fi

  local stale_file
  stale_file="$PID_FILE.stale-$(date +%Y%m%d%H%M%S)-$$"
  mv "$PID_FILE" "$stale_file" 2>/dev/null || rm -f "$PID_FILE"
}

health_is_ready() {
  curl -fsS "$HEALTH_URL" >/dev/null 2>&1
}

launchd_backend_is_installed() {
  [[ -f "$BACKEND_AGENT_PATH" ]]
}

launchd_backend_is_loaded() {
  launchctl print "$BACKEND_AGENT_DOMAIN/$BACKEND_AGENT_LABEL" >/dev/null 2>&1
}

wait_for_service() {
  local pid="$1"
  local attempts=0
  local max_attempts=60

  until health_is_ready; do
    if [[ -n "$pid" ]] && ! pid_is_alive "$pid"; then
      return 2
    fi
    attempts=$((attempts + 1))
    if [[ "$attempts" -ge "$max_attempts" ]]; then
      return 3
    fi
    sleep 0.5
  done

  return 0
}

start_service() {
  local existing_pid
  if existing_pid="$(read_pid)"; then
    if pid_is_alive "$existing_pid" && pid_matches_fruitspy_backend "$existing_pid"; then
      wait_for_service "$existing_pid"
      case "$?" in
        0)
          echo "already-running"
          return 0
          ;;
        2)
          mark_pid_stale
          ;;
        3)
          echo "timeout"
          return 1
          ;;
      esac
    else
      mark_pid_stale
    fi
  elif [[ -f "$PID_FILE" ]]; then
    mark_pid_stale
  fi

  if health_is_ready; then
    echo "already-running"
    return 0
  fi

  if launchd_backend_is_installed; then
    if ! launchd_backend_is_loaded; then
      launchctl bootstrap "$BACKEND_AGENT_DOMAIN" "$BACKEND_AGENT_PATH"
    fi
    launchctl kickstart -k "$BACKEND_AGENT_DOMAIN/$BACKEND_AGENT_LABEL"

    wait_for_service ""
    case "$?" in
      0)
        echo "started"
        ;;
      3)
        echo "timeout"
        return 1
        ;;
    esac
    return 0
  fi

  nohup "$BACKEND_START_SCRIPT" > "$LOG_FILE" 2>&1 &
  local new_pid="$!"
  echo "$new_pid" > "$PID_FILE"

  wait_for_service "$new_pid"
  case "$?" in
    0)
      echo "started"
      ;;
    2)
      rm -f "$PID_FILE"
      echo "failed"
      return 1
      ;;
    3)
      echo "timeout"
      return 1
      ;;
  esac
}

stop_service() {
  if launchd_backend_is_loaded; then
    launchctl bootout "$BACKEND_AGENT_DOMAIN/$BACKEND_AGENT_LABEL"
    [[ -f "$PID_FILE" ]] && mark_pid_stale
    echo "stopped"
    return 0
  fi

  local pid
  if pid="$(read_pid)"; then
    if pid_is_alive "$pid" && pid_matches_fruitspy_backend "$pid"; then
      kill "$pid"
      rm -f "$PID_FILE"
    else
      mark_pid_stale
    fi
  elif [[ -f "$PID_FILE" ]]; then
    mark_pid_stale
  fi
  echo "stopped"
}

status_service() {
  local pid
  if pid="$(read_pid)"; then
    if pid_is_alive "$pid" && pid_matches_fruitspy_backend "$pid" && health_is_ready; then
      echo "running"
      return 0
    fi
    if ! pid_is_alive "$pid" || ! pid_matches_fruitspy_backend "$pid"; then
      mark_pid_stale
    fi
  elif [[ -f "$PID_FILE" ]]; then
    mark_pid_stale
  fi

  if health_is_ready; then
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
