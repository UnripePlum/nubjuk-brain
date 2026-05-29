# Graph Report - brain  (2026-05-29)

## Corpus Check
- 45 files · ~18,594 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 687 nodes · 1767 edges · 43 communities (28 shown, 15 thin omitted)
- Extraction: 68% EXTRACTED · 32% INFERRED · 0% AMBIGUOUS · INFERRED: 567 edges (avg confidence: 0.52)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `6fccd428`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- [[_COMMUNITY_Community 0|Community 0]]
- [[_COMMUNITY_Community 1|Community 1]]
- [[_COMMUNITY_Community 2|Community 2]]
- [[_COMMUNITY_Community 3|Community 3]]
- [[_COMMUNITY_Community 4|Community 4]]
- [[_COMMUNITY_Community 5|Community 5]]
- [[_COMMUNITY_Community 6|Community 6]]
- [[_COMMUNITY_Community 7|Community 7]]
- [[_COMMUNITY_Community 8|Community 8]]
- [[_COMMUNITY_Community 9|Community 9]]
- [[_COMMUNITY_Community 10|Community 10]]
- [[_COMMUNITY_Community 11|Community 11]]
- [[_COMMUNITY_Community 12|Community 12]]
- [[_COMMUNITY_Community 13|Community 13]]
- [[_COMMUNITY_Community 14|Community 14]]
- [[_COMMUNITY_Community 15|Community 15]]
- [[_COMMUNITY_Community 16|Community 16]]
- [[_COMMUNITY_Community 17|Community 17]]
- [[_COMMUNITY_Community 18|Community 18]]
- [[_COMMUNITY_Community 19|Community 19]]
- [[_COMMUNITY_Community 20|Community 20]]
- [[_COMMUNITY_Community 21|Community 21]]
- [[_COMMUNITY_Community 22|Community 22]]
- [[_COMMUNITY_Community 24|Community 24]]
- [[_COMMUNITY_Community 25|Community 25]]
- [[_COMMUNITY_Community 26|Community 26]]
- [[_COMMUNITY_Community 27|Community 27]]
- [[_COMMUNITY_Community 31|Community 31]]
- [[_COMMUNITY_Community 32|Community 32]]
- [[_COMMUNITY_Community 33|Community 33]]
- [[_COMMUNITY_Community 34|Community 34]]
- [[_COMMUNITY_Community 35|Community 35]]
- [[_COMMUNITY_Community 36|Community 36]]
- [[_COMMUNITY_Community 37|Community 37]]
- [[_COMMUNITY_Community 38|Community 38]]
- [[_COMMUNITY_Community 39|Community 39]]
- [[_COMMUNITY_Community 40|Community 40]]
- [[_COMMUNITY_Community 41|Community 41]]
- [[_COMMUNITY_Community 42|Community 42]]

## God Nodes (most connected - your core abstractions)
1. `StiError` - 100 edges
2. `SessionOpts` - 74 edges
3. `MockBrainConfig` - 58 edges
4. `MoonshineTinyKoRulesPipeline` - 58 edges
5. `SessionManager` - 57 edges
6. `MoonshineTinyKoConfig` - 54 edges
7. `MockPipeline` - 51 edges
8. `IntentCatalog` - 51 edges
9. `StiResult` - 41 edges
10. `StiPipeline` - 41 edges

## Surprising Connections (you probably didn't know these)
- `give_hand Intent` --conceptually_related_to--> `MCU sti_engine_brain Client`  [AMBIGUOUS]
  recipes/nubjuk_motion_catalog.json → ARCHITECTURE.md
- `QwenSlmIntentResolver` --implements--> `Qwen SLM Resolver`  [EXTRACTED]
  brain/pipeline/qwen_slm.py → ARCHITECTURE.md
- `Default Motion Catalog` --semantically_similar_to--> `Nubjuk Motion Catalog`  [INFERRED] [semantically similar]
  brain/intent/default_catalog.json → recipes/nubjuk_motion_catalog.json
