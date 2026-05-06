from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress
from os import getpid
from typing import cast

from fastapi import FastAPI, WebSocket, WebSocketDisconnect

from brain.config import MockBrainConfig, RuntimeConfig, load_config_from_env
from brain.pipeline.base import SessionOpts, StiError
from brain.pipeline.mock import MockPipeline
from brain.pipeline.moonshine_tiny_ko import MoonshineTinyKoRulesPipeline
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

LOGGER = logging.getLogger("uvicorn.error")
WS_AUDIO_QUEUE_MAXSIZE = int(os.getenv("BRAIN_WS_AUDIO_QUEUE_MAXSIZE", os.getenv("BRAIN_WS_MAX_QUEUE", "256")))


def create_app(config: RuntimeConfig | None = None) -> FastAPI:
    _configure_app_logging()
    resolved_config = config or load_config_from_env()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.config = resolved_config
        pipeline = _build_pipeline(resolved_config)
        app.state.pipeline = pipeline
        app.state.manager = SessionManager(pipeline)
        LOGGER.info(
            json.dumps(
                {
                    "event": "pipeline_selected",
                    "pipeline": resolved_config.pipeline,
                    "server_version": resolved_config.server_version,
                    "slm_enabled": getattr(resolved_config, "slm_enabled", False),
                    "pid": getpid(),
                    "ws_audio_queue_maxsize": WS_AUDIO_QUEUE_MAXSIZE,
                    "intent_catalog_path": getattr(resolved_config, "intent_catalog_path", None),
                },
                separators=(",", ":"),
                ensure_ascii=False,
            )
        )
        try:
            yield
        finally:
            close = getattr(pipeline, "close", None)
            if close is not None:
                await close()

    app = FastAPI(lifespan=lifespan)

    @app.websocket("/sti")
    async def sti(websocket: WebSocket) -> None:
        await websocket.accept()
        manager: SessionManager = websocket.app.state.manager
        cfg: RuntimeConfig = websocket.app.state.config
        started = False
        correlation_id = ""
        binary_frames_received = 0
        audio_queue: asyncio.Queue[bytes] = asyncio.Queue(maxsize=WS_AUDIO_QUEUE_MAXSIZE)
        audio_error: asyncio.Future[None] = asyncio.get_running_loop().create_future()
        audio_worker = asyncio.create_task(_audio_feed_worker(manager, audio_queue, audio_error))
        _log_ws_connection_accepted(websocket)

        try:
            while True:
                raw = await websocket.receive()
                if raw["type"] == "websocket.disconnect":
                    _log_ws_disconnect(correlation_id, "receive_disconnect", raw, started=started)
                    if started:
                        await manager.cancel("websocket_disconnect")
                    return

                if "bytes" in raw and raw["bytes"] is not None:
                    if started:
                        try:
                            binary_frames_received += 1
                            _raise_audio_worker_error(audio_error)
                            queue_depth = _enqueue_audio_frame(audio_queue, raw["bytes"])
                            _log_audio_frame_enqueued(
                                correlation_id,
                                raw["bytes"],
                                frames_received=binary_frames_received,
                                queue_depth=queue_depth,
                            )
                            _raise_audio_worker_error(audio_error)
                        except StiError as exc:
                            correlation_id = manager.opts.correlation_id if manager.opts else ""
                            await websocket.send_json(
                                to_wire(make_error(correlation_id, _safe_error_code(exc.code), str(exc)))
                            )
                            await manager.cancel("pipeline_error")
                            with suppress(RuntimeError):
                                await websocket.close()
                            return
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
                    correlation_id = message.correlation_id
                    ready_started = time.monotonic()
                    opts = SessionOpts(
                        correlation_id=message.correlation_id,
                        max_utterance_ms=message.payload.max_utterance_ms,
                        language=message.payload.language,
                    )
                    if not await manager.try_start(opts, websocket):
                        _log_session_busy(message.correlation_id)
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
                        await _wait_for_audio_queue_drained(audio_queue, audio_error)
                        result = await _finish_session_or_cancel_on_error(
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

                    intent_message = make_intent(
                        message.correlation_id,
                        result.intent,
                        result.slots,
                        result.confidence,
                        result.raw_text,
                        result.asr_ms,
                        result.slm_ms,
                    )
                    _log_intent_send(message.correlation_id, result)
                    try:
                        await websocket.send_json(to_wire(intent_message))
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

        except WebSocketDisconnect as exc:
            _log_ws_disconnect(correlation_id, "websocket_disconnect_exception", exc, started=started)
            if started:
                await manager.cancel("websocket_disconnect")
        finally:
            await _cancel_audio_worker(audio_worker)

    return app


def _configure_app_logging() -> None:
    logging.getLogger("uvicorn.error").setLevel(logging.INFO)


def _log_intent_send(correlation_id: str, result) -> None:
    LOGGER.info(
        json.dumps(
            {
                "event": "intent_send",
                "correlation_id": correlation_id,
                "intent": result.intent,
                "confidence": result.confidence,
                "raw_text": result.raw_text,
                "asr_ms": result.asr_ms,
                "slm_ms": result.slm_ms,
            },
            separators=(",", ":"),
            ensure_ascii=False,
        )
    )


def _log_session_busy(correlation_id: str) -> None:
    LOGGER.info(
        json.dumps(
            {
                "event": "session_busy_send",
                "correlation_id": correlation_id,
                "reason": "single_flight",
            },
            separators=(",", ":"),
            ensure_ascii=False,
        )
    )


def _log_ws_connection_accepted(websocket: WebSocket) -> None:
    client = websocket.client
    LOGGER.info(
        json.dumps(
            {
                "event": "ws_connection_accepted",
                "pid": getpid(),
                "client_host": client.host if client else None,
                "client_port": client.port if client else None,
                "ws_audio_queue_maxsize": WS_AUDIO_QUEUE_MAXSIZE,
            },
            separators=(",", ":"),
            ensure_ascii=False,
        )
    )


def _log_audio_frame_enqueued(
    correlation_id: str,
    frame: bytes,
    *,
    frames_received: int,
    queue_depth: int,
) -> None:
    if not _should_log_audio_frame(frames_received):
        return
    LOGGER.info(
        json.dumps(
            {
                "event": "audio_frame_enqueued",
                "correlation_id": correlation_id,
                "frames_received": frames_received,
                "seq": _frame_seq(frame),
                "wire_bytes": len(frame),
                "queue_depth": queue_depth,
                "queue_max_frames": WS_AUDIO_QUEUE_MAXSIZE,
            },
            separators=(",", ":"),
            ensure_ascii=False,
        )
    )


def _log_ws_disconnect(correlation_id: str, source: str, event, *, started: bool) -> None:
    if isinstance(event, dict):
        code = event.get("code")
        reason = event.get("reason")
    else:
        code = getattr(event, "code", None)
        reason = getattr(event, "reason", None)
    LOGGER.info(
        json.dumps(
            {
                "event": "ws_disconnect",
                "correlation_id": correlation_id,
                "source": source,
                "started": started,
                "code": code,
                "reason": reason,
            },
            separators=(",", ":"),
            ensure_ascii=False,
        )
    )


def _build_pipeline(config: RuntimeConfig):
    if isinstance(config, MockBrainConfig):
        return MockPipeline(config)
    return MoonshineTinyKoRulesPipeline(config)


async def _send_schema_invalid(websocket: WebSocket, correlation_id: str, message: str) -> None:
    await websocket.send_json(to_wire(make_error(correlation_id, "schema_invalid", message)))


async def _audio_feed_worker(
    manager: SessionManager,
    audio_queue: asyncio.Queue[bytes],
    audio_error: asyncio.Future[None],
) -> None:
    frames_processed = 0
    try:
        while True:
            frame = await audio_queue.get()
            started = time.monotonic()
            try:
                await manager.feed_audio(frame)
                frames_processed += 1
                _log_audio_worker_feed(
                    manager.opts.correlation_id if manager.opts else "",
                    frame,
                    frames_processed=frames_processed,
                    queue_depth=audio_queue.qsize(),
                    feed_ms=int((time.monotonic() - started) * 1000),
                )
            except StiError as exc:
                if not audio_error.done():
                    audio_error.set_exception(exc)
                return
            except Exception as exc:  # pragma: no cover - defensive guard for unexpected pipeline bugs.
                if not audio_error.done():
                    audio_error.set_exception(StiError("internal", str(exc)))
                return
            finally:
                audio_queue.task_done()
    except asyncio.CancelledError:
        raise


async def _wait_for_audio_queue_drained(
    audio_queue: asyncio.Queue[bytes],
    audio_error: asyncio.Future[None],
) -> None:
    _raise_audio_worker_error(audio_error)
    drain_task = asyncio.create_task(audio_queue.join())
    done, _pending = await asyncio.wait(
        {drain_task, audio_error},
        return_when=asyncio.FIRST_COMPLETED,
    )
    if audio_error in done:
        drain_task.cancel()
        with suppress(asyncio.CancelledError):
            await drain_task
        _raise_audio_worker_error(audio_error)
    await drain_task
    _raise_audio_worker_error(audio_error)


def _raise_audio_worker_error(audio_error: asyncio.Future[None]) -> None:
    if audio_error.done():
        audio_error.result()


def _enqueue_audio_frame(audio_queue: asyncio.Queue[bytes], frame: bytes) -> int:
    try:
        audio_queue.put_nowait(frame)
        return audio_queue.qsize()
    except asyncio.QueueFull as exc:
        raise StiError("timeout", f"audio queue full max_frames={WS_AUDIO_QUEUE_MAXSIZE}") from exc


def _log_audio_worker_feed(
    correlation_id: str,
    frame: bytes,
    *,
    frames_processed: int,
    queue_depth: int,
    feed_ms: int,
) -> None:
    if not _should_log_audio_frame(frames_processed) and feed_ms < 5:
        return
    LOGGER.info(
        json.dumps(
            {
                "event": "audio_worker_feed",
                "correlation_id": correlation_id,
                "frames_processed": frames_processed,
                "seq": _frame_seq(frame),
                "feed_ms": feed_ms,
                "queue_depth": queue_depth,
                "queue_max_frames": WS_AUDIO_QUEUE_MAXSIZE,
            },
            separators=(",", ":"),
            ensure_ascii=False,
        )
    )


def _should_log_audio_frame(count: int) -> bool:
    return count <= 8 or count % 16 == 0


def _frame_seq(frame: bytes) -> int | None:
    if len(frame) < 2:
        return None
    return int.from_bytes(frame[0:2], byteorder="big", signed=False)


async def _cancel_audio_worker(audio_worker: asyncio.Task[None]) -> None:
    audio_worker.cancel()
    with suppress(asyncio.CancelledError):
        await audio_worker


async def _finish_session_or_cancel_on_error(
    websocket: WebSocket,
    manager: SessionManager,
    frames_reported: int,
):
    finish_task = asyncio.create_task(manager.finish(frames_reported))
    disconnect_task = asyncio.create_task(_cancel_finish_on_disconnect(websocket, manager, finish_task))
    try:
        return await finish_task
    except asyncio.CancelledError:
        return None
    except StiError:
        await manager.cancel("pipeline_error")
        raise
    finally:
        disconnect_task.cancel()
        disconnect_task.add_done_callback(_discard_task_result)


async def _cancel_finish_on_disconnect(
    websocket: WebSocket,
    manager: SessionManager,
    finish_task: asyncio.Task,
) -> None:
    reason = "websocket_disconnect"
    try:
        reason = await _wait_for_disconnect_or_cancel(websocket)
    except (WebSocketDisconnect, RuntimeError):
        pass
    if not finish_task.done():
        finish_task.cancel()
        await manager.cancel(reason)


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


def _discard_task_result(task: asyncio.Task) -> None:
    with suppress(BaseException):
        task.result()


def _safe_error_code(code: str) -> ErrorCode:
    if code in {"asr_failed", "slm_failed", "schema_invalid", "timeout", "internal"}:
        return cast(ErrorCode, code)
    return "internal"


app = create_app()
