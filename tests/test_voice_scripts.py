from __future__ import annotations

import asyncio
import importlib.util
import json
import sys
import wave
from pathlib import Path
from types import SimpleNamespace

import pytest


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "send_wav_to_brain.py"
SPEC = importlib.util.spec_from_file_location("send_wav_to_brain", SCRIPT_PATH)
assert SPEC is not None
send_wav_to_brain = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = send_wav_to_brain
SPEC.loader.exec_module(send_wav_to_brain)


def test_iter_audio_frames_pads_final_frame_and_marks_end() -> None:
    frames = send_wav_to_brain.iter_audio_frames(b"\x01\x02" * 5, frame_samples=4)

    assert len(frames) == 2
    assert frames[0].to_wire()[:4] == b"\x00\x00\x00\x00"
    assert frames[0].flags == 0
    assert len(frames[0].payload) == 8
    assert frames[1].to_wire()[:4] == b"\x00\x01\x01\x00"
    assert frames[1].flags == 1
    assert len(frames[1].payload) == 8
    assert frames[1].payload.endswith(b"\x00" * 6)


def test_read_wav_audio_accepts_16k_mono_pcm(tmp_path: Path) -> None:
    path = tmp_path / "voice.wav"
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(16_000)
        wav.writeframes(b"\x00\x00" * 160)

    audio = send_wav_to_brain.read_wav_audio(path)

    assert audio.duration_ms == 10
    assert audio.pcm == b"\x00\x00" * 160


def test_send_wav_stops_before_audio_upload_on_session_busy(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    path = tmp_path / "voice.wav"
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(16_000)
        wav.writeframes(b"\x00\x00" * 640)

    fake_ws = BusyWebSocket()
    monkeypatch.setitem(sys.modules, "websockets", SimpleNamespace(connect=lambda *_, **__: fake_ws))
    args = SimpleNamespace(
        wav=str(path),
        url="ws://127.0.0.1:8080/sti",
        device_id="voice-test",
        correlation_id="cid",
        frame_samples=640,
        max_utterance_ms=0,
        timeout_s=1.0,
        realtime=False,
    )

    with pytest.raises(RuntimeError, match="server busy"):
        asyncio.run(send_wav_to_brain.send_wav(args))

    assert len(fake_ws.sent) == 1
    start = json.loads(fake_ws.sent[0])
    assert start["type"] == "session_start"


class BusyWebSocket:
    def __init__(self) -> None:
        self.sent: list[str | bytes] = []

    async def __aenter__(self) -> "BusyWebSocket":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None

    async def send(self, message: str | bytes) -> None:
        self.sent.append(message)

    async def recv(self) -> str:
        return json.dumps(
            {
                "v": 1,
                "type": "session_busy",
                "correlation_id": "cid",
                "payload": {"reason": "single_flight", "retry_after_ms": 2000},
            },
            separators=(",", ":"),
        )
