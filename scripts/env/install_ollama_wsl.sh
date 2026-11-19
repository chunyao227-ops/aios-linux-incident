#!/usr/bin/env bash
set -euo pipefail

VERSION="${OLLAMA_VERSION:-v0.40.16}"
ARCHIVE="ollama-linux-amd64.tar.zst"
EXPECTED_SHA="${OLLAMA_SHA256:-87bfafb2acbc89b2e6a1be0a9043de6aa75fb450696f86bc426e65fc448f788d}"
DOWNLOAD_DIR="${OLLAMA_DOWNLOAD_DIR:-$HOME/.cache/ollama-download}"
INSTALL_ROOT="${OLLAMA_INSTALL_ROOT:-$HOME/.local/lib/ollama}"
BIN_DIR="${OLLAMA_BIN_DIR:-$HOME/.local/bin}"
MIRROR_URL="${OLLAMA_MIRROR_URL:-https://gh-proxy.com/https://github.com/ollama/ollama/releases/download/$VERSION/$ARCHIVE}"

mkdir -p "$DOWNLOAD_DIR" "$INSTALL_ROOT" "$BIN_DIR"

if [[ ! -f "$DOWNLOAD_DIR/$ARCHIVE" ]]; then
  curl -L --retry 5 --retry-delay 2 --connect-timeout 15 \
    -o "$DOWNLOAD_DIR/$ARCHIVE.part" "$MIRROR_URL"
  mv "$DOWNLOAD_DIR/$ARCHIVE.part" "$DOWNLOAD_DIR/$ARCHIVE"
fi

actual_sha="$(sha256sum "$DOWNLOAD_DIR/$ARCHIVE" | awk '{print $1}')"
if [[ "$actual_sha" != "$EXPECTED_SHA" ]]; then
  echo "SHA-256 mismatch: expected $EXPECTED_SHA, got $actual_sha" >&2
  exit 2
fi

tar --zstd -xf "$DOWNLOAD_DIR/$ARCHIVE" -C "$INSTALL_ROOT"
ln -sfn "$INSTALL_ROOT/bin/ollama" "$BIN_DIR/ollama"
"$BIN_DIR/ollama" --version

echo "Installed Ollama to $INSTALL_ROOT"
echo "Start with: bash scripts/env/start_ollama_wsl.sh"

