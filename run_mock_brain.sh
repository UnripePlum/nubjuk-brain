#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV="$ROOT/.venv"

if [ ! -x "$VENV/bin/python" ]; then
  echo "ERROR: .venv not found at $VENV" >&2
  echo "Create it with:" >&2
  echo "  cd \"$ROOT\"" >&2
  echo "  python3 -m venv .venv" >&2
  echo "  .venv/bin/python -m pip install -e '.[dev]'" >&2
  exit 1
fi

HOST="${MOCK_BRAIN_HOST:-0.0.0.0}"
PORT="${MOCK_BRAIN_PORT:-8080}"

cd "$ROOT"
exec "$VENV/bin/python" -m uvicorn brain.ws_server:app --host "$HOST" --port "$PORT"

