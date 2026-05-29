from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass

import pytest

from brain.config import MoonshineTinyKoConfig
from brain.intent.catalog import IntentCatalog
from brain.pipeline.base import SessionOpts, StiError
from brain.pipeline.moonshine_tiny_ko import (
    MoonshineTinyKoRulesPipeline,
    match_intent,
    pcm_s16le_to_float_list,
    pcm_s16le_stats,
)
from brain.pipeline.qwen_slm import SlmIntentDecision


@dataclass
class FakeTranscriber:
    text: str
    asr_ms: int = 12
    pcm_seen: bytes = b""

    def transcribe(self, pcm: bytes) -> tuple[str, int]:
        self.pcm_seen = pcm
        return self.text, self.asr_ms


@dataclass
class FakeTranscriberWithIdleWait(FakeTranscriber):
    wait_called: bool = False

    def wait_for_idle(self) -> None:
        self.wait_called = True
        raise AssertionError("cancel_session must not wait for ASR idle")


@dataclass
class FakeIntentResolver:
    intent: str
    slm_ms: int = 23
    cancelled: bool = False
    calls: int = 0

    async def resolve(self, raw_text: str, catalog: IntentCatalog) -> SlmIntentDecision:
        self.calls += 1
        return SlmIntentDecision(intent=self.intent, raw_output=self.intent, slm_ms=self.slm_ms)

    async def cancel(self) -> None:
        self.cancelled = True


def config(**overrides) -> MoonshineTinyKoConfig:
    return MoonshineTinyKoConfig(slm_enabled=False, **overrides)


def opts(max_utterance_ms: int = 5000) -> SessionOpts:
    return SessionOpts(correlation_id="cid", max_utterance_ms=max_utterance_ms)


def test_pcm_s16le_to_float_list() -> None:
    pcm = b"\x00\x00\x00@\x00\xc0"
    assert pcm_s16le_to_float_list(pcm) == [0.0, 0.5, -0.5]


def test_pcm_s16le_stats() -> None:
    pcm = b"\x00\x00\x00@\x00\xc0"

    stats = pcm_s16le_stats(pcm)

    assert stats["sample_count"] == 3
    assert stats["duration_ms"] == 0
    assert stats["rms"] == 0.408248
    assert stats["peak"] == 16384
    assert stats["peak_norm"] == 0.5
    assert stats["nonzero_ratio"] == 0.666667
    assert stats["clipped_samples"] == 0
    assert stats["dc_offset"] == 0.0


@pytest.mark.parametrize(
    ("text", "intent"),
    [
        ("오른쪽으로 굴러", "roll_right"),
        ("우회전", "roll_right"),
        ("좌로 글로", "roll_left"),
        ("roll right", "roll_right"),
        ("가만히 있어", "idle"),
    ],
)
def test_rule_matcher(text: str, intent: str) -> None:
    assert match_intent(text, unknown_confidence=0.2).intent == intent


def test_moonshine_pipeline_returns_roll_right_from_transcript() -> None:
    async def run() -> None:
        fake = FakeTranscriber("오른쪽으로 굴러")
        pipeline = MoonshineTinyKoRulesPipeline(config(), transcriber=fake)
        await pipeline.start_session(opts())
        await pipeline.feed_audio(b"\x00\x00" * 160)
        result = await pipeline.finish_session()
        assert result.intent == "roll_right"
        assert result.raw_text == "오른쪽으로 굴러"
        assert result.asr_ms == 12
        assert result.slm_ms == 0
        assert fake.pcm_seen == b"\x00\x00" * 160
        await pipeline.cancel_session()

    asyncio.run(run())


def test_moonshine_pipeline_uses_injected_catalog() -> None:
    async def run() -> None:
        catalog = IntentCatalog.from_dict(
            {
                "catalog_version": "test",
                "intents": [
                    {
                        "id": "wave_hand",
                        "aliases": ["손 흔들어"],
                        "confidence": 0.82,
                        "exact_confidence": 0.95,
                    }
                ],
            }
        )
        pipeline = MoonshineTinyKoRulesPipeline(
            config(),
            transcriber=FakeTranscriber("손 흔들어"),
            catalog=catalog,
        )
        await pipeline.start_session(opts())
        await pipeline.feed_audio(b"\x00\x00" * 160)
        result = await pipeline.finish_session()
        assert result.intent == "wave_hand"
        assert result.confidence == 0.95
        await pipeline.cancel_session()

    asyncio.run(run())


