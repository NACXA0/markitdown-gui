#!/usr/bin/env bash
# 下载官方 pandoc 二进制到 ./bin/pandoc（架构与宿主一致）。
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"

# shellcheck source=linux-arch.sh
source "$ROOT/scripts/linux-arch.sh"
detect_linux_arch

BIN_DIR="$ROOT/bin"
PANDOC_VERSION="${PANDOC_VERSION:-3.6.4}"
OUT="$BIN_DIR/pandoc"

mkdir -p "$BIN_DIR"

if [[ -x "$OUT" ]]; then
  if verify_elf_arch "$OUT"; then
    echo "Pandoc already present: $OUT ($HOST_MACHINE)"
    exit 0
  fi
  echo "==> Existing pandoc does not match host $HOST_MACHINE; re-downloading..."
  rm -f "$OUT"
fi

case "$HOST_MACHINE" in
  x86_64)
    ARCHIVE="pandoc-${PANDOC_VERSION}-linux-amd64.tar.gz"
    ;;
  aarch64)
    ARCHIVE="pandoc-${PANDOC_VERSION}-linux-arm64.tar.gz"
    ;;
  *)
    echo "Unsupported arch: $HOST_MACHINE" >&2
    exit 1
    ;;
esac

URL="https://github.com/jgm/pandoc/releases/download/${PANDOC_VERSION}/${ARCHIVE}"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

echo "==> Downloading $URL"
curl -fsSL "$URL" -o "$TMP/$ARCHIVE"
tar -xzf "$TMP/$ARCHIVE" -C "$TMP"
BIN="$(find "$TMP" -type f -name pandoc | head -n1)"
cp -f "$BIN" "$OUT"
chmod +x "$OUT"
verify_elf_arch "$OUT"
echo "==> Pandoc ready: $OUT ($HOST_MACHINE)"
