# Brain — 인터페이스 정의

> 🔒 외부 통신 계약은 `docs/protocol/mcu-brain.md`에서 잠금. **내부 모듈 인터페이스는 자유** — 다음은 권장 형태.

brain은 mcu의 `sti_engine_brain` 클라이언트와만 통신하는 STI 서비스. 외부 API 표면은 WS 프로토콜 하나뿐이며 그 외 인터페이스는 모두 모듈 내부 결정.

## `brain/brain/pipeline/base.py` — STI Pipeline 추상 (권장)

```python
from abc import ABC, abstractmethod
from dataclasses import dataclass

@dataclass
class StiResult:
    intent: str
    slots: dict
    confidence: float           # eval 기반 보정값, magic number X (PHASES.md §4.5 참고)
    raw_text: str | None
    asr_ms: int
    slm_ms: int

@dataclass
class SessionOpts:
    correlation_id: str
    max_utterance_ms: int
    language: str = "ko"

class StiError(Exception):
    """asr_failed / slm_failed / timeout / internal."""
    code: str

class StiPipeline(ABC):
    @abstractmethod
    async def start_session(self, opts: SessionOpts) -> None: ...

    @abstractmethod
    async def feed_audio(self, pcm: bytes) -> None: ...   # 16kHz mono 16-bit LE

    @abstractmethod
    async def finish_session(self) -> StiResult: ...      # raises StiError on failure

    @abstractmethod
    async def cancel_session(self) -> None: ...           # idempotent
```

원래 Phase 4 target architecture에서 고려했던 구현체:
- `WhisperLlamaPipeline` — 초기 계획의 Whisper.cpp + llama.cpp grammar 구현체. 현재 기본값은 아니다.
- `MockPipeline` — 테스트, 사전 정의된 결과 반환
- (향후) `WhisperRulesPipeline` — Whisper + rule-based intent matching (SLM 없는 경량 변형)

현재 구현체:
- `MockPipeline` — MCU happy-path 검증용. 오디오 내용을 보지 않고 설정된 intent를 반환한다.
- `MoonshineTinyKoRulesPipeline` — Moonshine tiny-ko ASR, brain-owned `IntentCatalog`, 선택적 Qwen SLM resolver를 연결한다.
- `QwenSlmIntentResolver` — `llama-cli` subprocess로 Qwen 3.5 0.8B GGUF를 호출하고 catalog에 존재하는 intent id만 채택한다.

## `brain/brain/session.py` — Single-flight 매니저

```python
from enum import Enum

class SessionState(Enum):
    IDLE = "idle"
    AUDIO_IN = "audio_in"           # session_start 받은 후 audio frame 수신 중
    PROCESSING = "processing"       # session_end 후 pipeline 실행
    DONE = "done"
    CANCELLED = "cancelled"

class SessionManager:
    """동시 1 세션만 활성. 두 번째는 session_busy 응답."""

    async def try_start(self, opts: SessionOpts, ws) -> bool:
        # asyncio.Lock으로 진입 시도. 이미 활성이면 False (busy 응답하라)
        ...

    async def feed_audio(self, frame: bytes) -> None: ...
    async def finish(self) -> StiResult: ...
    async def cancel(self) -> None: ...    # 어느 상태에서든 안전한 cleanup 보장
```

### State transitions (잠금 — 이 상태 모델은 변경 X)

```
IDLE → AUDIO_IN          (session_start 수락 후, lock acquired)
AUDIO_IN → PROCESSING    (session_end 수신 후)
AUDIO_IN | PROCESSING → CANCELLED   (session_cancel 또는 WS close)
PROCESSING → DONE        (intent or error 송신 완료)
DONE | CANCELLED → IDLE  (cleanup 완료 후, lock released)
```

**Cleanup 보장**:
- 어느 종료 경로(DONE/CANCELLED)에서든 lock release + pipeline `cancel_session()` 호출
- WS close 감지는 FastAPI의 `WebSocketDisconnect` 예외 catch
- 현재 Qwen SLM subprocess가 살아있으면 `terminate()` 후 1초 timeout 뒤 `kill()`

현재 구현에서 `/sti` handler는 binary frame을 내부 `asyncio.Queue(maxsize=256)`에 `put_nowait()`로 빠르게 적재하고, 별도 worker task가 `SessionManager.feed_audio(frame)`을 호출한다. 내부 queue가 가득 차면 receive loop를 block하지 않고 brain이 `timeout` error를 반환한다. `SessionManager.feed_audio(frame)`은 protocol binary frame 전체를 받는다. 여기서 4-byte header (`seq_u16`, `flags`, `reserved`)를 파싱하고, payload PCM만 `StiPipeline.feed_audio(pcm)`으로 넘긴다. 예상 payload는 16kHz mono PCM 40ms, 즉 640 samples × 2 bytes = 1280 bytes다. 예상과 다른 길이는 `frame_warning`으로 로그만 남기며, 첫 bring-up 검증을 위해 즉시 실패시키지 않는다.

## 외부 계약 (잠금)

내부 인터페이스는 자유지만 **WS 프로토콜은 절대 잠금**:

→ `docs/protocol/mcu-brain.md`의 메시지 카탈로그 (session_start, session_ack, session_busy, intent, error 등)와 envelope 구조를 정확히 따라야 합니다. **pydantic 모델로 1:1 매핑** 권장 — markdown은 human-readable, pydantic이 runtime 검증의 source of truth.
