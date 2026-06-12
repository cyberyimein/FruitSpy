#!/usr/bin/env zsh
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
APP_DIR="$ROOT_DIR/dist/FruitSpy.app"
MACOS_DIR="$APP_DIR/Contents/MacOS"
RESOURCES_DIR="$APP_DIR/Contents/Resources"
BUNDLED_SCRIPTS_DIR="$RESOURCES_DIR/scripts"
BUNDLED_RUNTIME_DIR="$RESOURCES_DIR/runtime"
FRONTEND_ICON_PNG="$ROOT_DIR/frontend/public/app-icon.png"
FRONTEND_ICON_SVG="$ROOT_DIR/frontend/public/favicon.svg"
BUILD_CACHE_DIR="$(mktemp -d)"

cleanup() {
  rm -rf "$BUILD_CACHE_DIR"
}
trap cleanup EXIT

build_icns_from_png() {
  local png_path="$1"
  local target_icns="$2"
  local tmp_dir
  tmp_dir="$(mktemp -d)"

  local iconset_dir
  iconset_dir="$tmp_dir/AppIcon.iconset"
  mkdir -p "$iconset_dir"

  sips -z 16 16 "$png_path" --out "$iconset_dir/icon_16x16.png" >/dev/null
  sips -z 32 32 "$png_path" --out "$iconset_dir/icon_16x16@2x.png" >/dev/null
  sips -z 32 32 "$png_path" --out "$iconset_dir/icon_32x32.png" >/dev/null
  sips -z 64 64 "$png_path" --out "$iconset_dir/icon_32x32@2x.png" >/dev/null
  sips -z 128 128 "$png_path" --out "$iconset_dir/icon_128x128.png" >/dev/null
  sips -z 256 256 "$png_path" --out "$iconset_dir/icon_128x128@2x.png" >/dev/null
  sips -z 256 256 "$png_path" --out "$iconset_dir/icon_256x256.png" >/dev/null
  sips -z 512 512 "$png_path" --out "$iconset_dir/icon_256x256@2x.png" >/dev/null
  sips -z 512 512 "$png_path" --out "$iconset_dir/icon_512x512.png" >/dev/null
  sips -z 1024 1024 "$png_path" --out "$iconset_dir/icon_512x512@2x.png" >/dev/null

  iconutil -c icns "$iconset_dir" -o "$target_icns" >/dev/null 2>&1 || {
    rm -rf "$tmp_dir"
    return 1
  }

  rm -rf "$tmp_dir"
  return 0
}

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

if [[ ! -d "$ROOT_DIR/runtime/backend/app" ]]; then
  echo "Bundled runtime is missing. Run scripts/build-app.sh first." >&2
  exit 1
fi

rm -rf "$APP_DIR"
mkdir -p "$MACOS_DIR" "$RESOURCES_DIR" "$BUNDLED_SCRIPTS_DIR" "$BUNDLED_RUNTIME_DIR"

SWIFT_SOURCES=(
  "$ROOT_DIR/launcher/Sources/main.swift"
  "$ROOT_DIR/launcher/Sources/AppDelegate.swift"
  "$ROOT_DIR/launcher/Sources/ServiceController.swift"
)
SWIFT_CACHE_ENV=(
  "CLANG_MODULE_CACHE_PATH=$BUILD_CACHE_DIR/clang"
  "SWIFT_MODULECACHE_PATH=$BUILD_CACHE_DIR/swift"
)
SWIFT_LOG="$BUILD_CACHE_DIR/swiftc.log"

if ! env "${SWIFT_CACHE_ENV[@]}" swiftc \
  -framework AppKit \
  "${SWIFT_SOURCES[@]}" \
  -o "$MACOS_DIR/FruitSpyLauncher" 2> "$SWIFT_LOG"; then
  COMPATIBLE_SDK="/Library/Developer/CommandLineTools/SDKs/MacOSX15.4.sdk"
  if [[ ! -d "$COMPATIBLE_SDK" ]]; then
    cat "$SWIFT_LOG" >&2
    exit 1
  fi

  echo "Default macOS SDK is incompatible with swiftc; retrying with MacOSX15.4.sdk"
  env "${SWIFT_CACHE_ENV[@]}" swiftc \
    -sdk "$COMPATIBLE_SDK" \
    -target "$(uname -m)-apple-macosx12.0" \
    -framework AppKit \
    "${SWIFT_SOURCES[@]}" \
    -o "$MACOS_DIR/FruitSpyLauncher"
fi

cp "$ROOT_DIR/launcher/Info.plist" "$APP_DIR/Contents/Info.plist"
cp "$ROOT_DIR/scripts/launcher.sh" "$BUNDLED_SCRIPTS_DIR/launcher.sh"
cp "$ROOT_DIR/scripts/dev-backend.sh" "$BUNDLED_SCRIPTS_DIR/dev-backend.sh"
rsync -a --delete "$ROOT_DIR/runtime/backend/" "$BUNDLED_RUNTIME_DIR/backend/"

if [[ -f "$ROOT_DIR/launcher/Resources/AppIcon.icns" ]]; then
  cp "$ROOT_DIR/launcher/Resources/AppIcon.icns" "$RESOURCES_DIR/AppIcon.icns"
elif [[ -f "$FRONTEND_ICON_PNG" ]] && build_icns_from_png "$FRONTEND_ICON_PNG" "$RESOURCES_DIR/AppIcon.icns"; then
  echo "App icon generated from frontend/public/app-icon.png"
elif [[ -f "$FRONTEND_ICON_SVG" ]] && build_icns_from_favicon "$FRONTEND_ICON_SVG" "$RESOURCES_DIR/AppIcon.icns"; then
  echo "App icon generated from frontend/public/favicon.svg"
else
  cp "/System/Library/CoreServices/CoreTypes.bundle/Contents/Resources/ToolbarInfo.icns" "$RESOURCES_DIR/AppIcon.icns"
fi

chmod +x "$BUNDLED_SCRIPTS_DIR/launcher.sh" "$BUNDLED_SCRIPTS_DIR/dev-backend.sh"

echo "Launcher app built at: $APP_DIR"
