# Brain — Phase별 구현 계획

> Phase 0 → 1 → 2 → 3 → 4 → 5 → 6 순서대로 진행. brain은 **Phase 4부터 활성**.
> 인터페이스 시그니처(권장)는 `INTERFACES.md`, 컴포넌트 구조는 `ARCHITECTURE.md` 참고.

## Phase 0~3 — brain 작업 없음

ESP가 Picovoice Rhino로 standalone 동작. brain은 미존재.

이 기간 동안 brain 진입 시점을 사전에 평가:
- [ ] Rhino context 확장만으로 자연어 변형 인식률이 실측 한계에 도달하는지 모니터링
- [ ] 50+ intent 또는 슬롯 복잡도 증가가 실제 요구로 들어왔는지 확인
- [ ] **둘 중 하나라도 yes일 때만 Phase 4 진입.** 추측으로 들어가지 말 것

### brain 도입 결정 체크리스트 (Phase 4 진입 전 모두 yes 필요)

- [ ] Rhino context.yml 확장만으로 해결 안 되는 자연어 변형이 실제 사용에서 관찰됨
- [ ] 인식 안 되는 표현 30개 이상 코퍼스 수집
- [ ] 사용자가 "확장성을 위해 SLM"이라고 명시 결정
- [ ] RPi 4GB 하드웨어 확보, 열 안정성 환경 검증
- [ ] Phase 1~3 정상 동작 (brain 없이 prototype 검증 완료)
- [ ] SLM/Whisper 모델 라이선스 확인 (상용 가능 여부)
- [ ] Pi 4GB 실측 thermal headroom 측정 (장시간 추론 시 클럭 throttle 확인)

위 모두 yes가 아니면 Phase 4 진입 보류.

---

## Phase 4 — brain STI 서비스 도입

**목표**: ESP가 brain을 primary로, Rhino를 fallback으로 사용. 자연어 자유도 향상.

### 현재 구현 스냅샷 (2026-05-05)

Phase 4 최종 계획 전체가 완료된 상태는 아니다. 현재 코드는 MCU 검증과 실음성 intent 검증을 위해 다음 범위까지 구현되어 있다.

| 영역 | 현재 상태 |
|------|-----------|
| WS protocol | `docs/protocol/mcu-brain.md` 계약을 유지한다. 외부 message shape 변경 없음. |
| Session | `SessionManager` 5-state 모델과 single-flight lock 사용. |
| Pipeline | `BRAIN_PIPELINE=mock` 기본값, `BRAIN_PIPELINE=moonshine_tiny_ko` 실음성 경로 추가. |
| ASR | Moonshine tiny-ko로 session_end 후 누적 PCM을 한 번에 transcription. |
| SLM | Qwen 3.5 0.8B Q4_K_M GGUF를 `llama-cli` subprocess로 호출. timeout/error 시 catalog matcher로 fallback. |
| Recipe | brain-owned `recipes/nubjuk_motion_catalog.json`, version `nubjuk-motion-2026-05-05.2`. |
| Intent set | `idle`, `sit`, `stand`, `roll_left`, `roll_right`, `give_hand`, `surprise`. |
| Voice test | `scripts/voice_test.sh`가 마이크 녹음 WAV를 MCU-style WS frame으로 `/sti`에 전송. |

아래 항목들은 원래 Phase 4 target architecture다. 현재 구현과 다를 수 있으며, 실제 배포 기준은 `ARCHITECTURE.md`의 현재 구현 섹션을 먼저 본다.

