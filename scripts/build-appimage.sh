#!/usr/bin/env bash
# 把 Flutter/Flet Linux 发布包打成当前宿主架构的 AppImage（x86_64 或 aarch64）。
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

# 优先使用 Flet 1.0 `flet build linux` 输出；否则回退到 Flutter bundle 路径。
BUNDLE="$ROOT/build/linux"
FLUTTER_BUNDLE="$(flutter_linux_bundle_path "$ROOT")"
OUT_DIR="$ROOT/dist/appimage"
APPDIR="$OUT_DIR/MarkItDownGUI-${APPIMAGE_ARCH}.AppDir"
APPIMAGE_NAME="$(appimage_basename)"
APPIMAGE="$OUT_DIR/$APPIMAGE_NAME"
TOOL="$ROOT/bin/appimagetool-${APPIMAGETOOL_ARCH}"

echo "==> Host arch: $HOST_MACHINE → AppImage: $APPIMAGE_NAME"

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

ensure_appimagetool() {
  if command -v appimagetool >/dev/null 2>&1; then
    local found
    found="$(command -v appimagetool)"
    if verify_elf_arch "$found"; then
      TOOL="$found"
      return
    fi
    echo "==> Ignoring PATH appimagetool (wrong arch): $found"
  fi
  if [[ -x "$TOOL" ]] && verify_elf_arch "$TOOL"; then
    return
  fi
  # 兼容旧路径 bin/appimagetool（仅当架构匹配时复用）
  if [[ -x "$ROOT/bin/appimagetool" ]] && verify_elf_arch "$ROOT/bin/appimagetool"; then
    TOOL="$ROOT/bin/appimagetool"
    return
  fi
  echo "==> Fetching appimagetool for $APPIMAGETOOL_ARCH..."
  mkdir -p "$ROOT/bin"
  URL="https://github.com/AppImage/appimagetool/releases/download/continuous/appimagetool-${APPIMAGETOOL_ARCH}.AppImage"
  MIRROR="https://ghfast.top/${URL}"
  if ! curl -L --fail --connect-timeout 30 --retry 5 -o "$TOOL" "$MIRROR"; then
    curl -L --fail --connect-timeout 30 --retry 5 -o "$TOOL" "$URL"
  fi
  chmod +x "$TOOL"
  verify_elf_arch "$TOOL"
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

echo "==> Syncing dependencies..."
uv sync --group dev

ensure_bundle
ensure_pandoc_in_bundle
mkdir -p "$ROOT/build/linux"

echo "==> Assembling AppDir..."
rm -rf "$APPDIR"
mkdir -p "$APPDIR/usr/bin" "$APPDIR/usr/share/applications" "$APPDIR/usr/share/icons/hicolor/256x256/apps"
cp -a "$BUNDLE/." "$APPDIR/usr/bin/"
# share/ 必须放在 AppDir 的 usr/share 下，而不是 usr/bin 内部
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

# AppImage 根目录的 .desktop 必须使用简单的 Icon= 基本名，且同目录要有对应的 .png
#（appimagetool 遇到没有该文件的反向 DNS 图标名会拒绝）。
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
  # 最小合法 1x1 PNG，让 appimagetool 接受该 AppDir。
  printf '\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\x0f\x00\x00\x01\x01\x00\x05\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82' \
    > "$APPDIR/markitdown-gui.png"
  ln -sfn "markitdown-gui.png" "$APPDIR/.DirIcon"
fi

ensure_appimagetool
mkdir -p "$OUT_DIR"

# appimagetool 在含非 ASCII 字符的路径下会报 Invalid byte sequence；
# 把最终打包放到纯 ASCII 的 /tmp 暂存区再拷回。
STAGE_ROOT="/tmp/markitdown-gui-appimage-${APPIMAGE_ARCH}"
STAGE_APPDIR="$STAGE_ROOT/MarkItDownGUI-${APPIMAGE_ARCH}.AppDir"
STAGE_OUT="$STAGE_ROOT/$APPIMAGE_NAME"
rm -rf "$STAGE_ROOT"
mkdir -p "$STAGE_ROOT"
echo "==> Staging AppDir at $STAGE_APPDIR (ASCII path for appimagetool)"
cp -a "$APPDIR" "$STAGE_APPDIR"

RUNTIME_FILE=""
for cand in \
  "$ROOT/bin/runtime-${APPIMAGETOOL_ARCH}" \
  "$ROOT/bin/runtime-x86_64" \
  "$ROOT/bin/runtime-aarch64"
do
  if [[ -f "$cand" ]]; then
    RUNTIME_FILE="$cand"
    break
  fi
done

# runtime 也拷到 ASCII 路径，避免 --runtime-file 踩中文路径
STAGE_RUNTIME=""
if [[ -n "$RUNTIME_FILE" ]]; then
  STAGE_RUNTIME="$STAGE_ROOT/runtime-${APPIMAGETOOL_ARCH}"
  cp -f "$RUNTIME_FILE" "$STAGE_RUNTIME"
fi

echo "==> Building AppImage with $TOOL ..."
set +e
if [[ -n "$STAGE_RUNTIME" ]]; then
  echo "==> Using local runtime: $RUNTIME_FILE"
  ARCH="$APPIMAGE_ARCH" "$TOOL" --runtime-file "$STAGE_RUNTIME" "$STAGE_APPDIR" "$STAGE_OUT"
else
  MIRROR_RUNTIME="https://ghfast.top/https://github.com/AppImage/type2-runtime/releases/download/continuous/runtime-${APPIMAGETOOL_ARCH}"
  TMP_RUNTIME="$STAGE_ROOT/runtime-${APPIMAGETOOL_ARCH}"
  if curl -L --fail --connect-timeout 30 --retry 5 -o "$TMP_RUNTIME" "$MIRROR_RUNTIME"; then
    ARCH="$APPIMAGE_ARCH" "$TOOL" --runtime-file "$TMP_RUNTIME" "$STAGE_APPDIR" "$STAGE_OUT"
  else
    ARCH="$APPIMAGE_ARCH" "$TOOL" "$STAGE_APPDIR" "$STAGE_OUT"
  fi
fi
APPIMAGE_RC=$?
set -e
if [[ $APPIMAGE_RC -ne 0 || ! -x "$STAGE_OUT" ]]; then
  echo "AppImage 打包失败（exit=$APPIMAGE_RC）。可手动下载 runtime 到 bin/runtime-${APPIMAGETOOL_ARCH} 后重试。" >&2
  exit 1
fi
cp -f "$STAGE_OUT" "$APPIMAGE"
chmod +x "$APPIMAGE"
rm -rf "$STAGE_ROOT"
echo "==> AppImage ready: $APPIMAGE"
ls -lh "$APPIMAGE"
