from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from enum import Enum

from brain.pipeline.base import SessionOpts, StiError, StiPipeline, StiResult

EXPECTED_PCM_PAYLOAD_BYTES = 640 * 2


class SessionState(Enum):
    IDLE = "idle"
    AUDIO_IN = "audio_in"
    PROCESSING = "processing"
    DONE = "done"
    CANCELLED = "cancelled"


@dataclass
class SessionStats:
    frames_observed: int = 0
    frames_reported: int | None = None
    audio_bytes: int = 0
    frame_warnings: list[str] = field(default_factory=list)
    expected_seq: int | None = None
    started_at: float = field(default_factory=time.monotonic)
    intent: str | None = None


class SessionManager:
    r"""Single-flight session manager for the P1 mock brain.

    State machine:
        IDLE -> AUDIO_IN -> PROCESSING -> DONE -> IDLE
             \              \-> CANCELLED -> IDLE
              \-> CANCELLED -> IDLE
    """

    def __init__(
        self,
        pipeline: StiPipeline,
        *,
        logger: logging.Logger | None = None,
    ) -> None:
        self._pipeline = pipeline
        self._lock = asyncio.Lock()
        self._logger = logger or logging.getLogger("brain.session")
        self.state = SessionState.IDLE
        self.opts: SessionOpts | None = None
        self.stats = SessionStats()

    @property
    def active(self) -> bool:
        return self._lock.locked()

    async def try_start(self, opts: SessionOpts, ws: object | None = None) -> bool:
        if self._lock.locked():
            return False
        await self._lock.acquire()
        self.opts = opts
        self.stats = SessionStats()
        await self._pipeline.start_session(opts)
        self._transition(SessionState.AUDIO_IN, "session_start")
        return True

    async def feed_audio(self, frame: bytes) -> None:
        if self.state is not SessionState.AUDIO_IN:
            return
        if len(frame) < 4:
            self._warn("frame_too_short")
            return

        seq = int.from_bytes(frame[0:2], byteorder="big", signed=False)
        flags = frame[2]
        reserved = frame[3]
        payload = frame[4:]

        if self.stats.expected_seq is None:
            self.stats.expected_seq = (seq + 1) & 0xFFFF
        elif seq != self.stats.expected_seq:
            self._warn(f"seq_non_monotonic expected={self.stats.expected_seq} got={seq}")
            self.stats.expected_seq = (seq + 1) & 0xFFFF
        else:
            self.stats.expected_seq = (self.stats.expected_seq + 1) & 0xFFFF

        if flags & ~0x01:
            self._warn(f"unknown_flags flags={flags}")
        if reserved != 0:
            self._warn(f"reserved_nonzero reserved={reserved}")
        if len(payload) != EXPECTED_PCM_PAYLOAD_BYTES:
            self._warn(f"unexpected_pcm_bytes bytes={len(payload)}")

        self.stats.frames_observed += 1
        self.stats.audio_bytes += len(payload)
        await self._pipeline.feed_audio(payload)

    async def finish(self, frames_reported: int) -> StiResult:
        if self.state is not SessionState.AUDIO_IN:
            raise StiError("internal", f"cannot finish from {self.state.value}")
        self.stats.frames_reported = frames_reported
        if frames_reported != self.stats.frames_observed:
            self._warn(
                f"frame_count_mismatch reported={frames_reported} observed={self.stats.frames_observed}"
            )
        self._transition(SessionState.PROCESSING, "session_end")
        try:
            result = await self._pipeline.finish_session()
        except StiError:
            if self.state is not SessionState.CANCELLED:
                self._transition(SessionState.CANCELLED, "pipeline_error")
                await self._cleanup()
            raise
        if self.state is SessionState.CANCELLED:
            raise StiError("internal", "session cancelled during processing")
        self.stats.intent = result.intent
        self._transition(SessionState.DONE, "pipeline_result")
        return result

    async def complete(self, reason: str = "response_sent") -> None:
        if self.state is SessionState.DONE:
            self._log_session_done()
            await self._cleanup(reason)

    async def cancel(self, reason: str = "cancel") -> None:
        if self.state is SessionState.IDLE and not self._lock.locked():
            return
        if self.state is not SessionState.CANCELLED:
            self._transition(SessionState.CANCELLED, reason)
        await self._cleanup(reason)

    def _transition(self, next_state: SessionState, reason: str) -> None:
        previous = self.state
        self.state = next_state
        self._log(
            {
                "event": "state_transition",
                "correlation_id": self.opts.correlation_id if self.opts else "",
                "from": previous.value,
                "to": next_state.value,
                "reason": reason,
            }
        )

    async def _cleanup(self, reason: str = "cleanup") -> None:
        await self._pipeline.cancel_session()
        if self.state is not SessionState.IDLE:
            self._transition(SessionState.IDLE, reason)
        self.opts = None
        if self._lock.locked():
            self._lock.release()

    def _warn(self, message: str) -> None:
        self.stats.frame_warnings.append(message)
        self._log(
            {
                "event": "frame_warning",
                "correlation_id": self.opts.correlation_id if self.opts else "",
                "warning": message,
            },
            level=logging.WARNING,
        )

    def _log_session_done(self) -> None:
        total_ms = int((time.monotonic() - self.stats.started_at) * 1000)
        self._log(
            {
                "event": "mock_session_done",
                "correlation_id": self.opts.correlation_id if self.opts else "",
                "state": self.state.value,
                "frames_observed": self.stats.frames_observed,
                "frames_reported": self.stats.frames_reported,
                "audio_bytes": self.stats.audio_bytes,
                "frame_warnings": self.stats.frame_warnings,
                "intent": self.stats.intent,
                "total_ms": total_ms,
            }
        )

    def _log(self, payload: dict[str, object], *, level: int = logging.INFO) -> None:
        self._logger.log(level, json.dumps(payload, separators=(",", ":"), ensure_ascii=False))
