#!/usr/bin/env zsh
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
FRONTEND_DIR="$ROOT_DIR/frontend"
BACKEND_DIR="$ROOT_DIR/backend"
RUNTIME_DIR="$ROOT_DIR/runtime"
PY_BIN="$(command -v python3.14 || command -v python3)"

mkdir -p "$RUNTIME_DIR"

cd "$FRONTEND_DIR"
npm install
npm run build

cd "$BACKEND_DIR"
"$PY_BIN" -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

mkdir -p "$RUNTIME_DIR/backend"
rsync -a --delete "$BACKEND_DIR/app/" "$RUNTIME_DIR/backend/app/"
rsync -a --delete "$BACKEND_DIR/frontend_dist/" "$RUNTIME_DIR/backend/frontend_dist/"
cp "$BACKEND_DIR/requirements.txt" "$RUNTIME_DIR/backend/requirements.txt"
cp "$BACKEND_DIR/env.temp.json" "$RUNTIME_DIR/backend/env.temp.json"

if [[ -f "$BACKEND_DIR/env.json" ]]; then
	cp "$BACKEND_DIR/env.json" "$RUNTIME_DIR/backend/env.json"
fi

echo "Build complete. Run scripts/dev-backend.sh to start local service."
