from __future__ import annotations

import asyncio
import json
import logging
import time

import pytest
from fastapi.testclient import TestClient

from brain.config import MockBrainConfig
from brain.pipeline.base import StiError
from brain.pipeline.mock import MockPipeline
from brain.session import EXPECTED_PCM_PAYLOAD_BYTES, SessionManager
import brain.ws_server as ws_server
from brain.ws_server import create_app


def start_message(correlation_id: str = "cid") -> dict:
    return {
        "v": 1,
        "type": "session_start",
        "device_id": "nubjuk-01",
        "correlation_id": correlation_id,
        "payload": {
            "language": "ko",
            "max_utterance_ms": 5000,
            "audio_format": {
                "sample_rate": 16000,
                "channels": 1,
                "bit_depth": 16,
                "encoding": "pcm_s16le",
            },
        },
    }


def end_message(correlation_id: str = "cid", frames: int = 3) -> dict:
    return {
        "v": 1,
        "type": "session_end",
        "correlation_id": correlation_id,
        "payload": {"audio_frames_sent": frames},
    }


def cancel_message(correlation_id: str = "cid") -> dict:
    return {
        "v": 1,
        "type": "session_cancel",
        "correlation_id": correlation_id,
        "payload": {"reason": "user_cancel"},
    }


def frame(seq: int, flags: int = 0, reserved: int = 0, payload_len: int = EXPECTED_PCM_PAYLOAD_BYTES) -> bytes:
    return seq.to_bytes(2, "big") + bytes([flags, reserved]) + (b"\x00" * payload_len)


class FailingPipeline(MockPipeline):
    async def finish_session(self):
        raise StiError("timeout", "mock timeout")


class FailingFeedPipeline(MockPipeline):
    async def feed_audio(self, pcm: bytes) -> None:
        raise StiError("timeout", "feed timeout")


class SlowFeedPipeline(MockPipeline):
    async def feed_audio(self, pcm: bytes) -> None:
        await asyncio.sleep(0.001)
        await super().feed_audio(pcm)


class BlockingFeedPipeline(MockPipeline):
    async def feed_audio(self, pcm: bytes) -> None:
        await asyncio.Event().wait()


def test_ws_happy_path_returns_roll_right_and_closes() -> None:
    with TestClient(create_app(MockBrainConfig())) as client:
        with client.websocket_connect("/sti") as ws:
            ws.send_json(start_message("happy"))
            ack = ws.receive_json()
            assert ack["type"] == "session_ack"
            assert ack["correlation_id"] == "happy"

            ws.send_bytes(frame(0))
            ws.send_bytes(frame(1))
            ws.send_bytes(frame(2, flags=1))
            ws.send_json(end_message("happy", frames=3))

            intent = ws.receive_json()
            assert intent["type"] == "intent"
            assert intent["correlation_id"] == "happy"
            assert intent["payload"]["intent"] == "roll_right"
            assert intent["payload"]["confidence"] == 0.92


def test_ws_drains_audio_queue_before_session_finish() -> None:
    pipeline = SlowFeedPipeline(MockBrainConfig())
    with TestClient(create_app(MockBrainConfig())) as client:
        client.app.state.manager = SessionManager(pipeline)
        with client.websocket_connect("/sti") as ws:
            ws.send_json(start_message("queued-audio"))
            assert ws.receive_json()["type"] == "session_ack"
            for seq in range(12):
                ws.send_bytes(frame(seq))
            ws.send_json(end_message("queued-audio", frames=12))

            intent = ws.receive_json()
            assert intent["type"] == "intent"

    assert pipeline.audio_bytes == 12 * EXPECTED_PCM_PAYLOAD_BYTES


def test_ws_audio_worker_error_returns_error_and_releases_lock() -> None:
    with TestClient(create_app(MockBrainConfig())) as client:
        client.app.state.manager = SessionManager(FailingFeedPipeline(MockBrainConfig()))

        with client.websocket_connect("/sti") as ws:
            ws.send_json(start_message("feed-error"))
            assert ws.receive_json()["type"] == "session_ack"
            ws.send_bytes(frame(0))
            ws.send_json(end_message("feed-error", frames=1))
            error = ws.receive_json()
            assert error["type"] == "error"
            assert error["correlation_id"] == "feed-error"
            assert error["payload"]["code"] == "timeout"

        client.app.state.manager = SessionManager(MockPipeline(MockBrainConfig()))
        with client.websocket_connect("/sti") as next_ws:
            next_ws.send_json(start_message("after-feed-error"))
            assert next_ws.receive_json()["type"] == "session_ack"


def test_ws_audio_queue_full_returns_error_without_blocking(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ws_server, "WS_AUDIO_QUEUE_MAXSIZE", 1)
    with TestClient(create_app(MockBrainConfig())) as client:
        client.app.state.manager = SessionManager(BlockingFeedPipeline(MockBrainConfig()))

        with client.websocket_connect("/sti") as ws:
            ws.send_json(start_message("queue-full"))
            assert ws.receive_json()["type"] == "session_ack"
            ws.send_bytes(frame(0))
            ws.send_bytes(frame(1))
            ws.send_bytes(frame(2))

            error = ws.receive_json()
            assert error["type"] == "error"
            assert error["correlation_id"] == "queue-full"
            assert error["payload"]["code"] == "timeout"
            assert "audio queue full" in error["payload"]["message"]

        client.app.state.manager = SessionManager(MockPipeline(MockBrainConfig()))
        with client.websocket_connect("/sti") as next_ws:
            next_ws.send_json(start_message("after-queue-full"))
            assert next_ws.receive_json()["type"] == "session_ack"