### 디렉토리 스캐폴딩
```
brain/
├── pyproject.toml
├── README.md
├── brain/
│   ├── __init__.py
│   ├── ws_server.py            # FastAPI + websockets, /sti 엔드포인트
│   ├── pipeline/
│   │   ├── __init__.py
│   │   ├── base.py             # StiPipeline ABC (INTERFACES.md)
│   │   ├── whisper_llama.py    # Phase 4 default 구현
│   │   ├── vad.py              # webrtcvad
│   │   ├── asr.py              # whisper.cpp 래퍼
│   │   └── slm.py              # llama.cpp + grammar
│   ├── session.py              # SessionManager (single-flight)
│   ├── schema.py               # pydantic models (mcu-brain.md 1:1 매핑)
│   ├── eval/
│   │   ├── __init__.py
│   │   ├── run_corpus.py       # 한국어 평가 코퍼스 실행
│   │   ├── calibrate_confidence.py  # confidence threshold 보정
│   │   └── corpus/             # 오디오 + ground truth (wav + manifest.csv)
│   ├── config.py               # env 기반 설정
│   └── logging.py              # 구조화 로그
├── models/                     # gguf 파일 (gitignore)
├── scripts/
│   ├── download_models.sh
│   ├── benchmark.sh
│   └── nubjuk-brain.service    # systemd unit
└── tests/
    ├── test_ws_protocol.py
    ├── test_pipeline.py
    └── test_session_singleflight.py
```

### 구현 task

#### 4.1 의존성 셋업 (codex fix: ASR/SLM 통합 방식 commit)
- [ ] Python 3.11 (arm64 RPi)
- [ ] FastAPI + `websockets`
- [ ] **ASR**: `llama-cpp-python`과 동일 패턴 — **Python binding 사용** (`pywhispercpp` 또는 `whispercpp`). subprocess는 안 씀. 이유:
  - cancellation 단순 (Python 객체 dispose)
  - latency 낮음 (process spawn 없음)
  - 메모리 격리는 `SessionManager`에서 모델 인스턴스 1개로 관리
- [ ] **SLM**: `llama-cpp-python` 사용 (Python binding). 이유 동일
- [ ] `webrtcvad`
- [ ] `pydantic` v2 (메시지 검증)

#### 4.2 모델 준비 (codex fix: 메모리 budget 현실적으로)
- [ ] Whisper.cpp `base.ko` Q5 권장 (small.ko는 RPi에서 latency 한계)
- [ ] SLM: **EXAONE 3.5 2.4B Q4** GGUF (한국어 우수, RPi에서 실용적)
- [ ] `models/` 디렉토리 (gitignore)
- [ ] `scripts/download_models.sh` 자동 다운로드 + checksum 검증
- [ ] **메모리 footprint 측정**:
  - Steady-state RSS (모델 로드 후 idle): ≤ 2.0GB
  - **Peak RSS** (audio + ASR + SLM 동시 inference 중): ≤ 2.8GB
  - **헤드룸**: 4GB - peak - kernel(~300MB) - 시스템 - 단편화 마진 ≥ 500MB
  - 측정 도구: `htop` + `psrecord` 또는 `tracemalloc`
- [ ] **Cold-start budget**: 모델 로드 시작 ~ 첫 session 수락 가능 시점 < 30초
- [ ] **Thermal soak**: 1시간 연속 추론 시 CPU 클럭이 throttle되지 않는지 (heatsink/fan 권장)

#### 4.3 WS 서버 (FastAPI)
- [ ] `/sti` 엔드포인트 — `docs/protocol/mcu-brain.md` 계약 따름
- [ ] 메시지 dispatch:
  - `session_start` → `SessionManager.try_start()`, 실패 시 `session_busy`
  - binary frame → 현재 세션의 `feed_audio()` 호출
  - `session_end` → `SessionManager.finish()` trigger
  - `session_cancel` → `SessionManager.cancel()`
- [ ] schema 위반 메시지 → `error{code:"schema_invalid"}` (recoverable, WS 유지) — codex fix: aggressive close X
- [ ] **치명적 protocol error만 close**: 잘못된 binary frame 길이, 인증 실패 (P6+) 등
- [ ] WS lifetime 한 세션과 동일 (1 utterance = 1 connection)
- [ ] WS close 감지 → `SessionManager.cancel()` 자동 호출 (subprocess/binding cleanup)

