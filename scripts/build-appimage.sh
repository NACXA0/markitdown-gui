#!/usr/bin/env bash
# Package the Flutter/Flet Linux release bundle as an x86_64 AppImage.
# Prefers an existing build (with flet-dropzone). Does not re-run network-heavy
# `flet build` unless --rebuild is passed.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

REBUILD=0
if [[ "${1:-}" == "--rebuild" ]]; then
  REBUILD=1
fi

# Prefer Flet 1.0 `flet build linux` output; fall back to Flutter bundle path.
BUNDLE="$ROOT/build/linux"
FLUTTER_BUNDLE="$ROOT/build/flutter/build/linux/x64/release/bundle"
OUT_DIR="$ROOT/dist/appimage"
APPDIR="$OUT_DIR/MarkItDownGUI.AppDir"
APPIMAGE="$OUT_DIR/MarkItDown_GUI-x86_64.AppImage"
TOOL="$ROOT/bin/appimagetool"

ensure_bundle() {
  if [[ -x "$BUNDLE/markitdown-gui" && "$REBUILD" -eq 0 ]]; then
    echo "==> Using existing Linux bundle: $BUNDLE"
    return
  fi
  if [[ -x "$FLUTTER_BUNDLE/markitdown-gui" && "$REBUILD" -eq 0 ]]; then
    BUNDLE="$FLUTTER_BUNDLE"
    echo "==> Using existing Flutter Linux bundle: $BUNDLE"
    return
  fi
  echo "==> Building Linux release with flet build..."
  env -u ANDROID_HOME uv run flet build linux --skip-flutter-doctor
  BUNDLE="$ROOT/build/linux"
  if [[ ! -x "$BUNDLE/markitdown-gui" ]]; then
    echo "flet build linux did not produce $BUNDLE/markitdown-gui" >&2
    exit 1
  fi
}

ensure_appimagetool() {
  if command -v appimagetool >/dev/null 2>&1; then
    TOOL="$(command -v appimagetool)"
    return
  fi
  if [[ -x "$TOOL" ]]; then
    return
  fi
  echo "==> Fetching appimagetool..."
  mkdir -p "$ROOT/bin"
  URL="https://github.com/AppImage/appimagetool/releases/download/continuous/appimagetool-x86_64.AppImage"
  MIRROR="https://ghfast.top/${URL}"
  if ! curl -L --fail --connect-timeout 30 --retry 5 -o "$TOOL" "$MIRROR"; then
    curl -L --fail --connect-timeout 30 --retry 5 -o "$TOOL" "$URL"
  fi
  chmod +x "$TOOL"
}

ensure_pandoc_in_bundle() {
  local dest="$BUNDLE/app/bin/pandoc"
  if [[ -x "$dest" ]]; then
    return
  fi
  if [[ ! -x "$ROOT/bin/pandoc" ]]; then
    bash "$ROOT/scripts/fetch-pandoc.sh"
  fi
  mkdir -p "$BUNDLE/app/bin"
  cp -f "$ROOT/bin/pandoc" "$dest"
  chmod +x "$dest"
  echo "==> Copied pandoc into bundle"
}

echo "==> Syncing dependencies..."
uv sync --group dev

ensure_bundle
ensure_pandoc_in_bundle
mkdir -p "$ROOT/build/linux"

echo "==> Assembling AppDir..."
rm -rf "$APPDIR"
mkdir -p "$APPDIR/usr/bin" "$APPDIR/usr/share/applications" "$APPDIR/usr/share/icons/hicolor/256x256/apps"
cp -a "$BUNDLE/." "$APPDIR/usr/bin/"
# share/ must live at AppDir usr/share, not inside usr/bin
if [[ -d "$APPDIR/usr/bin/share" ]]; then
  cp -a "$APPDIR/usr/bin/share/." "$APPDIR/usr/share/"
  rm -rf "$APPDIR/usr/bin/share"
fi

cat > "$APPDIR/AppRun" << 'EOF'
#!/bin/sh
HERE="$(dirname "$(readlink -f "$0")")"
cd "$HERE/usr/bin" || exit 1
exec "$HERE/usr/bin/markitdown-gui" "$@"
EOF
chmod +x "$APPDIR/AppRun"

# AppImage root .desktop must use a simple Icon= basename that matches a
# sibling .png (appimagetool rejects reverse-DNS icon names without that file).
cat > "$APPDIR/markitdown-gui.desktop" << 'EOF'
[Desktop Entry]
Name=MarkItDown GUI
Comment=Convert documents to Markdown
Exec=markitdown-gui
Icon=markitdown-gui
Type=Application
Categories=Utility;
Terminal=false
StartupWMClass=com.flet.markitdown-gui
EOF
cp -f "$APPDIR/markitdown-gui.desktop" "$APPDIR/usr/share/applications/"

DESKTOP_ID="com.flet.markitdown-gui"
ICON_SRC=""
for cand in \
  "$BUNDLE/share/icons/hicolor/256x256/apps/${DESKTOP_ID}.png" \
  "$ROOT/assets/icon.png" \
  "$ROOT/build/flutter/images/icon.png" \
  "$BUNDLE/data/flutter_assets/images/icon.png" \
  "$BUNDLE/data/app_icon.png"
do
  if [[ -f "$cand" ]]; then
    ICON_SRC="$cand"
    break
  fi
done
if [[ -n "$ICON_SRC" ]]; then
  cp -f "$ICON_SRC" "$APPDIR/markitdown-gui.png"
  cp -f "$ICON_SRC" "$APPDIR/usr/share/icons/hicolor/256x256/apps/markitdown-gui.png"
  ln -sfn "markitdown-gui.png" "$APPDIR/.DirIcon"
else
  # Minimal valid 1x1 PNG so appimagetool accepts the AppDir.
  printf '\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\x0f\x00\x00\x01\x01\x00\x05\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82' \
    > "$APPDIR/markitdown-gui.png"
  ln -sfn "markitdown-gui.png" "$APPDIR/.DirIcon"
fi

ensure_appimagetool
mkdir -p "$OUT_DIR"
echo "==> Building AppImage with $TOOL ..."
ARCH=x86_64 "$TOOL" "$APPDIR" "$APPIMAGE"
chmod +x "$APPIMAGE"
echo "==> AppImage ready: $APPIMAGE"
ls -lh "$APPIMAGE"
