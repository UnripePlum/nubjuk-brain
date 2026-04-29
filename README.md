# nubjuk-brain

MCU P1 verification mock brain.

This module is a development-only WebSocket server used to verify the MCU `sti_engine_brain` happy path before the real Phase 4 brain exists. It intentionally does not implement Whisper, SLM, model loading, grammar, confidence calibration, or any production brain behavior.

The only success path it proves is:

```text
session_start -> session_ack -> binary audio frames -> session_end -> intent=roll_right -> server close
```

## Feature Map

| Area | Files | What it does | Notes |
|------|-------|--------------|-------|
| WebSocket server | `brain/ws_server.py` | Serves `/sti`, receives MCU messages, sends `session_ack`, `session_busy`, `intent`, and `error` responses. | Server closes after `intent`, matching the locked protocol. |
| Message schema | `brain/schema.py` | Validates JSON envelopes and payloads with Pydantic models. | Mirrors `../docs/protocol/mcu-brain.md`; does not change the protocol. |
| Session state | `brain/session.py` | Enforces single-flight, tracks the 5-state session machine, logs state transitions, and releases the lock on cleanup. | States: `IDLE`, `AUDIO_IN`, `PROCESSING`, `DONE`, `CANCELLED`. |
| Mock pipeline | `brain/pipeline/mock.py` | Returns deterministic `intent=roll_right`. | Does not inspect or understand audio. |
| Pipeline interface | `brain/pipeline/base.py` | Defines `StiPipeline`, `SessionOpts`, `StiResult`, and `StiError`. | Matches `INTERFACES.md`. |
| Runtime config | `brain/config.py` | Reads mock intent, confidence, and artificial delay from environment variables. | Validates confidence and delay. |
| Runner script | `run_mock_brain.sh` | Runs the server through `.venv`. | Supports host/port overrides. |
| Tests | `tests/` | Covers schema examples, session state, WebSocket happy path, busy response, cleanup, config validation, and pipeline error handling. | Run `pytest` before shipping changes. |
| Follow-up tracking | `TODOS.md` | Captures the post-hardware-pass decision about strict binary validation. | Do not enable strict binary failure before first MCU bring-up. |

## Protocol Behavior

### Accepted Client Messages

- `session_start`
- binary audio frame
- `session_end`
- `session_cancel`

### Server Responses

- `session_ack`
- `session_busy`
- `intent`
- `error`

### Binary Audio Handling

The mock parses the 4-byte frame header:

```text
[seq_u16 BE][flags_u8][reserved_u8][PCM payload]
```

It counts frames and payload bytes, logs warnings for suspicious headers, and immediately discards the PCM payload. It does not buffer audio.

Warnings do not fail the first MCU happy-path session. After hardware bring-up succeeds, revisit `TODOS.md` and decide whether these warnings should become strict `schema_invalid` errors.

## Runtime Config

| Variable | Default | Meaning |
|----------|---------|---------|
| `MOCK_BRAIN_HOST` | `0.0.0.0` | Host used by `run_mock_brain.sh`. |
| `MOCK_BRAIN_PORT` | `8080` | Port used by `run_mock_brain.sh`. |
| `MOCK_BRAIN_INTENT` | `roll_right` | Intent returned by `MockPipeline`. |
| `MOCK_BRAIN_CONFIDENCE` | `0.92` | Confidence returned with the mock intent. |
| `MOCK_BRAIN_DELAY_MS` | `0` | Artificial processing delay for cleanup/disconnect testing. |

## Run

From this repo root, use the repo script:

```bash
./run_mock_brain.sh
```

Override host or port if needed:

```bash
MOCK_BRAIN_HOST=127.0.0.1 MOCK_BRAIN_PORT=18080 ./run_mock_brain.sh
```

Equivalent direct command:

```bash
.venv/bin/python -m uvicorn brain.ws_server:app --host 0.0.0.0 --port 8080
```

## MCU Connection

If this machine is on the same LAN as the MCU, point the MCU brain URL at:

```text
ws://<host-ip>:8080/sti
```

Replace `<host-ip>` with this machine's IP address on the same LAN as the MCU. On macOS, one common way to check Wi-Fi is:

```bash
ipconfig getifaddr en0
```

Expected MCU serial result:

```text
intent=roll_right
```

## Test

```bash
.venv/bin/python -m pytest
```

Current coverage categories:

- schema examples from the locked protocol
- generated response envelope shape
- invalid message validation
- single-flight session behavior
- cancel and disconnect cleanup
- WebSocket happy path
- WebSocket `session_busy`
- pipeline error to `error` response
- config validation

## Out of Scope

Do not add these before the Phase 4 gate is explicitly satisfied:

- Whisper
- SLM
- VAD
- grammar
- confidence calibration
- model downloads
- `models/`
- `eval/`
- systemd service
- production deployment
- changes to `../docs/protocol/mcu-brain.md`
- changes to `mcu/**`
- changes to `schemas/**`

## Phase Boundary

This mock is a P1 verification tool. It is not the start of the real Phase 4 brain.

Phase 4 remains blocked until the checklist in `PHASES.md` is satisfied.
