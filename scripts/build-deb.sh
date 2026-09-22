#!/usr/bin/env bash
# 把 Flutter/Flet Linux 发布包打成当前宿主架构的 .deb（amd64 或 arm64）。
# 优先使用已有构建（含 flet-dropzone）。除非传入 --rebuild，否则不会重新执行依赖网络的 `flet build`。
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

# shellcheck source=linux-arch.sh
source "$ROOT/scripts/linux-arch.sh"
detect_linux_arch

REBUILD=0
if [[ "${1:-}" == "--rebuild" ]]; then
  REBUILD=1
fi

VERSION="$(python3 -c "import tomllib; print(tomllib.load(open('pyproject.toml','rb'))['project']['version'])")"
PKG="markitdown-gui"
ARCH="$DEB_ARCH"
BUNDLE="$ROOT/build/linux"
FLUTTER_BUNDLE="$(flutter_linux_bundle_path "$ROOT")"
OUT_DIR="$ROOT/dist/deb"
STAGE="$OUT_DIR/$(deb_package_basename "$PKG" "$VERSION")"
DEB="$OUT_DIR/$(deb_package_basename "$PKG" "$VERSION").deb"
INSTALL_ROOT="/opt/markitdown-gui"

echo "==> Host arch: $HOST_MACHINE → deb Architecture: $ARCH"

ensure_bundle() {
  if [[ -x "$BUNDLE/markitdown-gui" && "$REBUILD" -eq 0 ]]; then
    if verify_elf_arch "$BUNDLE/markitdown-gui"; then
      echo "==> Using existing Linux bundle: $BUNDLE"
      return
    fi
    echo "==> Existing $BUNDLE/markitdown-gui does not match host; rebuilding..."
  fi
  if [[ -x "$FLUTTER_BUNDLE/markitdown-gui" && "$REBUILD" -eq 0 ]]; then
    if verify_elf_arch "$FLUTTER_BUNDLE/markitdown-gui"; then
      BUNDLE="$FLUTTER_BUNDLE"
      echo "==> Using existing Flutter Linux bundle: $BUNDLE"
      return
    fi
    echo "==> Existing Flutter bundle does not match host; rebuilding..."
  fi
  echo "==> Prefetching Flet runtime (GitHub mirror if needed)..."
  uv run python scripts/prefetch_flet_runtime.py
  sanitize_flutter_pubspec_paths "$ROOT"
  echo "==> Building Linux release with flet build..."
  flet_build_linux_env uv run flet build linux --skip-flutter-doctor
  BUNDLE="$ROOT/build/linux"
  if [[ ! -x "$BUNDLE/markitdown-gui" ]]; then
    echo "flet build linux did not produce $BUNDLE/markitdown-gui" >&2
    exit 1
  fi
  verify_elf_arch "$BUNDLE/markitdown-gui"
}

ensure_pandoc_in_bundle() {
  local dest="$BUNDLE/app/bin/pandoc"
  if [[ -x "$dest" ]] && verify_elf_arch "$dest"; then
    return
  fi
  if [[ -x "$ROOT/bin/pandoc" ]] && ! verify_elf_arch "$ROOT/bin/pandoc"; then
    echo "==> Removing host-mismatched $ROOT/bin/pandoc"
    rm -f "$ROOT/bin/pandoc"
  fi
  if [[ ! -x "$ROOT/bin/pandoc" ]]; then
    bash "$ROOT/scripts/fetch-pandoc.sh"
  fi
  verify_elf_arch "$ROOT/bin/pandoc"
  mkdir -p "$BUNDLE/app/bin"
  cp -f "$ROOT/bin/pandoc" "$dest"
  chmod +x "$dest"
  echo "==> Copied pandoc into bundle"
}

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
Description: Desktop GUI for Microsoft MarkItDown (public preview $VERSION)
 Convert documents to Markdown, preview the result, and export Markdown,
 Word, HTML, or PDF. Includes a local MCP server for other AI clients.
 This $VERSION package is a public test build, not a stable release.
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
