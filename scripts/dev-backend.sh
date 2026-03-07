#!/usr/bin/env zsh
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
BACKEND_DIR="$ROOT_DIR/backend"
VENV_DIR="$BACKEND_DIR/.venv"

PY_BIN="$(command -v python3.14 || command -v python3)"

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
exec uvicorn app.main:app --host 0.0.0.0 --port "${FRUITSPY_PORT:-8848}"