def test_moonshine_pipeline_uses_slm_intent_when_enabled() -> None:
    async def run() -> None:
        resolver = FakeIntentResolver("roll_left")
        pipeline = MoonshineTinyKoRulesPipeline(
            MoonshineTinyKoConfig(
                slm_enabled=True,
                slm_confidence=0.78,
                slm_min_catalog_confidence=0.73,
            ),
            transcriber=FakeTranscriber("좌로 글로"),
            intent_resolver=resolver,
        )
        await pipeline.start_session(opts())
        await pipeline.feed_audio(b"\x00\x00" * 160)
        result = await pipeline.finish_session()
        assert result.intent == "roll_left"
        assert result.confidence == 0.78
        assert result.slm_ms == 23
        await pipeline.cancel_session()
        assert resolver.calls == 1
        assert resolver.cancelled is True

    asyncio.run(run())


def test_moonshine_pipeline_keeps_high_confidence_catalog_match_over_slm() -> None:
    async def run() -> None:
        pipeline = MoonshineTinyKoRulesPipeline(
            MoonshineTinyKoConfig(
                slm_enabled=True,
                slm_confidence=0.78,
                slm_min_catalog_confidence=1.0,
            ),
            transcriber=FakeTranscriber("울어 굴러"),
            intent_resolver=FakeIntentResolver("roll_left"),
        )
        await pipeline.start_session(opts())
        await pipeline.feed_audio(b"\x00\x00" * 160)
        result = await pipeline.finish_session()
        assert result.intent == "roll_right"
        assert result.confidence == 0.94
        assert result.slm_ms == 23
        await pipeline.cancel_session()

    asyncio.run(run())


def test_moonshine_pipeline_falls_back_to_catalog_when_slm_returns_unknown() -> None:
    async def run() -> None:
        pipeline = MoonshineTinyKoRulesPipeline(
            MoonshineTinyKoConfig(slm_enabled=True, slm_min_catalog_confidence=0.73),
            transcriber=FakeTranscriber("좌로 글로"),
            intent_resolver=FakeIntentResolver("unknown"),
        )
        await pipeline.start_session(opts())
        await pipeline.feed_audio(b"\x00\x00" * 160)
        result = await pipeline.finish_session()
        assert result.intent == "roll_left"
        assert result.confidence == 0.72
        assert result.slm_ms == 23
        await pipeline.cancel_session()

    asyncio.run(run())


def test_moonshine_pipeline_keeps_phonetic_catalog_match_over_wrong_slm() -> None:
    async def run() -> None:
        pipeline = MoonshineTinyKoRulesPipeline(
            MoonshineTinyKoConfig(
                slm_enabled=True,
                slm_confidence=0.78,
                slm_min_catalog_confidence=0.73,
            ),
            transcriber=FakeTranscriber("은자"),
            intent_resolver=FakeIntentResolver("idle"),
        )
        await pipeline.start_session(opts())
        await pipeline.feed_audio(b"\x00\x00" * 160)
        result = await pipeline.finish_session()
        assert result.intent == "sit"
        assert result.confidence == 0.72
        assert result.slm_ms == 23
        await pipeline.cancel_session()

    asyncio.run(run())


def test_moonshine_pipeline_keeps_observed_asr_noise_over_wrong_slm() -> None:
    async def run() -> None:
        pipeline = MoonshineTinyKoRulesPipeline(
            MoonshineTinyKoConfig(
                slm_enabled=True,
                slm_confidence=0.78,
                slm_min_catalog_confidence=0.87,
            ),
            transcriber=FakeTranscriber("인자"),
            intent_resolver=FakeIntentResolver("idle"),
        )
        await pipeline.start_session(opts())
        await pipeline.feed_audio(b"\x00\x00" * 160)
        result = await pipeline.finish_session()
        assert result.intent == "sit"
        assert result.confidence == 0.86
        assert result.slm_ms == 23
        await pipeline.cancel_session()

    asyncio.run(run())


@pytest.mark.parametrize("text", ["아니 인자", "안 져."])
def test_moonshine_pipeline_skips_slm_for_realtime_sit_match(text: str) -> None:
    async def run() -> None:
        resolver = FakeIntentResolver("idle")
        pipeline = MoonshineTinyKoRulesPipeline(
            MoonshineTinyKoConfig(slm_enabled=True, slm_confidence=0.78),
            transcriber=FakeTranscriber(text),
            intent_resolver=resolver,
        )
        await pipeline.start_session(opts())
        await pipeline.feed_audio(b"\x00\x00" * 160)
        result = await pipeline.finish_session()
        assert result.intent == "sit"
        assert result.confidence == 0.72
        assert result.slm_ms == 0
        await pipeline.cancel_session()
        assert resolver.calls == 0

    asyncio.run(run())


