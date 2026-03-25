import asyncio
import contextlib
from dataclasses import asdict
from typing import Annotated, Any

from fastapi import APIRouter, HTTPException, Query, WebSocket, WebSocketDisconnect

from app.api.http.deps import DebugIMServiceDep
from app.api.http.schemas.debug_im import (
    DebugIMMessageListResponse,
    DebugIMMessageResponse,
    DebugIMSendMessageRequest,
    DebugIMSendMessageResponse,
    DebugIMSessionListResponse,
    DebugIMSessionResponse,
)
from app.application.debug_im.commands import SendDebugIMMessageCommand
from app.application.debug_im.dto import DebugIMMessageDTO
from app.application.debug_im.queries import (
    ListDebugIMMessagesQuery,
    ListDebugIMSessionsQuery,
    PollDebugIMMessagesQuery,
)

router = APIRouter(prefix="/debug/im", tags=["debug-im"])

WEBSOCKET_POLL_INTERVAL_SECONDS = 0.25


@router.post(
    "/messages",
    summary="模拟调试 IM 发送消息",
    response_model_exclude_none=True,
)
async def send_debug_im_message(
    payload: DebugIMSendMessageRequest,
    service: DebugIMServiceDep,
) -> DebugIMSendMessageResponse:
    result = await service.send_message(
        SendDebugIMMessageCommand(
            user_identity=payload.user_identity,
            text=payload.text,
            chat_id=payload.chat_id,
            thread_id=payload.thread_id,
            reply_to_message_id=payload.reply_to_message_id,
            raw_payload=payload.raw_payload,
        )
    )
    return DebugIMSendMessageResponse(**asdict(result))


