from __future__ import annotations

import asyncio
import json
import logging
import math
import sys
import threading
import time
from array import array
from typing import Protocol

from brain.config import MoonshineTinyKoConfig
from brain.intent.catalog import IntentCatalog, IntentMatch, load_intent_catalog
from brain.pipeline.base import SessionOpts, StiError, StiPipeline, StiResult
from brain.pipeline.qwen_slm import QwenSlmIntentResolver, SlmIntentDecision, compact_slm_output

SAMPLE_RATE_HZ = 16_000
BYTES_PER_SAMPLE = 2


class TinyKoTranscriber(Protocol):
    def transcribe(self, pcm: bytes) -> tuple[str, int]: ...


class SlmIntentResolver(Protocol):
    async def resolve(self, raw_text: str, catalog: IntentCatalog) -> SlmIntentDecision: ...

    async def cancel(self) -> None: ...


class MoonshineTinyKoTranscriber:
    def __init__(self, config: MoonshineTinyKoConfig) -> None:
        try:
            from moonshine_voice import ModelArch, Transcriber, get_model_for_language
        except ImportError as exc:
            raise RuntimeError(
                "moonshine-voice is not installed. Install with `pip install -e '.[moonshine]'`."
            ) from exc

        if config.model_dir:
            model_path = config.model_dir
            model_arch = ModelArch.TINY
        else:
            model_path, model_arch = get_model_for_language(config.language)

        if model_arch != ModelArch.TINY:
            raise RuntimeError(f"expected Moonshine tiny-ko model arch, got {model_arch!r}")

        options = {"max_tokens_per_second": config.max_tokens_per_second}
        self._transcriber = Transcriber(model_path=model_path, model_arch=model_arch, options=options)
        self._lock = threading.Lock()

    def transcribe(self, pcm: bytes) -> tuple[str, int]:
        audio = pcm_s16le_to_float_list(pcm)
        started = time.monotonic()
        with self._lock:
            transcript = self._transcriber.transcribe_without_streaming(audio, SAMPLE_RATE_HZ)
        asr_ms = int((time.monotonic() - started) * 1000)
        return extract_transcript_text(transcript), asr_ms

    def wait_for_idle(self) -> None:
        with self._lock:
            return

    def close(self) -> None:
        close = getattr(self._transcriber, "close", None)
        if close is not None:
            close()


class MoonshineTinyKoRulesPipeline(StiPipeline):
    def __init__(
        self,
        config: MoonshineTinyKoConfig,
        *,
        transcriber: TinyKoTranscriber | None = None,
        intent_resolver: SlmIntentResolver | None = None,
        catalog: IntentCatalog | None = None,
        logger: logging.Logger | None = None,
    ) -> None:
        self._config = config
        self._transcriber = transcriber or MoonshineTinyKoTranscriber(config)
        self._catalog = catalog or load_intent_catalog(config.intent_catalog_path)
        self._intent_resolver = intent_resolver
        if self._intent_resolver is None and config.slm_enabled:
            self._intent_resolver = QwenSlmIntentResolver(config)
        self._logger = logger or logging.getLogger("uvicorn.error")
        self._opts: SessionOpts | None = None
        self._pcm = bytearray()
        self._max_audio_bytes = _audio_bytes_for_ms(config.max_audio_ms)
        self.cancelled = False

    async def start_session(self, opts: SessionOpts) -> None:
        self._opts = opts
        self._pcm = bytearray()
        self._max_audio_bytes = _audio_bytes_for_ms(min(opts.max_utterance_ms, self._config.max_audio_ms))
        self.cancelled = False

    async def feed_audio(self, pcm: bytes) -> None:
        if self.cancelled:
            return
        if len(self._pcm) + len(pcm) > self._max_audio_bytes:
            raise StiError("timeout", "audio exceeds configured max duration")
        self._pcm.extend(pcm)

    async def finish_session(self) -> StiResult:
        if self.cancelled:
            raise StiError("internal", "moonshine pipeline cancelled")
        pcm = bytes(self._pcm)
        if not pcm:
            raise StiError("asr_failed", "empty audio")
        audio_stats = pcm_s16le_stats(pcm)

        try:
            raw_text, asr_ms = await asyncio.to_thread(self._transcriber.transcribe, pcm)
        except RuntimeError as exc:
            raise StiError("asr_failed", str(exc)) from exc

        if self.cancelled:
            raise StiError("internal", "moonshine pipeline cancelled")

        raw_text = raw_text.strip()
        self._log(
            {
                "event": "asr_answer",
                "correlation_id": self._opts.correlation_id if self._opts else "",
                "raw_text": raw_text,
                "asr_ms": asr_ms,
                "audio_bytes": len(pcm),
                **audio_stats,
            }
        )
        if not raw_text:
            raise StiError("asr_failed", "empty transcript")

        catalog_match = match_intent(
            raw_text,
            catalog=self._catalog,
            unknown_confidence=self._config.unknown_confidence,
        )
        match_source = "catalog"
        match = catalog_match
        slm_ms = 0

        slm_skip_reason = _slm_skip_reason(catalog_match, self._config.slm_min_catalog_confidence)
        if self._intent_resolver is not None and slm_skip_reason is None:
            try:
                decision = await self._intent_resolver.resolve(raw_text, self._catalog)
                slm_ms = decision.slm_ms
                self._log(
                    {
                        "event": "slm_answer",
                        "correlation_id": self._opts.correlation_id if self._opts else "",
                        "intent": decision.intent,
                        "slm_ms": slm_ms,
                        "raw_output": compact_slm_output(decision.raw_output),
                    }
                )
                slm_match = self._catalog.match_intent_id(
                    decision.intent,
                    confidence=self._config.slm_confidence,
                )
                if _should_accept_slm_match(catalog_match, slm_match):
                    match = slm_match
                    match_source = "slm"
            except StiError as exc:
                self._log(
                    {
                        "event": "slm_error",
                        "correlation_id": self._opts.correlation_id if self._opts else "",
                        "code": exc.code,
                        "message": str(exc),
                    }
                )
        elif self._intent_resolver is not None:
            self._log(
                {
                    "event": "slm_skip",
                    "correlation_id": self._opts.correlation_id if self._opts else "",
                    "intent": catalog_match.intent,
                    "confidence": catalog_match.confidence,
                    "threshold": self._config.slm_min_catalog_confidence,
                    "reason": slm_skip_reason,
                }
            )

        self._log(
            {
                "event": "intent_match",
                "correlation_id": self._opts.correlation_id if self._opts else "",
                "catalog_version": self._catalog.version,
                "intent": match.intent,
                "confidence": match.confidence,
                "source": match_source,
            }
        )
        return StiResult(
            intent=match.intent,
            slots=match.slots,
            confidence=match.confidence,
            raw_text=raw_text,
            asr_ms=asr_ms,
            slm_ms=slm_ms,
        )

    async def cancel_session(self) -> None:
        self.cancelled = True
        if self._intent_resolver is not None:
            await self._intent_resolver.cancel()
        self._pcm = bytearray()

    async def close(self) -> None:
        close = getattr(self._transcriber, "close", None)
        if close is not None:
            await asyncio.to_thread(close)

    def _log(self, payload: dict[str, object]) -> None:
        self._logger.info(json.dumps(payload, separators=(",", ":"), ensure_ascii=False))


