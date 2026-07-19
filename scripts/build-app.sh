#!/usr/bin/env zsh
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
FRONTEND_DIR="$ROOT_DIR/frontend"
BACKEND_DIR="$ROOT_DIR/backend"
RUNTIME_DIR="$ROOT_DIR/runtime"
PY_BIN=""
for name in python3.13 python3.12 python3.11 python3.10; do
  candidate="$(command -v "$name" 2>/dev/null || true)"
  if [[ -n "$candidate" ]]; then
    PY_BIN="$candidate"
    break
  fi
done
if [[ -z "$PY_BIN" ]]; then
  for candidate in \
    "$HOME/miniforge3/bin/python3.13" \
    "/opt/homebrew/Caskroom/miniforge/base/bin/python3.13" \
    "/opt/homebrew/bin/python3.13" \
    "/usr/local/bin/python3.13"; do
    if [[ -x "$candidate" ]]; then
      PY_BIN="$candidate"
      break
    fi
  done
fi

if [[ -z "$PY_BIN" ]]; then
  echo "FruitSpy Crawl API requires Python 3.10-3.13" >&2
  exit 1
fi

mkdir -p "$RUNTIME_DIR"

cd "$FRONTEND_DIR"
npm install
npm run build

cd "$BACKEND_DIR"
if [[ -d .venv ]] && ! .venv/bin/python -c 'import sys; raise SystemExit(not ((3, 10) <= sys.version_info[:2] <= (3, 13)))'; then
  "$PY_BIN" -m venv --clear .venv
else
  "$PY_BIN" -m venv .venv
fi
source .venv/bin/activate
pip install -r requirements.txt
python -m playwright install chromium

mkdir -p "$RUNTIME_DIR/backend"
rsync -a --delete "$BACKEND_DIR/app/" "$RUNTIME_DIR/backend/app/"
rsync -a --delete "$BACKEND_DIR/frontend_dist/" "$RUNTIME_DIR/backend/frontend_dist/"
cp "$BACKEND_DIR/requirements.txt" "$RUNTIME_DIR/backend/requirements.txt"
cp "$BACKEND_DIR/env.temp.json" "$RUNTIME_DIR/backend/env.temp.json"

if [[ -f "$BACKEND_DIR/env.json" ]]; then
	cp "$BACKEND_DIR/env.json" "$RUNTIME_DIR/backend/env.json"
fi

echo "Build complete. Run scripts/dev-backend.sh to start local service."
