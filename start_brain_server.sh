#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SESSION="${BRAIN_TMUX_SESSION:-nubjuk-brain}"
LOG="${BRAIN_SERVER_LOG:-$ROOT/.tmp/brain-server.log}"
PORT="${MOCK_BRAIN_PORT:-8080}"
START_TIMEOUT_SECONDS="${BRAIN_START_TIMEOUT_SECONDS:-120}"

resolve_tmux_bin() {
  if command -v tmux >/dev/null 2>&1; then
    command -v tmux
    return 0
  fi
  for candidate in "$HOME/.local/bin/tmux" "$HOME/bin/tmux"; do
    if [ -x "$candidate" ]; then
      echo "$candidate"
      return 0
    fi
  done
  return 1
}

TMUX_BIN="${BRAIN_TMUX_BIN:-$(resolve_tmux_bin || true)}"

if [ -z "$TMUX_BIN" ]; then
  echo "ERROR: tmux is required to start the brain server in the background." >&2
  exit 1
fi

if "$TMUX_BIN" has-session -t "$SESSION" 2>/dev/null; then
  echo "ERROR: tmux session '$SESSION' already exists." >&2
  echo "Stop it with: $TMUX_BIN kill-session -t $SESSION" >&2
  exit 1
fi

if command -v lsof >/dev/null 2>&1 && lsof -nP -iTCP:"$PORT" -sTCP:LISTEN >/dev/null 2>&1; then
  echo "ERROR: TCP port $PORT is already in use." >&2
  lsof -nP -iTCP:"$PORT" -sTCP:LISTEN >&2
  exit 1
fi

mkdir -p "$(dirname "$LOG")"
rm -f "$LOG"

PIPELINE="${BRAIN_PIPELINE:-moonshine_tiny_ko}"
CATALOG="${INTENT_CATALOG_PATH:-recipes/nubjuk_motion_catalog.json}"
WS_QUEUE="${BRAIN_WS_MAX_QUEUE:-256}"
WS_PROTOCOL="${BRAIN_WS_PROTOCOL:-websockets}"
WS_SIZE="${BRAIN_WS_MAX_SIZE:-1048576}"

"$TMUX_BIN" new-session -d -s "$SESSION" -c "$ROOT" \
  "BRAIN_PIPELINE='$PIPELINE' INTENT_CATALOG_PATH='$CATALOG' BRAIN_WS_MAX_QUEUE='$WS_QUEUE' BRAIN_WS_PROTOCOL='$WS_PROTOCOL' BRAIN_WS_MAX_SIZE='$WS_SIZE' ./run_mock_brain.sh > '$LOG' 2>&1"

for ((attempt = 1; attempt <= START_TIMEOUT_SECONDS; attempt++)); do
  if command -v lsof >/dev/null 2>&1 && lsof -nP -iTCP:"$PORT" -sTCP:LISTEN >/dev/null 2>&1; then
    echo "brain server started"
    echo "session: $SESSION"
    echo "url: ws://0.0.0.0:$PORT/sti"
    echo "log: $LOG"
    echo "stop: $TMUX_BIN kill-session -t $SESSION"
    if [ "${BRAIN_NO_TAIL:-0}" = "1" ]; then
      echo "tail logs: tail -f '$LOG'"
      exit 0
    fi
    echo "showing logs; press Ctrl-C to stop viewing logs, server keeps running"
    tail -n +1 -f "$LOG"
    exit 0
  fi
  sleep 1
done

echo "ERROR: brain server did not open TCP port $PORT within ${START_TIMEOUT_SECONDS}s." >&2
echo "Last log lines:" >&2
tail -40 "$LOG" >&2 || true
"$TMUX_BIN" kill-session -t "$SESSION" 2>/dev/null || true
exit 1