def test_ws_logs_intent_send(caplog) -> None:
    caplog.set_level(logging.INFO, logger="uvicorn.error")
    audio_frame = frame(0, flags=1)
    with TestClient(create_app(MockBrainConfig())) as client:
        with client.websocket_connect("/sti") as ws:
            ws.send_json(start_message("send-log"))
            assert ws.receive_json()["type"] == "session_ack"
            ws.send_bytes(audio_frame)
            ws.send_json(end_message("send-log", frames=1))
            assert ws.receive_json()["type"] == "intent"

    payloads = []
    for record in caplog.records:
        try:
            payloads.append(json.loads(record.message))
        except json.JSONDecodeError:
            pass
    connection = next(payload for payload in payloads if payload.get("event") == "ws_connection_accepted")
    assert connection["ws_audio_queue_maxsize"] == ws_server.WS_AUDIO_QUEUE_MAXSIZE
    audio_enqueued = next(payload for payload in payloads if payload.get("event") == "audio_frame_enqueued")
    assert audio_enqueued["correlation_id"] == "send-log"
    assert audio_enqueued["frames_received"] == 1
    assert audio_enqueued["seq"] == 0
    assert audio_enqueued["wire_bytes"] == len(audio_frame)
    worker_feed = next(payload for payload in payloads if payload.get("event") == "audio_worker_feed")
    assert worker_feed["correlation_id"] == "send-log"
    assert worker_feed["frames_processed"] == 1
    assert worker_feed["seq"] == 0
    intent_send = next(payload for payload in payloads if payload.get("event") == "intent_send")
    assert intent_send["correlation_id"] == "send-log"
    assert intent_send["intent"] == "roll_right"
    assert intent_send["confidence"] == 0.92
    assert intent_send["raw_text"] == "mock: roll_right"


def test_ws_schema_invalid_is_recoverable_before_start() -> None:
    with TestClient(create_app(MockBrainConfig())) as client:
        with client.websocket_connect("/sti") as ws:
            bad = start_message("recover")
            bad["v"] = 2
            ws.send_json(bad)
            error = ws.receive_json()
            assert error["type"] == "error"
            assert error["correlation_id"] == "recover"
            assert error["payload"]["code"] == "schema_invalid"

            ws.send_json(start_message("recover"))
            ack = ws.receive_json()
            assert ack["type"] == "session_ack"


def test_ws_pipeline_error_returns_error_and_releases_lock() -> None:
    with TestClient(create_app(MockBrainConfig())) as client:
        client.app.state.manager = SessionManager(FailingPipeline(MockBrainConfig()))

        with client.websocket_connect("/sti") as ws:
            ws.send_json(start_message("pipeline-error"))
            assert ws.receive_json()["type"] == "session_ack"
            ws.send_json(end_message("pipeline-error", frames=0))
            error = ws.receive_json()
            assert error["type"] == "error"
            assert error["correlation_id"] == "pipeline-error"
            assert error["payload"]["code"] == "timeout"

        client.app.state.manager = SessionManager(MockPipeline(MockBrainConfig()))
        with client.websocket_connect("/sti") as next_ws:
            next_ws.send_json(start_message("after-error"))
            assert next_ws.receive_json()["type"] == "session_ack"


def test_ws_busy_response_shape_and_cleanup() -> None:
    with TestClient(create_app(MockBrainConfig())) as client:
        with client.websocket_connect("/sti") as ws_a:
            ws_a.send_json(start_message("a"))
            assert ws_a.receive_json()["type"] == "session_ack"

            with client.websocket_connect("/sti") as ws_b:
                ws_b.send_json(start_message("b"))
                busy = ws_b.receive_json()
                assert busy["type"] == "session_busy"
                assert busy["correlation_id"] == "b"
                assert busy["payload"]["reason"] == "single_flight"

        with client.websocket_connect("/sti") as ws_c:
            ws_c.send_json(start_message("c"))
            assert ws_c.receive_json()["type"] == "session_ack"


def test_ws_disconnect_during_audio_in_releases_lock() -> None:
    with TestClient(create_app(MockBrainConfig())) as client:
        with client.websocket_connect("/sti") as ws:
            ws.send_json(start_message("drop-audio"))
            assert ws.receive_json()["type"] == "session_ack"

        with client.websocket_connect("/sti") as next_ws:
            next_ws.send_json(start_message("next"))
            assert next_ws.receive_json()["type"] == "session_ack"


def test_ws_session_cancel_releases_lock() -> None:
    with TestClient(create_app(MockBrainConfig())) as client:
        with client.websocket_connect("/sti") as ws:
            ws.send_json(start_message("cancel"))
            assert ws.receive_json()["type"] == "session_ack"
            ws.send_json(cancel_message("cancel"))

        with client.websocket_connect("/sti") as next_ws:
            next_ws.send_json(start_message("after-cancel"))
            assert next_ws.receive_json()["type"] == "session_ack"


def test_ws_disconnect_during_processing_releases_lock() -> None:
    with TestClient(create_app(MockBrainConfig(delay_ms=50))) as client:
        with client.websocket_connect("/sti") as ws:
            ws.send_json(start_message("processing"))
            assert ws.receive_json()["type"] == "session_ack"
            ws.send_json(end_message("processing", frames=0))

        deadline = time.monotonic() + 1.0
        while True:
            with client.websocket_connect("/sti") as next_ws:
                next_ws.send_json(start_message("after-processing-drop"))
                response = next_ws.receive_json()
                if response["type"] == "session_ack":
                    return
                assert response["type"] == "session_busy"
            if time.monotonic() > deadline:
                raise AssertionError("session lock was not released after processing disconnect")
            time.sleep(0.05)
