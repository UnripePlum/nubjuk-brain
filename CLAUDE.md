# nubjuk-brain — Claude Code 작업 규칙 (brain 세션 전용)

## 모듈 책임 (한 줄)
RPi 4GB에서 Whisper.cpp + SLM(EXAONE/Qwen) 실행. mcu의 `sti_engine_brain` 클라이언트와 stateful WS 세션으로 통신하는 STI 서비스.

> ⚠️ **Phase 1~3에는 brain이 활성화되지 않습니다.** 디렉토리만 존재, 코드 작성은 Phase 4 진입 결정 후.

상세 아키텍처는 `ARCHITECTURE.md` 참고.

---

## 🚧 격리 규칙 (cwd = brain/)

| 허용 | 금지 |
|------|------|
| `brain/**` (이 모듈 전체 read/write) | `mcu/**`, `viewer/**` (다른 모듈) |
| `docs/**` (read; protocol/*.md는 잠금) | `schemas/**` (잠금) |
| | `README.md`, root `CLAUDE.md` |

mcu의 동작이 궁금하면 **`docs/protocol/mcu-brain.md`만** 참고 — mcu 코드를 보지 마세요.

---

## 🔒 잠금 정책

### 외부 통신 계약 (잠금, 가장 중요)
- `docs/protocol/mcu-brain.md` — ESP↔brain WS STI 서비스 계약 (stateful session, single-flight, binary up + JSON down)

→ **이 계약 변경은 mcu의 `sti_engine_brain.c`와 동시 변경 필요.** 사용자 승인 없이 변경 X.

### 내부 인터페이스 (권장 형태, 시그니처 잠금)
- `brain/brain/pipeline/base.py` — `StiPipeline` 추상 (start_session/feed_audio/finish_session/cancel_session)
- `brain/brain/session.py` — `SessionManager` + `SessionState` enum

→ **State machine은 잠금** (IDLE/AUDIO_IN/PROCESSING/DONE/CANCELLED 5상태). 다른 부분은 변경 자유.

→ **정확한 시그니처는 `INTERFACES.md`**.

### 행동 contract (잠금)
- Single-flight: 동시 1 세션만, 두 번째는 `session_busy` 응답
- Cleanup 보장: 어느 종료 경로에서든 lock release + pipeline cancel + subprocess kill
- Schema 위반은 recoverable (close X) — `error{code:"schema_invalid"}` 후 WS 유지
- Confidence는 eval 기반 calibration (magic number X)
- Grammar는 JSON parser-valid + enum 강제만 보장 (의미 유효성 X)

---

## 작업 원칙

1. **WS 프로토콜 시그니처를 바꿔야 한다고 느끼면 STOP** — 사용자 확인 + mcu 동시 변경
2. **새 ASR/SLM 시도는 새 Pipeline 구현체로** — `WhisperLlamaPipeline` 외 새 클래스 추가
3. **Phase 진행은 `PHASES.md` 따름** — Phase 4 진입 체크리스트 5항목 모두 yes
4. **모든 메시지는 pydantic 모델로 검증** — markdown은 human-doc, pydantic이 runtime SoT
5. **테스트 가능성 우선**: `MockPipeline` 항상 동시 존재
6. **워킹 디렉토리 밖은 손대지 말 것** (위 격리 규칙)

### 격리가 깨지는 신호 (즉시 STOP, 사용자 확인)

- WS protocol (`docs/protocol/mcu-brain.md`) 변경 필요
- `schemas/` 변경 필요
- `SessionState` 머신 5상태 모델 변경 필요
- mcu 동작 추측 / 새 메시지 타입 발명 필요
- Phase 4 진입 결정 (체크리스트 미통과 상태)

---

## 문서 인덱스

| 파일 | 내용 |
|------|------|
| `CLAUDE.md` (이 파일) | 작업 규칙 + 잠금 정책 |
| `ARCHITECTURE.md` | 컴포넌트 다이어그램, 처리 흐름, 메모리 배치, latency 예산, failure 매트릭스 |
| `INTERFACES.md` | 권장 Python 인터페이스 (StiPipeline, SessionManager) |
| `PHASES.md` | Phase 0~6 구현 task + Gate 기준 + 진입 체크리스트 |
| `docs/protocol/mcu-brain.md` | ESP↔brain WS 계약 (잠금, read-only) |
