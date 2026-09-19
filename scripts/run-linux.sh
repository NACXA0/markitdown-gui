#!/usr/bin/env bash
# Launch the Linux release bundle (includes flet-dropzone).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BIN=""
for cand in \
  "$ROOT/build/linux/markitdown-gui" \
  "$ROOT/build/linux/bundle/markitdown-gui" \
  "$ROOT/build/flutter/build/linux/x64/release/bundle/markitdown-gui"
do
  if [[ -x "$cand" ]]; then
    BIN="$cand"
    break
  fi
done
if [[ -z "$BIN" ]]; then
  echo "未找到已构建的 markitdown-gui。" >&2
  echo "请先完成 Linux 构建：uv run flet build linux" >&2
  exit 1
fi
exec "$BIN" "$@"