- `Path` --uses--> `IntentCatalog`  [INFERRED]
  tests/test_intent_catalog.py → brain/intent/catalog.py
- `MockPipeline` --implements--> `Mock Pipeline Runtime`  [EXTRACTED]
  brain/pipeline/mock.py → ARCHITECTURE.md

## Hyperedges (group relationships)
- **STI Utterance Processing Flow** — architecture_locked_sti_protocol, ws_server_sti_handler, session_session_manager, pipeline_base_sti_pipeline, schema_server_message_models [EXTRACTED 1.00]
- **Voice Intent Resolution Safety Chain** — moonshine_moonshine_tiny_ko_rules_pipeline, moonshine_tiny_ko_transcriber, catalog_intent_catalog, qwen_qwen_slm_intent_resolver, architecture_slm_safety_rule [EXTRACTED 1.00]
- **Audio Backpressure and Cleanup Pattern** — ws_server_audio_feed_worker, architecture_audio_backpressure_queue, session_session_manager, architecture_cleanup_guarantee, qwen_subprocess_cancel [INFERRED 0.82]
- **Local Qwen SLM Stack** — install_llama_cli_llama_cli_installer, install_llama_cli_local_llama_cli_symlink, install_qwen35_qwen_model_installer, install_qwen35_qwen35_gguf_model, qwen35_smoke_test_qwen_smoke_test, test_qwen_slm_intent_prompt_builder, test_config_moonshine_env_config [INFERRED 0.85]
- **Voice WAV to STI Flow** — record_voice_record_voice_main, voice_test_voice_test_flow, send_wav_to_brain_send_wav, send_wav_to_brain_session_start_message, send_wav_to_brain_session_end_message, test_schema_protocol_examples_protocol_examples, test_ws_happy_path_websocket_happy_path [INFERRED 0.90]
- **Single-Flight Busy Protocol** — send_wav_to_brain_session_busy_handling, test_voice_scripts_busy_prevents_audio_upload, test_schema_protocol_examples_protocol_examples, test_session_singleflight_singleflight_lock, test_ws_happy_path_lock_cleanup [INFERRED 0.86]

## Communities (43 total, 15 thin omitted)

### Community 0 - "Community 0"
Cohesion: 0.06
Nodes (91): ABC, array, MoonshineTinyKoConfig, bytes, str, bytes, SessionOpts, StiResult (+83 more)

### Community 1 - "Community 1"
Cohesion: 0.14
Nodes (30): AudioFormat, ErrorMessage, ErrorPayload, extract_correlation_id(), IntentMessage, IntentPayload, make_error(), make_intent() (+22 more)