def test_moonshine_pipeline_keeps_roll_left_noise_over_wrong_slm() -> None:
    async def run() -> None:
        pipeline = MoonshineTinyKoRulesPipeline(
            MoonshineTinyKoConfig(
                slm_enabled=True,
                slm_confidence=0.78,
                slm_min_catalog_confidence=0.87,
            ),
            transcriber=FakeTranscriber("잘 어울려."),
            intent_resolver=FakeIntentResolver("roll_right"),
        )
        await pipeline.start_session(opts())
        await pipeline.feed_audio(b"\x00\x00" * 160)
        result = await pipeline.finish_session()
        assert result.intent == "roll_left"
        assert result.confidence == 0.86
        assert result.slm_ms == 23
        await pipeline.cancel_session()

    asyncio.run(run())


def test_moonshine_pipeline_skips_slm_for_unknown_transcript() -> None:
    async def run() -> None:
        resolver = FakeIntentResolver("idle")
        pipeline = MoonshineTinyKoRulesPipeline(
            MoonshineTinyKoConfig(slm_enabled=True, unknown_confidence=0.2, slm_confidence=0.78),
            transcriber=FakeTranscriber("전혀 모름"),
            intent_resolver=resolver,
        )
        await pipeline.start_session(opts())
        await pipeline.feed_audio(b"\x00\x00" * 160)
        result = await pipeline.finish_session()
        assert result.intent == "unknown"
        assert result.confidence == 0.2
        assert result.slm_ms == 0
        await pipeline.cancel_session()
        assert resolver.calls == 0

    asyncio.run(run())


def test_moonshine_pipeline_skips_slm_motion_for_unknown_transcript() -> None:
    async def run() -> None:
        resolver = FakeIntentResolver("roll_right")
        pipeline = MoonshineTinyKoRulesPipeline(
            MoonshineTinyKoConfig(slm_enabled=True, unknown_confidence=0.2, slm_confidence=0.78),
            transcriber=FakeTranscriber("전혀 모름"),
            intent_resolver=resolver,
        )
        await pipeline.start_session(opts())
        await pipeline.feed_audio(b"\x00\x00" * 160)
        result = await pipeline.finish_session()
        assert result.intent == "unknown"
        assert result.confidence == 0.2
        assert result.slm_ms == 0
        await pipeline.cancel_session()
        assert resolver.calls == 0

    asyncio.run(run())


def test_moonshine_cancel_does_not_wait_for_transcriber_idle() -> None:
    async def run() -> None:
        fake = FakeTranscriberWithIdleWait("오른쪽")
        pipeline = MoonshineTinyKoRulesPipeline(config(), transcriber=fake)
        await pipeline.start_session(opts())
        await pipeline.feed_audio(b"\x00\x00" * 160)

        await pipeline.cancel_session()

        assert pipeline.cancelled is True
        assert fake.wait_called is False

    asyncio.run(run())


def test_moonshine_pipeline_logs_asr_answer(caplog: pytest.LogCaptureFixture) -> None:
    async def run() -> None:
        logger = logging.getLogger("test.moonshine")
        pipeline = MoonshineTinyKoRulesPipeline(
            config(),
            transcriber=FakeTranscriber("오른쪽"),
            logger=logger,
        )
        await pipeline.start_session(opts())
        await pipeline.feed_audio(b"\x00\x00" * 160)
        await pipeline.finish_session()
        await pipeline.cancel_session()

    caplog.set_level(logging.INFO, logger="test.moonshine")
    asyncio.run(run())

    payloads = [json.loads(record.message) for record in caplog.records]
    asr_answer = next(payload for payload in payloads if payload["event"] == "asr_answer")
    assert asr_answer["correlation_id"] == "cid"
    assert asr_answer["raw_text"] == "오른쪽"
    assert asr_answer["asr_ms"] == 12
    assert asr_answer["audio_bytes"] == 320
    assert asr_answer["sample_count"] == 160
    assert asr_answer["duration_ms"] == 10
    assert asr_answer["rms"] == 0.0
    assert asr_answer["peak"] == 0
    assert asr_answer["nonzero_ratio"] == 0.0


def test_moonshine_pipeline_rejects_empty_transcript() -> None:
    async def run() -> None:
        pipeline = MoonshineTinyKoRulesPipeline(
            config(),
            transcriber=FakeTranscriber(""),
        )
        await pipeline.start_session(opts())
        await pipeline.feed_audio(b"\x00\x00" * 160)
        with pytest.raises(StiError, match="empty transcript"):
            await pipeline.finish_session()
        await pipeline.cancel_session()

    asyncio.run(run())


def test_moonshine_pipeline_enforces_max_audio_duration() -> None:
    async def run() -> None:
        pipeline = MoonshineTinyKoRulesPipeline(
            config(max_audio_ms=1),
            transcriber=FakeTranscriber("오른쪽"),
        )
        await pipeline.start_session(opts(max_utterance_ms=1))
        with pytest.raises(StiError, match="max duration"):
            await pipeline.feed_audio(b"\x00\x00" * 17)
        await pipeline.cancel_session()

    asyncio.run(run())
