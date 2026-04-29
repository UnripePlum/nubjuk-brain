from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


@dataclass
class StiResult:
    intent: str
    slots: dict[str, Any]
    confidence: float
    raw_text: str | None
    asr_ms: int
    slm_ms: int


@dataclass(frozen=True)
class SessionOpts:
    correlation_id: str
    max_utterance_ms: int
    language: str = "ko"


class StiError(Exception):
    """asr_failed / slm_failed / timeout / internal."""

    def __init__(self, code: str, message: str | None = None) -> None:
        super().__init__(message or code)
        self.code = code


class StiPipeline(ABC):
    @abstractmethod
    async def start_session(self, opts: SessionOpts) -> None: ...

    @abstractmethod
    async def feed_audio(self, pcm: bytes) -> None: ...

    @abstractmethod
    async def finish_session(self) -> StiResult: ...

    @abstractmethod
    async def cancel_session(self) -> None: ...