def pcm_s16le_to_float_list(pcm: bytes) -> list[float]:
    samples = _pcm_s16le_samples(pcm)
    return [max(-1.0, min(1.0, sample / 32768.0)) for sample in samples]


def pcm_s16le_stats(pcm: bytes) -> dict[str, int | float]:
    samples = _pcm_s16le_samples(pcm)
    if not samples:
        return {
            "sample_count": 0,
            "duration_ms": 0,
            "rms": 0.0,
            "peak": 0,
            "peak_norm": 0.0,
            "nonzero_ratio": 0.0,
            "clipped_samples": 0,
            "dc_offset": 0.0,
        }

    sample_count = len(samples)
    square_sum = 0
    abs_sum = 0
    peak = 0
    nonzero = 0
    clipped = 0
    for sample in samples:
        absolute = abs(sample)
        peak = max(peak, absolute)
        square_sum += sample * sample
        abs_sum += sample
        if sample != 0:
            nonzero += 1
        if absolute >= 32760:
            clipped += 1

    rms = math.sqrt(square_sum / sample_count) / 32768.0
    return {
        "sample_count": sample_count,
        "duration_ms": int(sample_count * 1000 / SAMPLE_RATE_HZ),
        "rms": round(rms, 6),
        "peak": peak,
        "peak_norm": round(peak / 32768.0, 6),
        "nonzero_ratio": round(nonzero / sample_count, 6),
        "clipped_samples": clipped,
        "dc_offset": round((abs_sum / sample_count) / 32768.0, 6),
    }


def _pcm_s16le_samples(pcm: bytes) -> array[int]:
    if len(pcm) % BYTES_PER_SAMPLE:
        raise RuntimeError("PCM payload must contain whole 16-bit samples")
    samples = array("h")
    samples.frombytes(pcm)
    if sys.byteorder != "little":
        samples.byteswap()
    return samples


def extract_transcript_text(transcript: object) -> str:
    lines = getattr(transcript, "lines", [])
    texts = [str(getattr(line, "text", "")).strip() for line in lines]
    return " ".join(text for text in texts if text)


def match_intent(text: str, *, catalog: IntentCatalog | None = None, unknown_confidence: float) -> IntentMatch:
    resolved_catalog = catalog or load_intent_catalog()
    return resolved_catalog.match(text, unknown_confidence=unknown_confidence)


def _should_accept_slm_match(catalog_match: IntentMatch, slm_match: IntentMatch | None) -> bool:
    if slm_match is None or slm_match.confidence <= catalog_match.confidence:
        return False
    if catalog_match.intent == "unknown":
        return False
    return slm_match.intent == catalog_match.intent


def _slm_skip_reason(catalog_match: IntentMatch, min_catalog_confidence: float) -> str | None:
    if catalog_match.intent == "unknown":
        return "catalog_unknown"
    if catalog_match.confidence >= min_catalog_confidence:
        return "catalog_confident"
    return None


def _audio_bytes_for_ms(duration_ms: int) -> int:
    return int(SAMPLE_RATE_HZ * BYTES_PER_SAMPLE * duration_ms / 1000)
