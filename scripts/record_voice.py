#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
import wave
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description="Record microphone audio as 16 kHz mono PCM WAV.")
    parser.add_argument("--output", required=True, help="Output WAV path.")
    parser.add_argument("--seconds", type=float, default=3.0, help="Recording duration in seconds.")
    parser.add_argument("--sample-rate", type=int, default=16_000, help="Sample rate in Hz.")
    args = parser.parse_args()

    if args.seconds <= 0:
        parser.error("--seconds must be positive")

    try:
        import sounddevice as sd
    except ImportError:
        print(
            "ERROR: sounddevice is not installed. Install voice test dependencies with:\n"
            "  .venv/bin/python -m pip install sounddevice",
            file=sys.stderr,
        )
        return 1

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    sample_count = int(args.sample_rate * args.seconds)

    print(f"Recording {args.seconds:.1f}s from default microphone -> {output}")
    try:
        recording = sd.rec(sample_count, samplerate=args.sample_rate, channels=1, dtype="int16")
        sd.wait()
    except Exception as exc:
        print(f"ERROR: microphone recording failed: {exc}", file=sys.stderr)
        print("On macOS, check microphone permission for the terminal app.", file=sys.stderr)
        return 1

    with wave.open(str(output), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(args.sample_rate)
        wav.writeframes(recording.tobytes())

    print(f"Wrote {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