#### 4.4 SessionManager (single-flight, 명시적 state machine)
- [ ] `Session` 클래스 — id, correlation_id, audio_buffer, state (`SessionState` enum)
- [ ] `SessionManager` — 동시 1개만 활성 (`asyncio.Lock`)
- [ ] **State transitions은 `INTERFACES.md`의 모델 따름** (잠금)
- [ ] 두 번째 `try_start` 요청 시 `session_busy{reason:"single_flight"}` 응답
- [ ] **Cleanup 보장**: DONE / CANCELLED / WS close / 예외 어느 경우에서든:
  - lock release
  - pipeline `cancel_session()` 호출 (idempotent)
  - audio buffer 해제
  - subprocess (있다면) terminate→kill timeout 5초
- [ ] **Race 케이스 명시**:
  - `session_cancel`이 `session_end`와 거의 동시 도착 → cancel 우선
  - `session_end` 후 응답 송신 전 WS close → CANCELLED 전이, 결과 송신 안 함

#### 4.5 Pipeline `WhisperLlamaPipeline` (codex fix: grammar 보장 정확성, confidence eval)
- [ ] `vad.py` — webrtcvad로 utterance 종료 감지 (보조 신호; 권한은 `session_end`)
- [ ] `asr.py` — Whisper.cpp 호출, 한국어 transcript 반환
- [ ] `slm.py` — llama.cpp + grammar 파일 (intent JSON 형식 강제)
- [ ] **Grammar 보장 범위 (정확히)**:
  - ✅ JSON parser-valid 출력
  - ✅ 필수 키 (`intent`, `slots`, ...) 존재
  - ✅ enum 값 (intent enum) 위반 차단
  - ❌ **의미적 유효성 보장 X** — cross-field 제약, 정확한 슬롯 의미 등
  - ❌ **Truncation/degenerate 출력 보장 X** — 빈 객체나 쓸모없는 출력 가능
  - 따라서 **grammar 출력 + pydantic 검증 + 의미 sanity check 모두 통과해야 accept**
- [ ] **Confidence 결정 (eval 기반, magic number X)**:
  - llama.cpp의 token logprob을 직접 confidence로 쓰지 않음 (calibration 안 됨)
  - 대신 **eval/calibrate_confidence.py**로 한국어 코퍼스에서:
    1. 정답·오답 분리
    2. 각 분류에 대해 logprob 분포 측정
    3. 95% precision threshold 선정 (false positive < 5%)
    4. 그 이하면 `intent="unknown"` 회신
  - threshold 값은 `config.py`에 calibration 결과로 저장
- [ ] **단일 utterance만 처리, partial 없음** (atomic 응답)

#### 4.6 Schema validator (`schema.py`)
- [ ] `docs/protocol/mcu-brain.md` 메시지 모두 **pydantic v2 모델로 1:1 매핑**
- [ ] 입출력 모든 메시지 검증
- [ ] 검증 실패 시 `schema_invalid` 에러로 클라이언트에 회신 (close X, recoverable)
- [ ] **markdown은 human-doc, pydantic은 runtime SoT** — 두 곳이 drift하지 않도록 PR 시 둘 다 수정 강제

#### 4.7 평가 하네스
- [ ] `eval/run_corpus.py` — 한국어 코퍼스 (wav 파일)
- [ ] **코퍼스 구성 (Phase 1과 통일, 150 샘플)**:
  - 5 intents × 5 발화 변형 × 3 노이즈 (조용/일반/시끄러움) × 2 화자 = 150
  - 30 distractor (false trigger 측정)
  - 추가 권장: dialect 변형 / 속도 변형 / clipped utterance 각 10개씩 (Phase 4.b로)
- [ ] 각 샘플을 mock WS 클라이언트로 brain에 전송, intent 결과 수집
- [ ] 메트릭 출력: ASR CER, Intent accuracy (top-1), latency P50/P95, abstention rate
- [ ] 평가 코퍼스 디렉토리 구조: `corpus/{intent}/{variant}_{noise}_{speaker}.wav` + `manifest.csv`

