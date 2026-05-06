#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

REPO_ID="${QWEN35_REPO_ID:-lmstudio-community/Qwen3.5-0.8B-GGUF}"
MODEL_FILE="${QWEN35_MODEL_FILE:-Qwen3.5-0.8B-Q4_K_M.gguf}"
MODEL_DIR="${QWEN35_MODEL_DIR:-$ROOT/models/qwen3.5-0.8b}"
MODEL_PATH="$MODEL_DIR/$MODEL_FILE"
URL="https://huggingface.co/$REPO_ID/resolve/main/$MODEL_FILE"
EXPECTED_BYTES="${QWEN35_EXPECTED_BYTES:-527502816}"
EXPECTED_SHA256="${QWEN35_EXPECTED_SHA256:-f5b14da98939b60bbe1019a964eba656407e1e0b64f1fe3003ff6d650e93bfec}"

mkdir -p "$MODEL_DIR"

if [ -f "$MODEL_PATH" ]; then
  echo "Model already exists: $MODEL_PATH"
else
  TMP_PATH="$MODEL_PATH.tmp"
  echo "Downloading $REPO_ID/$MODEL_FILE"
  echo "Target: $MODEL_PATH"
  curl -L --fail --continue-at - --output "$TMP_PATH" "$URL"
  mv "$TMP_PATH" "$MODEL_PATH"
fi

actual_bytes="$(wc -c < "$MODEL_PATH" | tr -d ' ')"
if [ "$actual_bytes" != "$EXPECTED_BYTES" ]; then
  echo "ERROR: size mismatch for $MODEL_PATH" >&2
  echo "expected=$EXPECTED_BYTES actual=$actual_bytes" >&2
  exit 1
fi

actual_sha256="$(shasum -a 256 "$MODEL_PATH" | awk '{print $1}')"
if [ "$actual_sha256" != "$EXPECTED_SHA256" ]; then
  echo "ERROR: sha256 mismatch for $MODEL_PATH" >&2
  echo "expected=$EXPECTED_SHA256 actual=$actual_sha256" >&2
  exit 1
fi

cat > "$MODEL_DIR/manifest.json" <<EOF
{
  "model": "Qwen3.5-0.8B",
  "format": "GGUF",
  "quantization": "Q4_K_M",
  "repo_id": "$REPO_ID",
  "file": "$MODEL_FILE",
  "path": "$MODEL_PATH",
  "bytes": $actual_bytes,
  "sha256": "$actual_sha256"
}
EOF

echo "Installed Qwen3.5-0.8B Q4_K_M GGUF"
echo "Model path: $MODEL_PATH"
