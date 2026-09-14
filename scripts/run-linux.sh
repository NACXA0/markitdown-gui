#!/usr/bin/env bash
# Launch the Linux release bundle (includes flet-dropzone).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BIN="$ROOT/build/linux/bundle/markitdown-gui"
if [[ ! -x "$BIN" ]]; then
  BIN="$ROOT/build/flutter/build/linux/x64/release/bundle/markitdown-gui"
fi
if [[ ! -x "$BIN" ]]; then
  echo "未找到已构建的 markitdown-gui。" >&2
  echo "请先完成 Linux 构建（flet build / flutter build）。" >&2
  exit 1
fi
exec "$BIN" "$@"
