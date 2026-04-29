from __future__ import annotations

import time

from fastapi.testclient import TestClient

from brain.config import MockBrainConfig
from brain.pipeline.base import StiError
from brain.pipeline.mock import MockPipeline
from brain.session import EXPECTED_PCM_PAYLOAD_BYTES, SessionManager
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
