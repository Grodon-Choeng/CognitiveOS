from collections import deque
from dataclasses import dataclass

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.http.deps.services import get_debug_im_service
from app.application.debug_im.commands import SendDebugIMMessageCommand
from app.application.debug_im.dto import (
    DebugIMMessageDTO,
    DebugIMMessageListDTO,
    DebugIMSendMessageDTO,
    DebugIMSessionDTO,
    DebugIMSessionListDTO,
)
from app.application.debug_im.queries import (
    ListDebugIMMessagesQuery,
    ListDebugIMSessionsQuery,
    PollDebugIMMessagesQuery,
)


@dataclass
class FakeDebugIMService:
    def __post_init__(self) -> None:
        self.sent_commands: list[SendDebugIMMessageCommand] = []
        self.pending_messages: deque[DebugIMMessageDTO] = deque()

    async def send_message(
        self,
        command: SendDebugIMMessageCommand,
    ) -> DebugIMSendMessageDTO:
        self.sent_commands.append(command)
        self.pending_messages.append(
            DebugIMMessageDTO(
                event_id="event-new",
                recorded_at="2026-03-25T10:00:01+08:00",
                direction="outbound",
                channel="debug_im",
                user_identity=command.user_identity,
                chat_id=command.chat_id,
                thread_id=command.thread_id,
                conversation_id="conversation-1",
                session_id="session-1",
                external_message_id="dbgout_1",
                root_message_id="dbgroot_1",
                parent_message_id="dbgmsg_1",
                text="好的，已收到。",
                success=True,
                adapter_name="debug_im",
                metadata={},
            )
        )
        return DebugIMSendMessageDTO(
            accepted=True,
            conversation_id="conversation-1",
            session_id="session-1",
            message_id="dbgmsg_1",
            handled=True,
            handled_by="conversation",
            reason="handled",
            response_text="好的，已收到。",
        )

    async def list_messages(
        self,
        query: ListDebugIMMessagesQuery,
    ) -> DebugIMMessageListDTO:
        self.last_message_query = query
        return DebugIMMessageListDTO(
            items=[
                DebugIMMessageDTO(
                    event_id="event-1",
                    recorded_at="2026-03-25T10:00:00+08:00",
                    direction="inbound",
                    channel="debug_im",
                    user_identity=query.user_identity,
                    chat_id=query.chat_id,
                    thread_id=query.thread_id,
                    conversation_id="conversation-1",
                    session_id="session-1",
                    external_message_id="dbgmsg_0",
                    root_message_id="dbgmsg_0",
                    parent_message_id=None,
                    text="你好",
                    success=True,
                    metadata={},
                )
            ]
        )

    async def list_messages_after(
        self,
        query: PollDebugIMMessagesQuery,
    ) -> DebugIMMessageListDTO:
        self.last_poll_query = query
        items = list(self.pending_messages)
        self.pending_messages.clear()
        return DebugIMMessageListDTO(items=items)

    async def list_sessions(
        self,
        query: ListDebugIMSessionsQuery,
    ) -> DebugIMSessionListDTO:
        self.last_session_query = query
        return DebugIMSessionListDTO(
            items=[
                DebugIMSessionDTO(
                    session_key="debug-user::chat-1::",
                    user_identity=query.user_identity or "debug-user",
                    chat_id="chat-1",
                    thread_id=None,
                    conversation_id="conversation-1",
                    session_id="session-1",
                    last_message_at="2026-03-25T10:00:00+08:00",
                    last_message_direction="outbound",
                    last_message_text="好的，已收到。",
                    last_external_message_id="dbgout_1",
                )
            ]
        )


def override_debug_im_service() -> FakeDebugIMService:
    return FakeDebugIMService()


def test_send_debug_im_message_route_returns_structured_response(app: FastAPI) -> None:
    app.dependency_overrides[get_debug_im_service] = override_debug_im_service

    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/v1/debug/im/messages",
                json={
                    "user_identity": "debug-user",
                    "chat_id": "chat-1",
                    "text": "你好",
                },
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == {
        "accepted": True,
        "conversation_id": "conversation-1",
        "session_id": "session-1",
        "message_id": "dbgmsg_1",
        "handled": True,
        "handled_by": "conversation",
        "reason": "handled",
        "response_text": "好的，已收到。",
    }


def test_list_debug_im_messages_route_returns_structured_response(app: FastAPI) -> None:
    app.dependency_overrides[get_debug_im_service] = override_debug_im_service

    try:
        with TestClient(app) as client:
            response = client.get(
                "/api/v1/debug/im/messages",
                params={"user_identity": "debug-user", "chat_id": "chat-1"},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["items"][0]["text"] == "你好"


def test_list_debug_im_sessions_route_returns_structured_response(app: FastAPI) -> None:
    app.dependency_overrides[get_debug_im_service] = override_debug_im_service

    try:
        with TestClient(app) as client:
            response = client.get(
                "/api/v1/debug/im/sessions",
                params={"user_identity": "debug-user"},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["items"][0]["last_message_text"] == "好的，已收到。"


def test_send_debug_im_message_route_rejects_thread_without_chat(app: FastAPI) -> None:
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/debug/im/messages",
            json={
                "user_identity": "debug-user",
                "thread_id": "thread-1",
                "text": "你好",
            },
        )

    assert response.status_code == 422


def test_debug_im_websocket_supports_history_ping_and_send(app: FastAPI) -> None:
    app.dependency_overrides[get_debug_im_service] = override_debug_im_service

    try:
        with TestClient(app) as client:
            with client.websocket_connect("/api/v1/debug/im/ws?user_identity=debug-user") as ws:
                history = ws.receive_json()
                assert history["type"] == "history_snapshot"
                assert history["messages"][0]["text"] == "你好"

                ws.send_json({"type": "ping"})
                pong = ws.receive_json()
                assert pong["type"] == "pong"

                ws.send_json({"type": "send_message", "text": "收到"})
                ack = ws.receive_json()
                assert ack["type"] == "message_ack"
                assert ack["result"]["message_id"] == "dbgmsg_1"

                created = ws.receive_json()
                assert created["type"] == "message_created"
                assert created["message"]["text"] == "好的，已收到。"
    finally:
        app.dependency_overrides.clear()


def test_debug_im_websocket_rejects_thread_without_chat(app: FastAPI) -> None:
    app.dependency_overrides[get_debug_im_service] = override_debug_im_service

    try:
        with TestClient(app) as client:
            with client.websocket_connect(
                "/api/v1/debug/im/ws?user_identity=debug-user&thread_id=thread-1"
            ) as ws:
                error = ws.receive_json()
                assert error["type"] == "error"
                assert "thread_id" in error["detail"]
    finally:
        app.dependency_overrides.clear()