#### 4.8 Latency / observability
- [ ] 각 응답에 `asr_ms` / `slm_ms` 포함
- [ ] **구조화 로그** (JSON): timestamp, session_id, correlation_id, state_transition, audio_bytes, transcript_len, intent, confidence, total_ms, error
- [ ] 로그 파일 rotation (`logging.handlers.RotatingFileHandler`, 10MB × 5)
- [ ] P50/P95 통계는 단순 grep + jq로 분석 (Prometheus 미도입)

#### 4.9 Deployment (systemd)
- [ ] `scripts/nubjuk-brain.service` — systemd unit
- [ ] `Restart=on-failure`, `RestartSec=5s`
- [ ] `MemoryMax=3G` (cgroup 보호)
- [ ] `OOMScoreAdjust=-500` (OOM killer 회피)
- [ ] 부팅 시 모델 경로 검증, 실패 시 명확한 로그 + exit
- [ ] `/health` HTTP 엔드포인트 (모델 로드 완료 + idle 상태 체크)

#### 4.10 Failure modes 명시 처리
- [ ] **ASR 빈 transcript**: `error{code:"asr_failed", message:"empty transcript"}`
- [ ] **SLM 응답 timeout** (default 5초): `error{code:"timeout"}`
- [ ] **Subprocess 행 오랫동안 응답 없음**: terminate→kill, `error{code:"internal"}`
- [ ] **OOM 임박** (psutil로 사용량 모니터, 90% 초과): 새 session 거부 (`session_busy{reason:"resource_pressure"}`)
- [ ] **Half-open WS / partial audio + 갑자기 disconnect**: SessionManager.cancel() 자동 호출, 자원 해제
- [ ] **모델 init 실패**: 부팅 거부 (systemd가 retry)
- [ ] **Thermal throttling 감지**: 로그 경고, 가능하면 advise

### Phase 4 Gate

- [ ] **메모리**: peak RSS ≤ 2.8GB, 헤드룸 ≥ 500MB
- [ ] **Cold-start**: 모델 로드 → 첫 session 수락 가능 < 30초
- [ ] **Thermal soak**: 1시간 연속 추론 시 클럭 throttle 0회
- [ ] grammar + pydantic 검증으로 schema-valid intent JSON 100%
- [ ] **한국어 평가 코퍼스 150 샘플 intent accuracy ≥ 90%** (Rhino 단독 대비 향상 측정)
- [ ] **End-to-end Latency P95 ≤ 3.5s** (session_start 수신 → intent 응답 송신, monotonic ms)
- [ ] confidence calibration 적용 후 `intent="unknown"` abstention rate가 정확도 향상에 기여 (eval 결과로 입증)
- [ ] Single-flight 강제: 동시 2 세션 요청 시 두 번째에 `session_busy` 응답
- [ ] 세션 cancel 시 즉시 자원 해제 (lock + audio buffer + subprocess), 다음 session 정상 시작
- [ ] WS schema 위반 메시지 거부 동작 (recoverable, close X)
- [ ] **Half-open / disconnect 자동 cleanup** 검증 (psutil로 zombie subprocess 확인)
- [ ] **OOM 시뮬레이션** — `MemoryMax=2.5G`로 일시 강제 시 systemd restart 정상
- [ ] **ESP의 dual fallback 통합 테스트** — brain stop 시 ESP가 500ms 내 Rhino로 전환

---

## Phase 5+ — brain 변경 거의 없음

Unity viewer 도입은 brain과 무관 (brain은 mcu만 통신).

- [ ] (선택) Phase 6 양산화 시 brain 인증/암호화 (mTLS 또는 토큰)
- [ ] (선택) brain 모델 업그레이드 — A/B benchmark 스크립트 + rollback 절차
- [ ] (선택) Multi-language 확장 (영어/일어 등 — Rhino context 확장 필요)

### Phase 6 production 추가 항목
- [ ] mTLS (양방향 인증서 검증)
- [ ] 모델 versioned manifest + checksum + rollback
- [ ] Crash-loop 감지 (systemd `RestartSec` + 횟수 제한)
- [ ] 24h+ soak: 메모리 leak slope ≤ 50 MB/h, 응답 latency 안정성
