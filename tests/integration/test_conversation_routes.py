from dataclasses import dataclass

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.http.deps.services import get_conversation_service
from app.application.conversations.commands import HandleInboundConversationMessageCommand
from app.application.conversations.dto import ConversationInboundResult


@dataclass
class FakeConversationService:
    async def handle_inbound_message(
        self,
        command: HandleInboundConversationMessageCommand,
        include_debug: bool = False,
    ) -> ConversationInboundResult:
        assert command.channel == "feishu"
        assert command.message_type == "text"
        assert command.user_identity == "ou_123"
        return ConversationInboundResult(
            handled=True,
            conversation_id="conversation-1",
            session_id="session-1",
            handled_by="reminder",
            reason=None,
            response_text="好的，已处理。",
            debug={"stage": "kernel"} if include_debug else None,
        )


def override_conversation_service() -> FakeConversationService:
    return FakeConversationService()


def test_receive_conversation_message_route_returns_structured_response(app: FastAPI) -> None:
    app.dependency_overrides[get_conversation_service] = override_conversation_service

    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/v1/conversations/messages",
                json={
                    "channel": "feishu",
                    "message_type": "text",
                    "user_identity": "ou_123",
                    "text": "你好",
                },
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == {
        "handled": True,
        "conversation_id": "conversation-1",
        "session_id": "session-1",
        "handled_by": "reminder",
        "response_text": "好的，已处理。",
    }


def test_receive_conversation_message_route_rejects_invalid_payload(app: FastAPI) -> None:
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/conversations/messages",
            json={
                "channel": "feishu",
                "message_type": "text",
            },
        )

    assert response.status_code == 422


def test_receive_conversation_message_route_rejects_thread_without_chat(app: FastAPI) -> None:
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/conversations/messages",
            json={
                "channel": "feishu",
                "message_type": "text",
                "user_identity": "ou_123",
                "thread_id": "ot_thread_123",
                "text": "你好",
            },
        )

    assert response.status_code == 422


def test_receive_conversation_message_route_rejects_text_message_without_text(
    app: FastAPI,
) -> None:
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/conversations/messages",
            json={
                "channel": "feishu",
                "message_type": "text",
                "user_identity": "ou_123",
            },
        )

    assert response.status_code == 422


def test_receive_conversation_message_route_supports_debug_response(app: FastAPI) -> None:
    app.dependency_overrides[get_conversation_service] = override_conversation_service

    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/v1/conversations/messages?debug=true",
                json={
                    "channel": "feishu",
                    "message_type": "text",
                    "user_identity": "ou_123",
                    "text": "你好",
                },
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["debug"]["stage"] == "kernel"
