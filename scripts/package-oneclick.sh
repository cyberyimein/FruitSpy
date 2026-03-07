#!/usr/bin/env zsh
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
DIST_DIR="$ROOT_DIR/dist"
APP_PATH="$DIST_DIR/FruitSpy.app"
ZIP_PATH="$DIST_DIR/FruitSpy-oneclick.zip"

"$ROOT_DIR/scripts/build-app.sh"
"$ROOT_DIR/scripts/build-launcher.sh"

rm -f "$ZIP_PATH"
cd "$DIST_DIR"
/usr/bin/zip -r "$(basename "$ZIP_PATH")" "$(basename "$APP_PATH")" >/dev/null

echo "One-click package ready: $ZIP_PATH"
