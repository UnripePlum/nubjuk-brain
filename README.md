# nubjuk-brain

Stateful STI WebSocket brain for Nubjuk.

The server talks to the MCU `sti_engine_brain` client over the locked `/sti` protocol, receives 16 kHz mono PCM audio frames, and returns a motion `intent`. It supports two runtime pipelines:

- `mock`: deterministic MCU happy-path verification.
- `moonshine_tiny_ko`: real voice path using Moonshine tiny-ko ASR, a brain-owned motion intent catalog, and an optional Qwen 3.5 0.8B GGUF SLM resolver.

The main flow is:

```text
session_start -> session_ack -> binary audio frames -> session_end -> ASR/catalog/SLM -> intent -> server close
```

## Feature Map

| Area | Files | What it does | Notes |
|------|-------|--------------|-------|
| WebSocket server | `brain/ws_server.py` | Serves `/sti`, receives MCU messages, sends `session_ack`, `session_busy`, `intent`, and `error` responses. | Server closes after `intent`, matching the locked protocol. |
| Message schema | `brain/schema.py` | Validates JSON envelopes and payloads with Pydantic models. | Mirrors `../docs/protocol/mcu-brain.md`; does not change the protocol. |
| Session state | `brain/session.py` | Enforces single-flight, tracks the 5-state session machine, logs state transitions, and releases the lock on cleanup. | States: `IDLE`, `AUDIO_IN`, `PROCESSING`, `DONE`, `CANCELLED`. |
| Mock pipeline | `brain/pipeline/mock.py` | Returns deterministic `intent=roll_right`. | Does not inspect or understand audio. |
| Voice pipeline | `brain/pipeline/moonshine_tiny_ko.py` | Buffers PCM, transcribes with Moonshine tiny-ko, resolves intent through catalog plus optional Qwen SLM. | Selected with `BRAIN_PIPELINE=moonshine_tiny_ko`. |
| Intent catalog | `brain/intent/`, `recipes/nubjuk_motion_catalog.json` | Validates motion aliases, ASR-noise corrections, Korean phonetic matching, and catalog versions. | `asr_noise` is exact-only so bad partial matches do not trigger motion. |
| Qwen resolver | `brain/pipeline/qwen_slm.py` | Calls `llama-cli` with a constrained intent prompt and only accepts catalog intent ids. | SLM can raise confidence only when it agrees with deterministic catalog matching. |
| Pipeline interface | `brain/pipeline/base.py` | Defines `StiPipeline`, `SessionOpts`, `StiResult`, and `StiError`. | Matches `INTERFACES.md`. |
| Runtime config | `brain/config.py` | Reads mock, Moonshine, Qwen, catalog, and WebSocket settings from environment variables. | Validates confidence, timeouts, and supported model choices. |
| Runner script | `run_mock_brain.sh` | Runs the server through `.venv`. | Supports host/port overrides. |
| Background runner | `start_brain_server.sh` | Starts the real voice brain defaults in a `tmux` session. | Writes `.tmp/brain-server.log`. |
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

The server parses the 4-byte frame header:

```text
[seq_u16 BE][flags_u8][reserved_u8][PCM payload]
```

Expected payload is 40 ms of 16 kHz mono PCM S16LE: `640 samples * 2 bytes = 1280 bytes`.

The WebSocket handler does not run ASR while receiving frames. It puts binary frames into an internal `asyncio.Queue(maxsize=256)` with `put_nowait()`, and a separate worker calls `SessionManager.feed_audio(frame)`. This keeps TCP receive consumption separate from audio buffering and ASR work.

Warnings such as non-monotonic sequence numbers, reserved bytes, or partial PCM payloads are logged as `frame_warning` and do not fail the session yet. After hardware bring-up succeeds, revisit `TODOS.md` and decide whether these warnings should become strict `schema_invalid` errors.

## Runtime Config

