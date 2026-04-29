from __future__ import annotations

import asyncio

from brain.config import MockBrainConfig
from brain.pipeline.base import SessionOpts, StiError, StiPipeline, StiResult


class MockPipeline(StiPipeline):
    def __init__(self, config: MockBrainConfig) -> None:
        self._config = config
        self._opts: SessionOpts | None = None
        self.audio_bytes = 0
        self.cancelled = False

    async def start_session(self, opts: SessionOpts) -> None:
        self._opts = opts
        self.audio_bytes = 0
        self.cancelled = False

    async def feed_audio(self, pcm: bytes) -> None:
        self.audio_bytes += len(pcm)

    async def finish_session(self) -> StiResult:
        if self.cancelled:
            raise StiError("internal", "mock pipeline cancelled")
        if self._config.delay_ms:
            await asyncio.sleep(self._config.delay_ms / 1000)
        if self.cancelled:
            raise StiError("internal", "mock pipeline cancelled")
        return StiResult(
            intent=self._config.intent,
            slots={},
            confidence=self._config.confidence,
            raw_text=f"mock: {self._config.intent}",
            asr_ms=0,
            slm_ms=0,
        )

    async def cancel_session(self) -> None:
        self.cancelled = True

