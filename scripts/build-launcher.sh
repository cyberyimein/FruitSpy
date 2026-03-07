#!/usr/bin/env zsh
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
APP_DIR="$ROOT_DIR/dist/FruitSpy.app"
MACOS_DIR="$APP_DIR/Contents/MacOS"
RESOURCES_DIR="$APP_DIR/Contents/Resources"
FRONTEND_ICON_SVG="$ROOT_DIR/frontend/public/favicon.svg"

build_icns_from_favicon() {
  local svg_path="$1"
  local target_icns="$2"
  local tmp_dir
  tmp_dir="$(mktemp -d)"

  qlmanage -t -s 1024 -o "$tmp_dir" "$svg_path" >/dev/null 2>&1 || {
    rm -rf "$tmp_dir"
    return 1
  }

  local preview_png
  preview_png="$tmp_dir/$(basename "$svg_path").png"
  if [[ ! -f "$preview_png" ]]; then
    rm -rf "$tmp_dir"
    return 1
  fi

  local iconset_dir
  iconset_dir="$tmp_dir/AppIcon.iconset"
  mkdir -p "$iconset_dir"

  sips -z 16 16 "$preview_png" --out "$iconset_dir/icon_16x16.png" >/dev/null
  sips -z 32 32 "$preview_png" --out "$iconset_dir/icon_16x16@2x.png" >/dev/null
  sips -z 32 32 "$preview_png" --out "$iconset_dir/icon_32x32.png" >/dev/null
  sips -z 64 64 "$preview_png" --out "$iconset_dir/icon_32x32@2x.png" >/dev/null
  sips -z 128 128 "$preview_png" --out "$iconset_dir/icon_128x128.png" >/dev/null
  sips -z 256 256 "$preview_png" --out "$iconset_dir/icon_128x128@2x.png" >/dev/null
  sips -z 256 256 "$preview_png" --out "$iconset_dir/icon_256x256.png" >/dev/null
  sips -z 512 512 "$preview_png" --out "$iconset_dir/icon_256x256@2x.png" >/dev/null
  sips -z 512 512 "$preview_png" --out "$iconset_dir/icon_512x512.png" >/dev/null
  cp "$preview_png" "$iconset_dir/icon_512x512@2x.png"

  iconutil -c icns "$iconset_dir" -o "$target_icns" >/dev/null 2>&1 || {
    rm -rf "$tmp_dir"
    return 1
  }

  rm -rf "$tmp_dir"
  return 0
}

mkdir -p "$MACOS_DIR" "$RESOURCES_DIR"

swiftc \
  -framework AppKit \
  "$ROOT_DIR/launcher/Sources/main.swift" \
  "$ROOT_DIR/launcher/Sources/AppDelegate.swift" \
  "$ROOT_DIR/launcher/Sources/ServiceController.swift" \
  -o "$MACOS_DIR/FruitSpyLauncher"

cp "$ROOT_DIR/launcher/Info.plist" "$APP_DIR/Contents/Info.plist"
cp "$ROOT_DIR/scripts/launcher.sh" "$RESOURCES_DIR/launcher.sh"

if [[ -f "$ROOT_DIR/launcher/Resources/AppIcon.icns" ]]; then
  cp "$ROOT_DIR/launcher/Resources/AppIcon.icns" "$RESOURCES_DIR/AppIcon.icns"
elif [[ -f "$FRONTEND_ICON_SVG" ]] && build_icns_from_favicon "$FRONTEND_ICON_SVG" "$RESOURCES_DIR/AppIcon.icns"; then
  echo "App icon generated from frontend/public/favicon.svg"
else
  cp "/System/Library/CoreServices/CoreTypes.bundle/Contents/Resources/ToolbarInfo.icns" "$RESOURCES_DIR/AppIcon.icns"
fi

chmod +x "$RESOURCES_DIR/launcher.sh"

echo "Launcher app built at: $APP_DIR"
