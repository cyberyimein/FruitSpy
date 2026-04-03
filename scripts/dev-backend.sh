#!/usr/bin/env zsh
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
RUNTIME_DIR="${FRUITSPY_RUNTIME_DIR:-$ROOT_DIR/runtime}"

if [[ -d "$ROOT_DIR/backend" ]]; then
  BACKEND_DIR="$ROOT_DIR/backend"
  VENV_DIR="$BACKEND_DIR/.venv"
  CONFIG_PATH_DEFAULT="$BACKEND_DIR/env.json"
elif [[ -d "$ROOT_DIR/runtime/backend" ]]; then
  BACKEND_DIR="$ROOT_DIR/runtime/backend"
  STATE_BACKEND_DIR="$RUNTIME_DIR/backend"
  mkdir -p "$STATE_BACKEND_DIR"

  if [[ -f "$BACKEND_DIR/env.temp.json" && ! -f "$STATE_BACKEND_DIR/env.temp.json" ]]; then
    cp "$BACKEND_DIR/env.temp.json" "$STATE_BACKEND_DIR/env.temp.json"
  fi

  if [[ -f "$BACKEND_DIR/env.json" && ! -f "$STATE_BACKEND_DIR/env.json" ]]; then
    cp "$BACKEND_DIR/env.json" "$STATE_BACKEND_DIR/env.json"
  fi

  VENV_DIR="$STATE_BACKEND_DIR/.venv"
  CONFIG_PATH_DEFAULT="$STATE_BACKEND_DIR/env.json"
else
  echo "FruitSpy backend directory not found under $ROOT_DIR" >&2
  exit 1
fi

PY_BIN="$(command -v python3.14 || command -v python3)"

mkdir -p "$(dirname "$VENV_DIR")"

if [[ ! -d "$VENV_DIR" ]]; then
  "$PY_BIN" -m venv "$VENV_DIR"
fi

source "$VENV_DIR/bin/activate"

REQ_FILE="$BACKEND_DIR/requirements.txt"
STAMP_FILE="$VENV_DIR/.deps_installed"
if [[ ! -f "$STAMP_FILE" || "$REQ_FILE" -nt "$STAMP_FILE" ]]; then
  pip install -r "$REQ_FILE"
  touch "$STAMP_FILE"
fi

export PYTHONPATH="$BACKEND_DIR"
export FRUITSPY_CONFIG_PATH="${FRUITSPY_CONFIG_PATH:-$CONFIG_PATH_DEFAULT}"
export FRUITSPY_FRONTEND_DIST="${FRUITSPY_FRONTEND_DIST:-$BACKEND_DIR/frontend_dist}"
exec uvicorn app.main:app --host 0.0.0.0 --port "${FRUITSPY_PORT:-8848}"
