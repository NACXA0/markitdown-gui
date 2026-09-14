#!/usr/bin/env bash
# Download official pandoc binary into ./bin/pandoc
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BIN_DIR="$ROOT/bin"
PANDOC_VERSION="${PANDOC_VERSION:-3.6.4}"
OUT="$BIN_DIR/pandoc"

mkdir -p "$BIN_DIR"

if [[ -x "$OUT" ]]; then
  echo "Pandoc already present: $OUT"
  exit 0
fi

ARCH="$(uname -m)"
case "$ARCH" in
  x86_64|amd64)
    ARCHIVE="pandoc-${PANDOC_VERSION}-linux-amd64.tar.gz"
    ;;
  aarch64|arm64)
    ARCHIVE="pandoc-${PANDOC_VERSION}-linux-arm64.tar.gz"
    ;;
  *)
    echo "Unsupported arch: $ARCH" >&2
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
echo "==> Pandoc ready: $OUT"
