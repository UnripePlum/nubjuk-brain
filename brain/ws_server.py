from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress
from typing import cast

from fastapi import FastAPI, WebSocket, WebSocketDisconnect

from brain.config import MockBrainConfig
from brain.pipeline.base import SessionOpts, StiError
from brain.pipeline.mock import MockPipeline
from brain.schema import (
    ErrorCode,
    ProtocolValidationError,
    SessionCancelMessage,
    SessionEndMessage,
    SessionStartMessage,
    make_error,
    make_intent,
    make_session_ack,
    make_session_busy,
    parse_client_message,
    to_wire,
)
from brain.session import SessionManager


def create_app(config: MockBrainConfig | None = None) -> FastAPI:
    resolved_config = config or MockBrainConfig.from_env()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.config = resolved_config
        app.state.manager = SessionManager(MockPipeline(resolved_config))
        yield

    app = FastAPI(lifespan=lifespan)

    @app.websocket("/sti")
    async def sti(websocket: WebSocket) -> None:
        await websocket.accept()
        manager: SessionManager = websocket.app.state.manager
        cfg: MockBrainConfig = websocket.app.state.config
        started = False

        try:
            while True:
                raw = await websocket.receive()
                if raw["type"] == "websocket.disconnect":
                    if started:
                        await manager.cancel("websocket_disconnect")
                    return

                if "bytes" in raw and raw["bytes"] is not None:
                    if started:
                        await manager.feed_audio(raw["bytes"])
                    else:
                        await _send_schema_invalid(websocket, "", "binary frame before session_start")
                    continue

                text = raw.get("text")
                if text is None:
                    await _send_schema_invalid(websocket, "", "unsupported websocket message")
                    continue

                try:
                    message = parse_client_message(text)
                except ProtocolValidationError as exc:
                    await _send_schema_invalid(websocket, exc.correlation_id, str(exc))
                    continue

                if isinstance(message, SessionStartMessage):
                    ready_started = time.monotonic()
                    opts = SessionOpts(
                        correlation_id=message.correlation_id,
                        max_utterance_ms=message.payload.max_utterance_ms,
                        language=message.payload.language,
                    )
                    if not await manager.try_start(opts, websocket):
                        await websocket.send_json(to_wire(make_session_busy(message.correlation_id)))
                        await websocket.close()
                        return
                    started = True
                    ready_at_ms = int((time.monotonic() - ready_started) * 1000)
                    await websocket.send_json(
                        to_wire(make_session_ack(message.correlation_id, cfg.server_version, ready_at_ms))
                    )
                    continue

                if not started:
                    await _send_schema_invalid(websocket, message.correlation_id, "session_start required")
                    continue

                if isinstance(message, SessionEndMessage):
                    try:
                        result = await _finish_or_cancel_on_disconnect(
                            websocket,
                            manager,
                            message.payload.audio_frames_sent,
                        )
                    except StiError as exc:
                        await websocket.send_json(
                            to_wire(make_error(message.correlation_id, _safe_error_code(exc.code), str(exc)))
                        )
                        with suppress(RuntimeError):
                            await websocket.close()
                        return
                    if result is None:
                        return

                    try:
                        await websocket.send_json(
                            to_wire(
                                make_intent(
                                    message.correlation_id,
                                    result.intent,
                                    result.slots,
                                    result.confidence,
                                    result.raw_text,
                                    result.asr_ms,
                                    result.slm_ms,
                                )
                            )
                        )
                    except (WebSocketDisconnect, RuntimeError):
                        await manager.cancel("websocket_disconnect")
                        return
                    await manager.complete("intent_sent")
                    try:
                        await websocket.close()
                    except RuntimeError:
                        pass
                    return

                if isinstance(message, SessionCancelMessage):
                    await manager.cancel("session_cancel")
                    await websocket.close()
                    return

        except WebSocketDisconnect:
            if started:
                await manager.cancel("websocket_disconnect")

    return app


async def _send_schema_invalid(websocket: WebSocket, correlation_id: str, message: str) -> None:
    await websocket.send_json(to_wire(make_error(correlation_id, "schema_invalid", message)))


async def _finish_or_cancel_on_disconnect(
    websocket: WebSocket,
    manager: SessionManager,
    frames_reported: int,
):
    finish_task = asyncio.create_task(manager.finish(frames_reported))
    disconnect_task = asyncio.create_task(_wait_for_disconnect_or_cancel(websocket))
    done, _pending = await asyncio.wait(
        {finish_task, disconnect_task},
        return_when=asyncio.FIRST_COMPLETED,
    )

    if disconnect_task in done:
        reason = disconnect_task.result()
        finish_task.cancel()
        with suppress(asyncio.CancelledError):
            await finish_task
        await manager.cancel(reason)
        return None

    disconnect_task.cancel()
    with suppress(asyncio.CancelledError):
        await disconnect_task

    try:
        return finish_task.result()
    except StiError:
        await manager.cancel("pipeline_error")
        raise


async def _wait_for_disconnect_or_cancel(websocket: WebSocket) -> str:
    while True:
        raw = await websocket.receive()
        if raw["type"] == "websocket.disconnect":
            return "websocket_disconnect"
        text = raw.get("text")
        if text is None:
            continue
        try:
            message = parse_client_message(text)
        except ProtocolValidationError:
            continue
        if isinstance(message, SessionCancelMessage):
            return "session_cancel"


def _safe_error_code(code: str) -> ErrorCode:
    if code in {"asr_failed", "slm_failed", "schema_invalid", "timeout", "internal"}:
        return cast(ErrorCode, code)
    return "internal"


app = create_app()
