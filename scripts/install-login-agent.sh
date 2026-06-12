#!/usr/bin/env zsh
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
SOURCE_APP="$ROOT_DIR/dist/FruitSpy.app"
SOURCE_STARTUP="$ROOT_DIR/scripts/apple-container-startup.sh"
SOURCE_WORKLOAD_PLIST="$ROOT_DIR/launcher/com.fruitspy.apple-container-workloads.plist"
SOURCE_BACKEND_PLIST="$ROOT_DIR/launcher/com.fruitspy.backend.plist"

APP_DIR="$HOME/Applications/FruitSpy.app"
BIN_DIR="$HOME/Library/Application Support/FruitSpy/bin"
STARTUP_SCRIPT="$BIN_DIR/apple-container-startup.sh"
WORKLOAD_AGENT_PATH="$HOME/Library/LaunchAgents/com.fruitspy.apple-container-workloads.plist"
WORKLOAD_AGENT_LABEL="com.fruitspy.apple-container-workloads"
BACKEND_AGENT_PATH="$HOME/Library/LaunchAgents/com.fruitspy.backend.plist"
BACKEND_AGENT_LABEL="com.fruitspy.backend"
DOMAIN="gui/$UID"

unload_agent() {
  local label="$1"
  local path="$2"

  if ! launchctl print "$DOMAIN/$label" >/dev/null 2>&1; then
    return 0
  fi

  launchctl bootout "$DOMAIN/$label" >/dev/null 2>&1 \
    || launchctl bootout "$DOMAIN" "$path" >/dev/null 2>&1 \
    || true

  for _ in {1..50}; do
    if ! launchctl print "$DOMAIN/$label" >/dev/null 2>&1; then
      return 0
    fi
    /bin/sleep 0.1
  done

  echo "Unable to unload launch agent: $label" >&2
  return 1
}

load_agent() {
  local label="$1"
  local path="$2"

  for _ in {1..50}; do
    if launchctl print "$DOMAIN/$label" >/dev/null 2>&1; then
      return 0
    fi
    if launchctl bootstrap "$DOMAIN" "$path" >/dev/null 2>&1; then
      return 0
    fi
    /bin/sleep 0.1
  done

  echo "Unable to load launch agent: $label" >&2
  return 1
}

if [[ ! -d "$SOURCE_APP" ]]; then
  echo "FruitSpy.app is missing. Run scripts/build-app.sh and scripts/build-launcher.sh first." >&2
  exit 1
fi

mkdir -p "$HOME/Applications" "$BIN_DIR" "$HOME/Library/LaunchAgents"

reload_workload=false
reload_backend=false
if [[ ! -f "$WORKLOAD_AGENT_PATH" ]] \
  || ! /usr/bin/cmp -s "$SOURCE_WORKLOAD_PLIST" "$WORKLOAD_AGENT_PATH" \
  || ! launchctl print "$DOMAIN/$WORKLOAD_AGENT_LABEL" >/dev/null 2>&1; then
  reload_workload=true
  unload_agent "$WORKLOAD_AGENT_LABEL" "$WORKLOAD_AGENT_PATH"
fi
if [[ ! -f "$BACKEND_AGENT_PATH" ]] \
  || ! /usr/bin/cmp -s "$SOURCE_BACKEND_PLIST" "$BACKEND_AGENT_PATH" \
  || ! launchctl print "$DOMAIN/$BACKEND_AGENT_LABEL" >/dev/null 2>&1; then
  reload_backend=true
  unload_agent "$BACKEND_AGENT_LABEL" "$BACKEND_AGENT_PATH"
fi

rsync -a --delete "$SOURCE_APP/" "$APP_DIR/"
install -m 755 "$SOURCE_STARTUP" "$STARTUP_SCRIPT"
install -m 644 "$SOURCE_WORKLOAD_PLIST" "$WORKLOAD_AGENT_PATH"
install -m 644 "$SOURCE_BACKEND_PLIST" "$BACKEND_AGENT_PATH"

if [[ "$reload_workload" == true ]]; then
  load_agent "$WORKLOAD_AGENT_LABEL" "$WORKLOAD_AGENT_PATH"
fi
if [[ "$reload_backend" == true ]]; then
  load_agent "$BACKEND_AGENT_LABEL" "$BACKEND_AGENT_PATH"
fi
launchctl kickstart -k "$DOMAIN/$WORKLOAD_AGENT_LABEL"
launchctl kickstart -k "$DOMAIN/$BACKEND_AGENT_LABEL"

echo "Installed FruitSpy at $APP_DIR"
echo "Installed login agents $WORKLOAD_AGENT_LABEL and $BACKEND_AGENT_LABEL"
