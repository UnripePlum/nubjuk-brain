from __future__ import annotations

import pytest

from brain.schema import (
    ErrorMessage,
    IntentMessage,
    ProtocolValidationError,
    SessionAckMessage,
    SessionBusyMessage,
    make_error,
    make_intent,
    make_session_ack,
    make_session_busy,
    parse_client_message,
    to_wire,
)


SESSION_START = {
    "v": 1,
    "type": "session_start",
    "device_id": "nubjuk-01",
    "correlation_id": "01Jcid",
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

SESSION_END = {
    "v": 1,
    "type": "session_end",
    "correlation_id": "01Jcid",
    "payload": {"audio_frames_sent": 87},
}

SESSION_CANCEL = {
    "v": 1,
    "type": "session_cancel",
    "correlation_id": "01Jcid",
    "payload": {"reason": "user_cancel"},
}


def test_protocol_client_examples_validate() -> None:
    assert parse_client_message(SESSION_START).type == "session_start"
    assert parse_client_message(SESSION_END).type == "session_end"
    assert parse_client_message(SESSION_CANCEL).type == "session_cancel"


def test_protocol_server_examples_validate() -> None:
    SessionAckMessage.model_validate(
        {
            "v": 1,
            "type": "session_ack",
            "correlation_id": "01Jcid",
            "payload": {"server_version": "0.4.1", "ready_at_ms": 12},
        }
    )
    SessionBusyMessage.model_validate(
        {
            "v": 1,
            "type": "session_busy",
            "correlation_id": "01Jcid",
            "payload": {"reason": "single_flight", "retry_after_ms": 2000},
        }
    )
    IntentMessage.model_validate(
        {
            "v": 1,
            "type": "intent",
            "correlation_id": "01Jcid",
            "payload": {
                "intent": "sit",
                "slots": {},
                "confidence": 0.91,
                "raw_text": "sit",
                "asr_ms": 320,
                "slm_ms": 480,
            },
        }
    )
    ErrorMessage.model_validate(
        {
            "v": 1,
            "type": "error",
            "correlation_id": "01Jcid",
            "payload": {"code": "asr_failed", "message": "Whisper returned empty"},
        }
    )


def test_generated_responses_match_envelope_shape() -> None:
    for message in [
        make_session_ack("cid", "0.1.0", 1),
        make_session_busy("cid"),
        make_intent("cid", "roll_right", {}, 0.92, "mock: roll_right", 0, 0),
        make_error("cid", "schema_invalid", "bad payload"),
    ]:
        dumped = to_wire(message)
        assert dumped["v"] == 1
        assert "type" in dumped
        assert dumped["correlation_id"] == "cid"
        assert "payload" in dumped


@pytest.mark.parametrize(
    "message",
    [
        {**SESSION_START, "v": 2},
        {**SESSION_START, "type": "not_real"},
        {
            **SESSION_START,
            "payload": {
                **SESSION_START["payload"],
                "audio_format": {**SESSION_START["payload"]["audio_format"], "sample_rate": 8000},
            },
        },
    ],
)
def test_invalid_client_messages_fail_validation(message: dict) -> None:
    with pytest.raises(ProtocolValidationError) as exc:
        parse_client_message(message)
    assert exc.value.correlation_id == "01Jcid"