| Variable | Default | Meaning |
|----------|---------|---------|
| `MOCK_BRAIN_HOST` | `0.0.0.0` | Host used by `run_mock_brain.sh`. |
| `MOCK_BRAIN_PORT` | `8080` | Port used by `run_mock_brain.sh`. |
| `BRAIN_WS_PROTOCOL` | `websockets` | Uvicorn WebSocket protocol implementation. |
| `BRAIN_WS_MAX_QUEUE` | `256` | Uvicorn WebSocket incoming message queue length. Raised above the default to absorb MCU audio bursts. |
| `BRAIN_WS_MAX_SIZE` | `1048576` | Uvicorn WebSocket max individual message size in bytes. |
| `BRAIN_PIPELINE` | `mock` | Runtime pipeline: `mock` or `moonshine_tiny_ko`. |
| `BRAIN_TMUX_SESSION` | `nubjuk-brain` | tmux session name used by `start_brain_server.sh`. |
| `BRAIN_SERVER_LOG` | `.tmp/brain-server.log` | Log file used by `start_brain_server.sh`. |
| `BRAIN_NO_TAIL` | `0` | Set to `1` if `start_brain_server.sh` should start the tmux server without following logs. |
| `MOCK_BRAIN_INTENT` | `roll_right` | Intent returned by `MockPipeline`. |
| `MOCK_BRAIN_CONFIDENCE` | `0.92` | Confidence returned with the mock intent. |
| `MOCK_BRAIN_DELAY_MS` | `0` | Artificial processing delay for cleanup/disconnect testing. |
| `INTENT_CATALOG_PATH` | unset | Optional recipe catalog path. `start_brain_server.sh` defaults it to `recipes/nubjuk_motion_catalog.json`. |
| `MOONSHINE_MAX_AUDIO_MS` | `5000` | Maximum accumulated audio per session. |
| `MOONSHINE_UNKNOWN_CONFIDENCE` | `0.2` | Confidence for unmatched text. |
| `BRAIN_SLM_ENABLED` | `true` | Enables the Qwen SLM resolver for the Moonshine pipeline. |
| `LLAMA_CLI` | `.tools/llama.cpp/bin/llama-cli` | llama.cpp CLI used by Qwen resolver. |
| `QWEN35_MODEL_PATH` | `models/qwen3.5-0.8b/Qwen3.5-0.8B-Q4_K_M.gguf` | Qwen 3.5 0.8B GGUF model path. |
| `BRAIN_SLM_TIMEOUT_MS` | `5000` | SLM subprocess timeout. |

## Run

For the MCU voice path, start the brain server in the background with one command:

```bash
./start_brain_server.sh
```

The command starts the server in `tmux` and immediately follows `.tmp/brain-server.log` in the same terminal. Press `Ctrl-C` to stop viewing logs; the server keeps running.

Shutdown:

```bash
tmux kill-session -t nubjuk-brain
```

From this repo root, use the repo script:

```bash
./run_mock_brain.sh
```

The foreground runner defaults to `BRAIN_PIPELINE=mock`. To run the same voice path without tmux:

```bash
BRAIN_PIPELINE=moonshine_tiny_ko \
INTENT_CATALOG_PATH=recipes/nubjuk_motion_catalog.json \
./run_mock_brain.sh
```

Override host or port if needed:

```bash
MOCK_BRAIN_HOST=127.0.0.1 MOCK_BRAIN_PORT=18080 ./run_mock_brain.sh
```

Equivalent direct command:

```bash
.venv/bin/python -m uvicorn brain.ws_server:app --host 0.0.0.0 --port 8080 --ws websockets --ws-max-queue 256 --ws-max-size 1048576
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

Expected logs when the MCU connects:

```text
ws_connection_accepted
audio_frame_enqueued
audio_worker_feed
asr_answer
slm_answer
intent_match
intent_send
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
- intent catalog alias, ASR-noise, and phonetic matching
- Moonshine pipeline fallback and SLM safety rules
- WebSocket receive-loop backpressure protection
- runner scripts and voice-test helpers

## Model Setup

Install local Qwen dependencies when using the SLM path:

```bash
scripts/install_llama_cli.sh
scripts/install_qwen35_0_8b.sh
scripts/qwen35_smoke_test.sh
```

Moonshine tiny-ko loads through the `moonshine-voice` package. If a custom model directory is needed, set `MOONSHINE_MODEL_DIR`.

## More Docs

- `ARCHITECTURE.md`: runtime architecture, catalog matching rules, and operational notes.
- `INTERFACES.md`: internal pipeline and session manager interfaces.
- `PHASES.md`: phase boundaries and gates.
- `TODOS.md`: follow-up decisions after hardware bring-up.

## Out of Scope

Do not change these from this repo unless the corresponding project owner explicitly asks:

- `../docs/protocol/mcu-brain.md`
- `mcu/**`
- `schemas/**`
- production deployment setup

## Phase Boundary

The mock pipeline remains available for P1 verification. The Moonshine/Qwen path is the current real-voice prototype and still needs Phase 4 gates such as latency, memory, systemd, and soak verification before production use.
