#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV="$ROOT/.venv"

usage() {
  cat <<'EOF'
Usage:
  scripts/voice_test.sh

Environment:
  BRAIN_WS_URL     Brain WebSocket URL. Default: ws://127.0.0.1:8080/sti
  VOICE_SECONDS    Recording duration in seconds. Default: 3
  VOICE_WAV        Output WAV path. Default: .tmp/voice-test-<timestamp>.wav

Examples:
  scripts/voice_test.sh
  VOICE_SECONDS=5 scripts/voice_test.sh
  BRAIN_WS_URL=ws://192.168.0.10:8080/sti scripts/voice_test.sh
EOF
}

if [ "${1:-}" = "--help" ] || [ "${1:-}" = "-h" ]; then
  usage
  exit 0
fi

if [ "$#" -gt 0 ]; then
  echo "ERROR: unknown argument: $1" >&2
  usage >&2
  exit 2
fi

if [ ! -x "$VENV/bin/python" ]; then
  echo "ERROR: .venv not found at $VENV" >&2
  echo "Create it with:" >&2
  echo "  cd \"$ROOT\"" >&2
  echo "  python3 -m venv .venv" >&2
  echo "  .venv/bin/python -m pip install -e '.[dev]'" >&2
  exit 1
fi

URL="${BRAIN_WS_URL:-ws://127.0.0.1:8080/sti}"
SECONDS_TO_RECORD="${VOICE_SECONDS:-3}"
WAV_PATH="${VOICE_WAV:-$ROOT/.tmp/voice-test-$(date +%Y%m%d-%H%M%S).wav}"

"$VENV/bin/python" "$ROOT/scripts/record_voice.py" \
  --seconds "$SECONDS_TO_RECORD" \
  --output "$WAV_PATH"

"$VENV/bin/python" "$ROOT/scripts/send_wav_to_brain.py" \
  "$WAV_PATH" \
  --url "$URL"
