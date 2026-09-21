#!/usr/bin/env bash
# 把 Flutter/Flet Linux 发布包打包成 amd64 .deb。
# 优先使用已有构建（含 flet-dropzone）。除非传入 --rebuild，否则不会重新执行依赖网络的 `flet build`。
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

REBUILD=0
if [[ "${1:-}" == "--rebuild" ]]; then
  REBUILD=1
fi

VERSION="$(python3 -c "import tomllib; print(tomllib.load(open('pyproject.toml','rb'))['project']['version'])")"
PKG="markitdown-gui"
ARCH="amd64"
BUNDLE="$ROOT/build/linux"
FLUTTER_BUNDLE="$ROOT/build/flutter/build/linux/x64/release/bundle"
OUT_DIR="$ROOT/dist/deb"
STAGE="$OUT_DIR/${PKG}_${VERSION}_${ARCH}"
DEB="$OUT_DIR/${PKG}_${VERSION}_${ARCH}.deb"
INSTALL_ROOT="/opt/markitdown-gui"

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

machine="$(uname -m)"
if [[ "$machine" != "x86_64" && "$machine" != "amd64" ]]; then
  echo "This script only packages amd64 (got $machine)." >&2
  exit 1
fi

ensure_bundle
ensure_pandoc_in_bundle

echo "==> Assembling package tree..."
rm -rf "$STAGE"
mkdir -p \
  "$STAGE/DEBIAN" \
  "$STAGE$INSTALL_ROOT" \
  "$STAGE/usr/bin" \
  "$STAGE/usr/share/applications" \
  "$STAGE/usr/share/icons/hicolor"

cp -a "$BUNDLE/." "$STAGE$INSTALL_ROOT/"
# 桌面入口和图标安装到 /usr/share 下，而不是 /opt 内部。
rm -rf "$STAGE$INSTALL_ROOT/share"

cat > "$STAGE/usr/bin/markitdown-gui" << EOF
#!/bin/sh
cd "$INSTALL_ROOT" || exit 1
exec ./markitdown-gui "\$@"
EOF
chmod 755 "$STAGE/usr/bin/markitdown-gui"

cat > "$STAGE/usr/share/applications/com.flet.markitdown-gui.desktop" << EOF
[Desktop Entry]
Type=Application
Name=MarkItDown GUI
Comment=Convert documents to Markdown
Exec=/usr/bin/markitdown-gui %U
Icon=com.flet.markitdown-gui
Terminal=false
Categories=Utility;Office;
StartupWMClass=com.flet.markitdown-gui
EOF

shopt -s nullglob
for png in "$BUNDLE"/share/icons/hicolor/*/apps/com.flet.markitdown-gui.png; do
  size_dir="$(basename "$(dirname "$(dirname "$png")")")"
  dest="$STAGE/usr/share/icons/hicolor/$size_dir/apps"
  mkdir -p "$dest"
  cp -f "$png" "$dest/com.flet.markitdown-gui.png"
done
shopt -u nullglob

if [[ ! -f "$STAGE/usr/share/icons/hicolor/256x256/apps/com.flet.markitdown-gui.png" && -f "$ROOT/assets/icon.png" ]]; then
  mkdir -p "$STAGE/usr/share/icons/hicolor/256x256/apps"
  cp -f "$ROOT/assets/icon.png" "$STAGE/usr/share/icons/hicolor/256x256/apps/com.flet.markitdown-gui.png"
fi

INSTALLED_KB="$(du -sk "$STAGE" --exclude=DEBIAN | awk '{print $1}')"

cat > "$STAGE/DEBIAN/control" << EOF
Package: $PKG
Version: $VERSION
Section: utils
Priority: optional
Architecture: $ARCH
Maintainer: nacxa <nacxa0@gmail.com>
Installed-Size: $INSTALLED_KB
Depends: libc6 (>= 2.35), libstdc++6, libgtk-3-0t64 | libgtk-3-0, libglib2.0-0t64 | libglib2.0-0
Homepage: https://github.com/NACXA0/markitdown-gui
Description: Desktop GUI for Microsoft MarkItDown (public preview 0.1.1)
 Convert documents to Markdown, preview the result, and export Markdown,
 Word, HTML, or PDF. Includes a local MCP server for other AI clients.
 This 0.1.1 package is a public test build, not a stable release.
EOF

cat > "$STAGE/DEBIAN/postinst" << 'EOF'
#!/bin/sh
set -e
if [ "$1" = "configure" ]; then
  if command -v gtk-update-icon-cache >/dev/null 2>&1; then
    gtk-update-icon-cache -f -t /usr/share/icons/hicolor >/dev/null 2>&1 || true
  fi
  if command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database -q /usr/share/applications >/dev/null 2>&1 || true
  fi
fi
EOF

cat > "$STAGE/DEBIAN/postrm" << 'EOF'
#!/bin/sh
set -e
if [ "$1" = "remove" ] || [ "$1" = "purge" ]; then
  if command -v gtk-update-icon-cache >/dev/null 2>&1; then
    gtk-update-icon-cache -f -t /usr/share/icons/hicolor >/dev/null 2>&1 || true
  fi
  if command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database -q /usr/share/applications >/dev/null 2>&1 || true
  fi
fi
EOF
chmod 755 "$STAGE/DEBIAN/postinst" "$STAGE/DEBIAN/postrm"

echo "==> Building $DEB ..."
mkdir -p "$OUT_DIR"
# gzip 能让旧版 dpkg 正常安装，也比 xz 占用更少磁盘。
dpkg-deb --root-owner-group -Zgzip -z6 --build "$STAGE" "$DEB"
rm -rf "$STAGE"
echo "==> deb ready: $DEB"
dpkg-deb -I "$DEB"
ls -lh "$DEB"