### Community 2 - "Community 2"
Cohesion: 0.09
Nodes (81): MockBrainConfig, RuntimeConfig, ProtocolValidationError, ErrorCode, SessionCancelMessage, SessionEndMessage, SessionStartMessage, r"""Single-flight session manager for the P1 mock brain.      State machine: (+73 more)

### Community 3 - "Community 3"
Cohesion: 0.08
Nodes (41): BaseModel, Any, bool, float, int, Path, str, candidates() (+33 more)

### Community 4 - "Community 4"
Cohesion: 0.07
Nodes (38): llama-cli macOS Arm64 Installer, llama.cpp b8994 macOS Arm64 Release Asset, Local llama-cli Symlink, Qwen Model Manifest, Qwen3.5-0.8B Q4_K_M GGUF Model, Qwen3.5 0.8B GGUF Installer, Qwen3.5 Smoke Test, Roll Right Intent Prompt (+30 more)

### Community 5 - "Community 5"
Cohesion: 0.10
Nodes (30): _bool_from_env(), _float_from_env(), from_env(), _int_from_env(), load_config_from_env(), bool, float, int (+22 more)

### Community 6 - "Community 6"
Cohesion: 0.09
Nodes (29): 16 kHz Mono PCM WAV Recorder, record_voice Main, AudioFrame Wire Frame, iter_audio_frames, send_wav, session_busy Handling, session_end Message, session_start Message (+21 more)

### Community 7 - "Community 7"
Cohesion: 0.19
Nodes (17): int, IntentCatalog, MoonshineTinyKoConfig, str, build_intent_prompt(), compact_slm_output(), extract_slm_completion(), parse_intent_from_slm_output() (+9 more)

### Community 8 - "Community 8"
Cohesion: 0.18
Nodes (17): Mock Pipeline Runtime, load_config_from_env, MockBrainConfig, MoonshineTinyKoConfig, RuntimeConfig, StiPipeline Interface Contract, MoonshineTinyKoRulesPipeline, PCM Audio Helpers (+9 more)

### Community 9 - "Community 9"
Cohesion: 0.20
Nodes (7): BusyWebSocket, bytes, MonkeyPatch, Path, str, test_read_wav_audio_accepts_16k_mono_pcm(), test_send_wav_stops_before_audio_upload_on_session_busy()

### Community 10 - "Community 10"
Cohesion: 0.21
Nodes (13): Audio Backpressure Queue, Binary Audio Frame Format, Single Utterance Flow, External WebSocket Contract, Client Message Models, parse_client_message, Response Builder Functions, Server Message Models (+5 more)

### Community 11 - "Community 11"
Cohesion: 0.21
Nodes (12): load_intent_catalog, IntentCandidate, IntentCatalog, IntentCatalogData, normalize_text, phonetic_similarity, PronunciationCandidate, match_intent (+4 more)

### Community 12 - "Community 12"
Cohesion: 0.18
Nodes (9): IntentRecipe, idle Intent, Nubjuk Motion Catalog, roll_left Intent, roll_right Intent, sit Intent, stand Intent, surprise Intent (+1 more)

### Community 13 - "Community 13"
Cohesion: 0.25
Nodes (11): Cleanup Guarantee, Phase 4 Latency Budget, SessionState FSM, Single-flight Concurrency Model, Locked Behavior Contract, SessionManager Interface Contract, Korean Evaluation Harness, Phase 4 Gate (+3 more)

### Community 14 - "Community 14"
Cohesion: 0.22
Nodes (10): Moonshine Tiny-Ko Voice Runtime, Brain-owned Motion Recipe Catalog, Phase-based Brain Activation, Qwen SLM Resolver, SLM Catalog Agreement Safety Rule, IntentMatch, Default Motion Catalog, SLM Acceptance Gate (+2 more)

### Community 15 - "Community 15"
Cohesion: 0.22
Nodes (9): Locked /sti Protocol, MCU sti_engine_brain Client, Nubjuk Brain, RPi 4GB Runtime, STI WebSocket Service, Systemd Deployment, Brain Module Isolation Rules, Claude Brain Working Rules (+1 more)

### Community 16 - "Community 16"
Cohesion: 0.50
Nodes (7): apply_wpa2(), apply_wpa3(), require_nmcli(), restart_hotspot(), show_status(), usage(), switch_rpi_hotspot_security.sh script

### Community 17 - "Community 17"
Cohesion: 0.50
Nodes (4): Frame Warning Policy, Session Frame Warning Logger, Strict Binary Validation Follow-up, Tail Partial Frame Decision

### Community 34 - "Community 34"
Cohesion: 0.07
Nodes (27): Accepted Client Messages, Binary Audio Handling, code:text (session_start -> session_ack -> binary audio frames -> sessi), code:bash (ipconfig getifaddr en0), code:text (ws_connection_accepted), code:bash (.venv/bin/python -m pytest), code:bash (scripts/install_llama_cli.sh), code:text ([seq_u16 BE][flags_u8][reserved_u8][PCM payload]) (+19 more)

### Community 35 - "Community 35"
Cohesion: 0.09
Nodes (21): Brain-owned motion recipe catalog, Brain — 모듈 아키텍처, code:mermaid (flowchart LR), code:mermaid (sequenceDiagram), code:mermaid (stateDiagram-v2), code:block4 (audio frames (PCM 16kHz mono)), code:json ({), code:block6 (┌──────────────────────────────────┐) (+13 more)

### Community 36 - "Community 36"
Cohesion: 0.09
Nodes (21): 4.10 Failure modes 명시 처리, 4.1 의존성 셋업 (codex fix: ASR/SLM 통합 방식 commit), 4.2 모델 준비 (codex fix: 메모리 budget 현실적으로), 4.3 WS 서버 (FastAPI), 4.4 SessionManager (single-flight, 명시적 state machine), 4.5 Pipeline `WhisperLlamaPipeline` (codex fix: grammar 보장 정확성, confidence eval), 4.6 Schema validator (`schema.py`), 4.7 평가 하네스 (+13 more)

### Community 37 - "Community 37"
Cohesion: 0.18
Nodes (10): nubjuk-brain — Claude Code 작업 규칙 (brain 세션 전용), 🚧 격리 규칙 (cwd = brain/), 격리가 깨지는 신호 (즉시 STOP, 사용자 확인), 내부 인터페이스 (권장 형태, 시그니처 잠금), 모듈 책임 (한 줄), 문서 인덱스, 외부 통신 계약 (잠금, 가장 중요), 작업 원칙 (+2 more)

### Community 39 - "Community 39"
Cohesion: 0.22
Nodes (8): `brain/brain/pipeline/base.py` — STI Pipeline 추상 (권장), `brain/brain/session.py` — Single-flight 매니저, Brain — 인터페이스 정의, code:python (from abc import ABC, abstractmethod), code:python (from enum import Enum), code:block3 (IDLE → AUDIO_IN          (session_start 수락 후, lock acquired)), State transitions (잠금 — 이 상태 모델은 변경 X), 외부 계약 (잠금)

### Community 40 - "Community 40"
Cohesion: 0.50
Nodes (3): Brain P1 Mock Strict Binary Validation Follow-up, TODOS, Voice Brain Tail Partial Frame Decision

## Ambiguous Edges - Review These
- `MCU sti_engine_brain Client` → `give_hand Intent`  [AMBIGUOUS]
  ARCHITECTURE.md · relation: conceptually_related_to

## Knowledge Gaps
- **127 isolated node(s):** `run_mock_brain.sh script`, `start_brain_server.sh script`, `MonkeyPatch`, `bytes`, `PreToolUse` (+122 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **15 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **What is the exact relationship between `MCU sti_engine_brain Client` and `give_hand Intent`?**
  _Edge tagged AMBIGUOUS (relation: conceptually_related_to) - confidence is low._
- **Why does `StiError` connect `Community 0` to `Community 2`, `Community 38`, `Community 7`?**
  _High betweenness centrality (0.069) - this node is a cross-community bridge._
- **Why does `IntentCatalog` connect `Community 0` to `Community 3`, `Community 7`?**
  _High betweenness centrality (0.046) - this node is a cross-community bridge._
- **Why does `MoonshineTinyKoRulesPipeline` connect `Community 0` to `Community 2`?**
  _High betweenness centrality (0.038) - this node is a cross-community bridge._
- **Are the 78 inferred relationships involving `StiError` (e.g. with `int` and `bytes`) actually correct?**
  _`StiError` has 78 INFERRED edges - model-reasoned connections that need verification._
- **Are the 62 inferred relationships involving `SessionOpts` (e.g. with `int` and `bytes`) actually correct?**
  _`SessionOpts` has 62 INFERRED edges - model-reasoned connections that need verification._
- **Are the 32 inferred relationships involving `MockBrainConfig` (e.g. with `int` and `bytes`) actually correct?**
  _`MockBrainConfig` has 32 INFERRED edges - model-reasoned connections that need verification._