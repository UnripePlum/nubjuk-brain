#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

TAG="${LLAMA_CPP_TAG:-b8994}"
ASSET="${LLAMA_CPP_ASSET:-llama-$TAG-bin-macos-arm64.tar.gz}"
BASE_URL="${LLAMA_CPP_BASE_URL:-https://github.com/ggml-org/llama.cpp/releases/download/$TAG}"
INSTALL_ROOT="${LLAMA_CPP_INSTALL_ROOT:-$ROOT/.tools/llama.cpp}"
INSTALL_DIR="$INSTALL_ROOT/$TAG"
BIN_DIR="$INSTALL_ROOT/bin"
ARCH="$(uname -sm)"

if [ "$ARCH" != "Darwin arm64" ]; then
  echo "ERROR: this installer is pinned for macOS arm64, got: $ARCH" >&2
  echo "Override LLAMA_CPP_ASSET and LLAMA_CPP_BASE_URL for another platform." >&2
  exit 1
fi

mkdir -p "$INSTALL_DIR" "$BIN_DIR" "$ROOT/.tmp"

if [ ! -x "$INSTALL_DIR/llama-cli" ] && [ ! -x "$INSTALL_DIR/bin/llama-cli" ]; then
  ARCHIVE="$ROOT/.tmp/$ASSET"
  URL="$BASE_URL/$ASSET"
  echo "Downloading $URL"
  curl -L --fail --output "$ARCHIVE" "$URL"
  tar -xzf "$ARCHIVE" -C "$INSTALL_DIR"
fi

if [ -x "$INSTALL_DIR/llama-cli" ]; then
  SOURCE_BIN="$INSTALL_DIR/llama-cli"
elif [ -x "$INSTALL_DIR/bin/llama-cli" ]; then
  SOURCE_BIN="$INSTALL_DIR/bin/llama-cli"
else
  SOURCE_BIN="$(find "$INSTALL_DIR" -type f -name llama-cli 2>/dev/null | head -1 || true)"
fi

if [ -z "${SOURCE_BIN:-}" ]; then
  echo "ERROR: llama-cli not found after extracting $ASSET" >&2
  find "$INSTALL_DIR" -maxdepth 3 -type f | sort >&2
  exit 1
fi
chmod +x "$SOURCE_BIN"

ln -sf "$SOURCE_BIN" "$BIN_DIR/llama-cli"

echo "Installed llama-cli"
echo "Path: $BIN_DIR/llama-cli"
"$BIN_DIR/llama-cli" --version
