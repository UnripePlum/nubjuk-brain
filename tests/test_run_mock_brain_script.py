from __future__ import annotations

from pathlib import Path


def test_runner_increases_uvicorn_websocket_queue() -> None:
    script = Path(__file__).resolve().parents[1] / "run_mock_brain.sh"
    content = script.read_text(encoding="utf-8")

    assert 'WS_PROTOCOL="${BRAIN_WS_PROTOCOL:-websockets}"' in content
    assert 'WS_MAX_QUEUE="${BRAIN_WS_MAX_QUEUE:-256}"' in content
    assert "--ws-max-queue" in content
    assert '"$WS_MAX_QUEUE"' in content
