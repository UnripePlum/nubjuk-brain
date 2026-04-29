from __future__ import annotations

import json
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter
from pydantic import ValidationError as PydanticValidationError


class ProtocolValidationError(ValueError):
    def __init__(self, message: str, correlation_id: str = "") -> None:
        super().__init__(message)
        self.correlation_id = correlation_id


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


ErrorCode = Literal["asr_failed", "slm_failed", "schema_invalid", "timeout", "internal"]


class AudioFormat(StrictModel):
    sample_rate: Literal[16000]
    channels: Literal[1]
    bit_depth: Literal[16]
    encoding: Literal["pcm_s16le"]


class SessionStartPayload(StrictModel):
    language: str = "ko"
    max_utterance_ms: int = Field(gt=0)
    audio_format: AudioFormat


class SessionStartMessage(StrictModel):
    v: Literal[1]
    type: Literal["session_start"]
    device_id: str
    correlation_id: str
    payload: SessionStartPayload


class SessionEndPayload(StrictModel):
    audio_frames_sent: int = Field(ge=0)


class SessionEndMessage(StrictModel):
    v: Literal[1]
    type: Literal["session_end"]
    correlation_id: str
    payload: SessionEndPayload


class SessionCancelPayload(StrictModel):
    reason: str


class SessionCancelMessage(StrictModel):
    v: Literal[1]
    type: Literal["session_cancel"]
    correlation_id: str
    payload: SessionCancelPayload


ClientMessage = Annotated[
    SessionStartMessage | SessionEndMessage | SessionCancelMessage,
    Field(discriminator="type"),
]

CLIENT_MESSAGE_ADAPTER = TypeAdapter(ClientMessage)


class SessionAckPayload(StrictModel):
    server_version: str
    ready_at_ms: int = Field(ge=0)


class SessionAckMessage(StrictModel):
    v: Literal[1] = 1
    type: Literal["session_ack"] = "session_ack"
    correlation_id: str
    payload: SessionAckPayload


class SessionBusyPayload(StrictModel):
    reason: Literal["single_flight", "version_mismatch", "resource_pressure"]
    retry_after_ms: int = Field(ge=0)


class SessionBusyMessage(StrictModel):
    v: Literal[1] = 1
    type: Literal["session_busy"] = "session_busy"
    correlation_id: str
    payload: SessionBusyPayload


class IntentPayload(StrictModel):
    intent: str
    slots: dict[str, Any]
    confidence: float = Field(ge=0, le=1)
    raw_text: str | None
    asr_ms: int = Field(ge=0)
    slm_ms: int = Field(ge=0)


class IntentMessage(StrictModel):
    v: Literal[1] = 1
    type: Literal["intent"] = "intent"
    correlation_id: str
    payload: IntentPayload


class ErrorPayload(StrictModel):
    code: ErrorCode
    message: str


class ErrorMessage(StrictModel):
    v: Literal[1] = 1
    type: Literal["error"] = "error"
    correlation_id: str
    payload: ErrorPayload


ServerMessage = SessionAckMessage | SessionBusyMessage | IntentMessage | ErrorMessage


def parse_client_message(raw: str | dict[str, Any]) -> ClientMessage:
    try:
        data = json.loads(raw) if isinstance(raw, str) else raw
    except json.JSONDecodeError as exc:
        raise ProtocolValidationError("invalid JSON") from exc
    try:
        return CLIENT_MESSAGE_ADAPTER.validate_python(data)
    except PydanticValidationError as exc:
        raise ProtocolValidationError(str(exc), extract_correlation_id(data)) from exc


def extract_correlation_id(data: object) -> str:
    if isinstance(data, dict):
        value = data.get("correlation_id")
        if isinstance(value, str):
            return value
    return ""


def to_wire(message: ServerMessage) -> dict[str, Any]:
    return message.model_dump(mode="json")


def make_session_ack(correlation_id: str, server_version: str, ready_at_ms: int) -> SessionAckMessage:
    return SessionAckMessage(
        correlation_id=correlation_id,
        payload=SessionAckPayload(server_version=server_version, ready_at_ms=ready_at_ms),
    )


def make_session_busy(correlation_id: str, retry_after_ms: int = 2000) -> SessionBusyMessage:
    return SessionBusyMessage(
        correlation_id=correlation_id,
        payload=SessionBusyPayload(reason="single_flight", retry_after_ms=retry_after_ms),
    )


def make_intent(
    correlation_id: str,
    intent: str,
    slots: dict[str, Any],
    confidence: float,
    raw_text: str | None,
    asr_ms: int,
    slm_ms: int,
) -> IntentMessage:
    return IntentMessage(
        correlation_id=correlation_id,
        payload=IntentPayload(
            intent=intent,
            slots=slots,
            confidence=confidence,
            raw_text=raw_text,
            asr_ms=asr_ms,
            slm_ms=slm_ms,
        ),
    )


def make_error(correlation_id: str, code: ErrorCode, message: str) -> ErrorMessage:
    return ErrorMessage(
        correlation_id=correlation_id,
        payload=ErrorPayload(code=code, message=message),
    )
