#!/usr/bin/env bash
# 把 MarkItDown GUI 的 AppImage 安装到用户应用菜单。
# 主产物：dist/appimage/MarkItDown_GUI-x86_64.AppImage
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
APPIMAGE_SRC="$ROOT/dist/appimage/MarkItDown_GUI-x86_64.AppImage"
INSTALL_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/markitdown-gui"
BIN_DIR="${HOME}/.local/bin"
APP_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/applications"
ICON_ROOT="${XDG_DATA_HOME:-$HOME/.local/share}/icons/hicolor"
ICON_DIR="$ICON_ROOT/256x256/apps"

if [[ ! -x "$APPIMAGE_SRC" ]]; then
  echo "未找到 AppImage，正在构建…"
  bash "$ROOT/scripts/build-appimage.sh"
fi

mkdir -p "$INSTALL_DIR" "$BIN_DIR" "$APP_DIR" "$ICON_DIR"
cp -f "$APPIMAGE_SRC" "$INSTALL_DIR/MarkItDown_GUI-x86_64.AppImage"
chmod +x "$INSTALL_DIR/MarkItDown_GUI-x86_64.AppImage"
ln -sfn "$INSTALL_DIR/MarkItDown_GUI-x86_64.AppImage" "$BIN_DIR/markitdown-gui"

ICON_SRC=""
for cand in \
  "$ROOT/assets/icon.png" \
  "$ROOT/build/linux/share/icons/hicolor/256x256/apps/com.flet.markitdown-gui.png" \
  "$ROOT/build/flutter/images/icon.png"
do
  if [[ -f "$cand" ]]; then
    ICON_SRC="$cand"
    break
  fi
done
if [[ -n "$ICON_SRC" ]]; then
  cp -f "$ICON_SRC" "$ICON_DIR/markitdown-gui.png"
fi

cat > "$APP_DIR/markitdown-gui.desktop" << EOF
[Desktop Entry]
Name=MarkItDown GUI
Comment=Convert documents to Markdown
Exec=$BIN_DIR/markitdown-gui
Icon=markitdown-gui
Type=Application
Categories=Utility;Office;
Terminal=false
StartupNotify=true
StartupWMClass=com.flet.markitdown-gui
EOF

# 删除旧的 Flet bundle 桌面入口（来自早期安装路径）。
rm -f "$APP_DIR/com.flet.markitdown-gui.desktop"

if command -v update-desktop-database >/dev/null 2>&1; then
  update-desktop-database "$APP_DIR" >/dev/null 2>&1 || true
fi
if command -v gtk-update-icon-cache >/dev/null 2>&1; then
  gtk-update-icon-cache -q -t -f "$ICON_ROOT" 2>/dev/null || true
fi

echo "已安装 AppImage："
echo "  AppImage → $INSTALL_DIR/MarkItDown_GUI-x86_64.AppImage"
echo "  命令     → $BIN_DIR/markitdown-gui"
echo "  菜单项   → $APP_DIR/markitdown-gui.desktop"
echo
echo "可在应用菜单搜索「MarkItDown」，或运行：markitdown-gui"
echo
echo "注意：拖放需要本 AppImage（内含 flet-dropzone）。"
echo "不要用 \`uv run python main.py\` 测拖放——那会走官方轻量客户端并报 Unknown control: flet_dropzone。"