@router.get("/messages", summary="查询调试 IM 最近消息")
async def list_debug_im_messages(
    service: DebugIMServiceDep,
    user_identity: Annotated[str, Query(min_length=1)],
    chat_id: Annotated[str | None, Query()] = None,
    thread_id: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> DebugIMMessageListResponse:
    _raise_if_invalid_thread_pair(chat_id=chat_id, thread_id=thread_id)
    result = await service.list_messages(
        ListDebugIMMessagesQuery(
            user_identity=user_identity,
            chat_id=chat_id,
            thread_id=thread_id,
            limit=limit,
        )
    )
    return DebugIMMessageListResponse(
        items=[DebugIMMessageResponse(**asdict(item)) for item in result.items]
    )


@router.get("/sessions", summary="查询调试 IM 最近会话")
async def list_debug_im_sessions(
    service: DebugIMServiceDep,
    user_identity: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 20,
) -> DebugIMSessionListResponse:
    result = await service.list_sessions(
        ListDebugIMSessionsQuery(
            user_identity=user_identity,
            limit=limit,
        )
    )
    return DebugIMSessionListResponse(
        items=[DebugIMSessionResponse(**asdict(item)) for item in result.items]
    )


@router.websocket("/ws")
async def debug_im_websocket(
    websocket: WebSocket,
    service: DebugIMServiceDep,
) -> None:
    await websocket.accept()
    validation_error = _validate_websocket_query(websocket)
    if validation_error is not None:
        await websocket.send_json({"type": "error", "detail": validation_error})
        await websocket.close(code=1008)
        return

    user_identity = websocket.query_params["user_identity"]
    chat_id = _optional_query_param(websocket, "chat_id")
    thread_id = _optional_query_param(websocket, "thread_id")
    history_limit = _parse_history_limit(websocket)
    send_lock = asyncio.Lock()

    history = await service.list_messages(
        ListDebugIMMessagesQuery(
            user_identity=user_identity,
            chat_id=chat_id,
            thread_id=thread_id,
            limit=history_limit,
        )
    )
    await _send_json(
        websocket,
        send_lock,
        {
            "type": "history_snapshot",
            "messages": [_serialize_message(item) for item in history.items],
        },
    )

    latest_recorded_at = history.items[-1].recorded_at if history.items else None
    latest_event_id = history.items[-1].event_id if history.items else None

    poll_task = asyncio.create_task(
        _poll_debug_im_messages(
            websocket=websocket,
            send_lock=send_lock,
            service=service,
            user_identity=user_identity,
            chat_id=chat_id,
            thread_id=thread_id,
            latest_recorded_at=latest_recorded_at,
            latest_event_id=latest_event_id,
        )
    )
    try:
        while True:
            payload = await websocket.receive_json()
            event_type = payload.get("type")
            if event_type == "ping":
                await _send_json(websocket, send_lock, {"type": "pong"})
                continue
            if event_type != "send_message":
                await _send_json(
                    websocket,
                    send_lock,
                    {"type": "error", "detail": "不支持的 websocket 事件类型。"},
                )
                continue

            text = payload.get("text")
            if not isinstance(text, str) or not text.strip():
                await _send_json(
                    websocket,
                    send_lock,
                    {"type": "error", "detail": "send_message 事件必须提供非空 text。"},
                )
                continue

            reply_to_message_id = payload.get("reply_to_message_id")
            if reply_to_message_id is not None and not isinstance(reply_to_message_id, str):
                await _send_json(
                    websocket,
                    send_lock,
                    {"type": "error", "detail": "reply_to_message_id 必须是字符串。"},
                )
                continue

            result = await service.send_message(
                SendDebugIMMessageCommand(
                    user_identity=user_identity,
                    text=text.strip(),
                    chat_id=chat_id,
                    thread_id=thread_id,
                    reply_to_message_id=reply_to_message_id,
                    raw_payload=_build_websocket_raw_payload(
                        text=text.strip(),
                        chat_id=chat_id,
                        thread_id=thread_id,
                        reply_to_message_id=reply_to_message_id,
                    ),
                )
            )
            await _send_json(
                websocket,
                send_lock,
                {
                    "type": "message_ack",
                    "result": asdict(result),
                },
            )
    except WebSocketDisconnect:
        return
    finally:
        poll_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await poll_task


async def _poll_debug_im_messages(
    *,
    websocket: WebSocket,
    send_lock: asyncio.Lock,
    service: DebugIMServiceDep,
    user_identity: str,
    chat_id: str | None,
    thread_id: str | None,
    latest_recorded_at: str | None,
    latest_event_id: str | None,
) -> None:
    while True:
        await asyncio.sleep(WEBSOCKET_POLL_INTERVAL_SECONDS)
        result = await service.list_messages_after(
            PollDebugIMMessagesQuery(
                user_identity=user_identity,
                chat_id=chat_id,
                thread_id=thread_id,
                after_recorded_at=latest_recorded_at,
                after_event_id=latest_event_id,
                limit=100,
            )
        )
        for item in result.items:
            latest_recorded_at = item.recorded_at
            latest_event_id = item.event_id
            await _send_json(
                websocket,
                send_lock,
                {"type": "message_created", "message": _serialize_message(item)},
            )


async def _send_json(
    websocket: WebSocket,
    send_lock: asyncio.Lock,
    payload: dict[str, Any],
) -> None:
    async with send_lock:
        await websocket.send_json(payload)


def _serialize_message(item: DebugIMMessageDTO) -> dict[str, Any]:
    return asdict(item)


def _raise_if_invalid_thread_pair(
    *,
    chat_id: str | None,
    thread_id: str | None,
) -> None:
    if thread_id is not None and chat_id is None:
        raise HTTPException(status_code=422, detail="thread_id 不能脱离 chat_id 单独提供。")


def _validate_websocket_query(websocket: WebSocket) -> str | None:
    user_identity = _optional_query_param(websocket, "user_identity")
    if user_identity is None or not user_identity.strip():
        return "websocket 连接必须提供非空 user_identity。"
    chat_id = _optional_query_param(websocket, "chat_id")
    thread_id = _optional_query_param(websocket, "thread_id")
    if thread_id is not None and chat_id is None:
        return "thread_id 不能脱离 chat_id 单独提供。"
    return None


def _parse_history_limit(websocket: WebSocket) -> int:
    raw_limit = _optional_query_param(websocket, "history_limit")
    if raw_limit is None:
        return 20
    try:
        parsed = int(raw_limit)
    except ValueError:
        return 20
    return min(max(parsed, 1), 200)


def _optional_query_param(websocket: WebSocket, key: str) -> str | None:
    value = websocket.query_params.get(key)
    if value is None or not value.strip():
        return None
    return value


def _build_websocket_raw_payload(
    *,
    text: str,
    chat_id: str | None,
    thread_id: str | None,
    reply_to_message_id: str | None,
) -> dict[str, str]:
    payload: dict[str, str] = {
        "transport": "websocket",
        "text": text,
    }
    if chat_id is not None:
        payload["chat_id"] = chat_id
    if thread_id is not None:
        payload["thread_id"] = thread_id
    if reply_to_message_id is not None:
        payload["reply_to_message_id"] = reply_to_message_id
    return payload
