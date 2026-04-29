from __future__ import annotations

import asyncio

import pytest

from brain.config import MockBrainConfig
from brain.pipeline.base import SessionOpts, StiError
from brain.pipeline.mock import MockPipeline
from brain.session import EXPECTED_PCM_PAYLOAD_BYTES, SessionManager, SessionState


def frame(seq: int, payload_len: int = EXPECTED_PCM_PAYLOAD_BYTES, flags: int = 0, reserved: int = 0) -> bytes:
    return seq.to_bytes(2, "big") + bytes([flags, reserved]) + (b"\x00" * payload_len)


def opts(correlation_id: str = "cid") -> SessionOpts:
    return SessionOpts(correlation_id=correlation_id, max_utterance_ms=5000)


def test_session_lifecycle_happy_path() -> None:
    async def run() -> None:
        manager = SessionManager(MockPipeline(MockBrainConfig()))
        assert manager.state is SessionState.IDLE
        assert await manager.try_start(opts(), None)
        assert manager.state is SessionState.AUDIO_IN
        await manager.feed_audio(frame(0))
        result = await manager.finish(frames_reported=1)
        assert result.intent == "roll_right"
        assert manager.state is SessionState.DONE
        await manager.complete()
        assert manager.state is SessionState.IDLE
        assert not manager.active

    asyncio.run(run())


def test_singleflight_rejects_second_session() -> None:
    async def run() -> None:
        manager = SessionManager(MockPipeline(MockBrainConfig()))
        assert await manager.try_start(opts("a"), None)
        assert not await manager.try_start(opts("b"), None)
        await manager.cancel("test_done")
        assert not manager.active

    asyncio.run(run())


def test_cancel_from_audio_in_releases_lock() -> None:
    async def run() -> None:
        manager = SessionManager(MockPipeline(MockBrainConfig()))
        assert await manager.try_start(opts(), None)
        await manager.cancel("session_cancel")
        assert manager.state is SessionState.IDLE
        assert not manager.active
        assert await manager.try_start(opts("next"), None)
        await manager.cancel("test_done")

    asyncio.run(run())


def test_cancel_from_processing_releases_lock() -> None:
    async def run() -> None:
        manager = SessionManager(MockPipeline(MockBrainConfig(delay_ms=50)))
        assert await manager.try_start(opts(), None)
        task = asyncio.create_task(manager.finish(frames_reported=0))
        await asyncio.sleep(0.01)
        assert manager.state is SessionState.PROCESSING
        await manager.cancel("websocket_disconnect")
        with pytest.raises(StiError):
            await task
        assert manager.state is SessionState.IDLE
        assert not manager.active

    asyncio.run(run())


def test_frame_warnings_are_logged_but_not_fatal() -> None:
    async def run() -> None:
        manager = SessionManager(MockPipeline(MockBrainConfig()))
        assert await manager.try_start(opts(), None)
        await manager.feed_audio(frame(0, reserved=1))
        await manager.feed_audio(frame(2, payload_len=4))
        result = await manager.finish(frames_reported=99)
        assert result.intent == "roll_right"
        assert manager.stats.frames_observed == 2
        assert manager.stats.audio_bytes == EXPECTED_PCM_PAYLOAD_BYTES + 4
        assert len(manager.stats.frame_warnings) >= 3
        await manager.complete()

    asyncio.run(run())

