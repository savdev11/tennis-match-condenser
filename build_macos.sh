#!/usr/bin/env bash
set -euo pipefail

APP_NAME="Tennis Match Condenser"
APP_VERSION="1.7.0"
BUNDLE_ID="com.saveriocustodi.tennismatchcondenser"
ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
DIST_DIR="$ROOT_DIR/dist"
BUILD_DIR="$ROOT_DIR/build"
STAGING_DIR="$DIST_DIR/dmg_staging"
DMG_NAME="Tennis-Match-Condenser-${APP_VERSION}-macOS.dmg"
ICON_PNG="$ROOT_DIR/assets/icon_1024.png"
ICON_ICNS="$ROOT_DIR/assets/app_icon.icns"
PYI_CFG="$ROOT_DIR/.pyinstaller"
PIP_CACHE="$ROOT_DIR/.pip-cache"

cd "$ROOT_DIR"

if [[ ! -d ".venv" ]]; then
  python3 -m venv .venv
fi
source .venv/bin/activate
export PYINSTALLER_CONFIG_DIR="$PYI_CFG"
export PIP_CACHE_DIR="$PIP_CACHE"

python -m pip install -r requirements.txt pyinstaller

rm -rf "$BUILD_DIR" "$DIST_DIR" "$PYI_CFG"

if [[ -f "$ICON_ICNS" ]]; then
  pyinstaller \
    --noconfirm \
    --clean \
    --windowed \
    --name "$APP_NAME" \
    --icon "$ICON_ICNS" \
    --osx-bundle-identifier "$BUNDLE_ID" \
    "$ROOT_DIR/app.py"
else
  pyinstaller \
    --noconfirm \
    --clean \
    --windowed \
    --name "$APP_NAME" \
    --osx-bundle-identifier "$BUNDLE_ID" \
    "$ROOT_DIR/app.py"
fi

# Ensure app bundle version is aligned with release tag.
APP_PLIST="$DIST_DIR/$APP_NAME.app/Contents/Info.plist"
if [[ -f "$APP_PLIST" ]]; then
  /usr/libexec/PlistBuddy -c "Set :CFBundleShortVersionString $APP_VERSION" "$APP_PLIST" \
    || /usr/libexec/PlistBuddy -c "Add :CFBundleShortVersionString string $APP_VERSION" "$APP_PLIST"
  /usr/libexec/PlistBuddy -c "Set :CFBundleVersion $APP_VERSION" "$APP_PLIST" \
    || /usr/libexec/PlistBuddy -c "Add :CFBundleVersion string $APP_VERSION" "$APP_PLIST"
fi

# Re-sign after Info.plist edits; otherwise macOS reports invalid signature.
if [[ -d "$DIST_DIR/$APP_NAME.app" ]]; then
  codesign --force --deep --sign - "$DIST_DIR/$APP_NAME.app"
fi

mkdir -p "$STAGING_DIR"
rm -rf "$STAGING_DIR/$APP_NAME.app" "$STAGING_DIR/Applications"
cp -R "$DIST_DIR/$APP_NAME.app" "$STAGING_DIR/"
ln -s /Applications "$STAGING_DIR/Applications"

hdiutil create \
  -volname "$APP_NAME" \
  -srcfolder "$STAGING_DIR" \
  -ov \
  -format UDZO \
  "$DIST_DIR/$DMG_NAME"

echo "Build completata:"
echo "App: $DIST_DIR/$APP_NAME.app"
echo "DMG: $DIST_DIR/$DMG_NAME"
