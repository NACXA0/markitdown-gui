#!/usr/bin/env bash
# 启动 Linux 发布包（含 flet-dropzone）。按宿主架构查找 Flutter bundle。
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"

# shellcheck source=linux-arch.sh
source "$ROOT/scripts/linux-arch.sh"
detect_linux_arch

FLUTTER_BUNDLE="$(flutter_linux_bundle_path "$ROOT")"
BIN=""
for cand in \
  "$ROOT/build/linux/markitdown-gui" \
  "$ROOT/build/linux/bundle/markitdown-gui" \
  "$FLUTTER_BUNDLE/markitdown-gui"
do
  if [[ -x "$cand" ]]; then
    if verify_elf_arch "$cand"; then
      BIN="$cand"
      break
    fi
    echo "跳过架构不匹配的二进制: $cand" >&2
  fi
done
if [[ -z "$BIN" ]]; then
  echo "未找到与宿主 ($HOST_MACHINE) 匹配的 markitdown-gui。" >&2
  echo "请先完成 Linux 构建：uv run flet build linux" >&2
  exit 1
fi
exec "$BIN" "$@"
