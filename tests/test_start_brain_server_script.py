from __future__ import annotations

from pathlib import Path


def test_start_brain_server_script_uses_real_voice_defaults() -> None:
    script = Path(__file__).resolve().parents[1] / "start_brain_server.sh"
    content = script.read_text()

    assert "BRAIN_PIPELINE:-moonshine_tiny_ko" in content
    assert "INTENT_CATALOG_PATH:-recipes/nubjuk_motion_catalog.json" in content
    assert "BRAIN_WS_MAX_QUEUE:-256" in content
    assert "BRAIN_WS_PROTOCOL:-websockets" in content
    assert "BRAIN_WS_MAX_SIZE:-1048576" in content
    assert "BRAIN_TMUX_SESSION:-nubjuk-brain" in content
    assert "BRAIN_TMUX_TERM" in content
    assert "xterm-256color" in content
    assert 'TERM="$TMUX_TERM" "$TMUX_BIN" new-session' in content
    assert ".tmp/brain-server.log" in content
    assert "./run_mock_brain.sh" in content
    assert "BRAIN_NO_TAIL:-0" in content
    assert 'tail -n +1 -f "$LOG"' in content
