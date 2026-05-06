#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MODEL_PATH="${QWEN35_MODEL_PATH:-$ROOT/models/qwen3.5-0.8b/Qwen3.5-0.8B-Q4_K_M.gguf}"
LLAMA_CLI="${LLAMA_CLI:-$ROOT/.tools/llama.cpp/bin/llama-cli}"
PROMPT="${1:-Map the Korean command '오른쪽으로 굴러' to one intent id from: roll_right. Answer only the id.}"

if [ ! -f "$MODEL_PATH" ]; then
  echo "ERROR: model not found at $MODEL_PATH" >&2
  echo "Install it with: scripts/install_qwen35_0_8b.sh" >&2
  exit 1
fi

if [ ! -x "$LLAMA_CLI" ] && ! command -v "$LLAMA_CLI" >/dev/null 2>&1; then
  echo "ERROR: llama-cli not found." >&2
  echo "Install it with: scripts/install_llama_cli.sh" >&2
  echo "Or set LLAMA_CLI=/path/to/llama-cli." >&2
  exit 1
fi

exec "$LLAMA_CLI" \
  -m "$MODEL_PATH" \
  -p "$PROMPT" \
  -n 16 \
  --temp 0 \
  --ctx-size 2048 \
  --single-turn \
  --reasoning off \
  --no-display-prompt \
  --no-warmup \
  --log-disable
