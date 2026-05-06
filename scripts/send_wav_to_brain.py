#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import json
import secrets
import wave
from dataclasses import dataclass
from pathlib import Path
from typing import Any

SAMPLE_RATE_HZ = 16_000
CHANNELS = 1
SAMPLE_WIDTH_BYTES = 2
DEFAULT_FRAME_SAMPLES = 640


@dataclass(frozen=True)
class AudioFrame:
    seq: int
    flags: int
    payload: bytes

    def to_wire(self) -> bytes:
        return self.seq.to_bytes(2, "big") + bytes([self.flags, 0]) + self.payload


@dataclass(frozen=True)
class WavAudio:
    pcm: bytes
    duration_ms: int


def read_wav_audio(path: Path) -> WavAudio:
    with wave.open(str(path), "rb") as wav:
        channels = wav.getnchannels()
        sample_width = wav.getsampwidth()
        sample_rate = wav.getframerate()
        frame_count = wav.getnframes()
        if channels != CHANNELS or sample_width != SAMPLE_WIDTH_BYTES or sample_rate != SAMPLE_RATE_HZ:
            raise ValueError(
                "WAV must be 16 kHz mono pcm_s16le "
                f"(got channels={channels}, sample_width={sample_width}, sample_rate={sample_rate})"
            )
        pcm = wav.readframes(frame_count)
    duration_ms = int(frame_count * 1000 / SAMPLE_RATE_HZ)
    if not pcm:
        raise ValueError("WAV has no audio frames")
    return WavAudio(pcm=pcm, duration_ms=duration_ms)


def iter_audio_frames(pcm: bytes, *, frame_samples: int = DEFAULT_FRAME_SAMPLES) -> list[AudioFrame]:
    if frame_samples <= 0:
        raise ValueError("frame_samples must be positive")
    frame_bytes = frame_samples * SAMPLE_WIDTH_BYTES
    frames: list[AudioFrame] = []
    for seq, offset in enumerate(range(0, len(pcm), frame_bytes)):
        payload = pcm[offset : offset + frame_bytes]
        is_last = offset + frame_bytes >= len(pcm)
        if is_last and len(payload) < frame_bytes:
            payload += b"\x00" * (frame_bytes - len(payload))
        frames.append(AudioFrame(seq=seq & 0xFFFF, flags=1 if is_last else 0, payload=payload))
    return frames


async def send_wav(args: argparse.Namespace) -> None:
    try:
        import websockets
    except ImportError as exc:
        raise RuntimeError("websockets is not installed. Run `.venv/bin/python -m pip install -e '.[dev]'`.") from exc

    wav_audio = read_wav_audio(Path(args.wav))
    frames = iter_audio_frames(wav_audio.pcm, frame_samples=args.frame_samples)
    correlation_id = args.correlation_id or secrets.token_hex(8)
    max_utterance_ms = args.max_utterance_ms or max(1000, wav_audio.duration_ms + 1000)

    start_message: dict[str, Any] = {
        "v": 1,
        "type": "session_start",
        "device_id": args.device_id,
        "correlation_id": correlation_id,
        "payload": {
            "language": "ko",
            "max_utterance_ms": max_utterance_ms,
            "audio_format": {
                "sample_rate": SAMPLE_RATE_HZ,
                "channels": CHANNELS,
                "bit_depth": 16,
                "encoding": "pcm_s16le",
            },
        },
    }
    end_message = {
        "v": 1,
        "type": "session_end",
        "correlation_id": correlation_id,
        "payload": {"audio_frames_sent": len(frames)},
    }

    print(f"Connecting {args.url} correlation_id={correlation_id}", flush=True)
    async with websockets.connect(args.url, open_timeout=args.timeout_s, close_timeout=args.timeout_s) as ws:
        await ws.send(json.dumps(start_message, separators=(",", ":")))
        ack_message = await ws.recv()
        print(f"<- {ack_message}", flush=True)
        try:
            ack = json.loads(ack_message)
        except json.JSONDecodeError as exc:
            raise RuntimeError("server returned non-JSON response before audio upload") from exc
        if ack.get("type") == "session_busy":
            retry_after_ms = ack.get("payload", {}).get("retry_after_ms", 0)
            raise RuntimeError(f"server busy; retry_after_ms={retry_after_ms}")
        if ack.get("type") == "error":
            raise RuntimeError(f"server rejected session_start: {ack}")
        if ack.get("type") != "session_ack":
            raise RuntimeError(f"expected session_ack, got {ack.get('type')}")

        frame_delay_s = args.frame_samples / SAMPLE_RATE_HZ
        estimated_send_s = len(frames) * frame_delay_s if args.realtime else 0
        print(
            f"-> sending frames={len(frames)} audio_ms={wav_audio.duration_ms} "
            f"realtime={args.realtime} estimated_send_s={estimated_send_s:.1f}",
            flush=True,
        )
        for frame in frames:
            await ws.send(frame.to_wire())
            if args.realtime:
                await asyncio.sleep(frame_delay_s)

        print(f"-> sent frames={len(frames)} audio_ms={wav_audio.duration_ms}", flush=True)
        await ws.send(json.dumps(end_message, separators=(",", ":")))

        while True:
            try:
                message = await asyncio.wait_for(ws.recv(), timeout=args.timeout_s)
            except asyncio.TimeoutError:
                raise RuntimeError(f"timed out waiting for server response after {args.timeout_s}s")
            except websockets.exceptions.ConnectionClosed:
                return

            print(f"<- {message}", flush=True)
            try:
                parsed = json.loads(message)
            except json.JSONDecodeError:
                continue
            if parsed.get("type") in {"intent", "error"}:
                return


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Send a 16 kHz mono PCM WAV to the brain /sti WebSocket.")
    parser.add_argument("wav", help="Input WAV path.")
    parser.add_argument("--url", default="ws://127.0.0.1:8080/sti", help="Brain WebSocket URL.")
    parser.add_argument("--device-id", default="voice-test", help="Protocol device_id.")
    parser.add_argument("--correlation-id", default="", help="Protocol correlation_id. Defaults to random.")
    parser.add_argument("--frame-samples", type=int, default=DEFAULT_FRAME_SAMPLES, help="PCM samples per frame.")
    parser.add_argument("--max-utterance-ms", type=int, default=0, help="session_start max_utterance_ms.")
    parser.add_argument("--timeout-s", type=float, default=20.0, help="WebSocket response timeout.")
    parser.add_argument("--fast", action="store_false", dest="realtime", help="Send all frames without realtime delay.")
    parser.set_defaults(realtime=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        asyncio.run(send_wav(args))
    except Exception as exc:
        print(f"ERROR: {exc}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
