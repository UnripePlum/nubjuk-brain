# nubjuk-brain

Development-only mock brain for MCU P1 STI verification.

This module intentionally does not implement Whisper, SLM, model loading, grammar, confidence calibration, or Phase 4 brain behavior. It only serves the locked MCU-brain WebSocket contract well enough for the MCU happy path:

```text
session_start -> session_ack -> binary audio frames -> session_end -> intent=roll_right -> server close
```

## Run

```bash
uvicorn brain.ws_server:app --host 0.0.0.0 --port 8080
```

Optional environment variables:

- `MOCK_BRAIN_INTENT`, default `roll_right`
- `MOCK_BRAIN_CONFIDENCE`, default `0.92`
- `MOCK_BRAIN_DELAY_MS`, default `0`

## Test

```bash
python -m pytest
```

