import json
from dataclasses import asdict
from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.http.deps.services import get_conversation_service
from app.application.conversations.commands import HandleInboundConversationMessageCommand
from app.application.conversations.dto import ConversationInboundResult
from app.application.conversations.service import ConversationApplicationService
from app.infrastructure.types import JSONObject

router = APIRouter(prefix="/conversations", tags=["conversations"])


@router.post("/messages", summary="接收内部统一消息入口")
async def receive_conversation_message(
    payload: dict[str, object],
    service: Annotated[ConversationApplicationService, Depends(get_conversation_service)],
) -> ConversationInboundResult:
    command = HandleInboundConversationMessageCommand(
        channel=str(payload["channel"]),
        message_type=str(payload["message_type"]),
        user_identity=str(payload["user_identity"]),
        external_message_id=_get_optional_string(payload, "external_message_id"),
        root_message_id=_get_optional_string(payload, "root_message_id"),
        parent_message_id=_get_optional_string(payload, "parent_message_id"),
        chat_id=_get_optional_string(payload, "chat_id"),
        thread_id=_get_optional_string(payload, "thread_id"),
        text=_get_optional_string(payload, "text"),
        raw_payload=_to_json_object(payload),
    )
    result = await service.handle_inbound_message(command)
    return ConversationInboundResult(**asdict(result))


def _get_optional_string(payload: dict[str, object], key: str) -> str | None:
    value = payload.get(key)
    if isinstance(value, str):
        return value
    return None


def _to_json_object(payload: dict[str, object]) -> JSONObject:
    return json.loads(json.dumps(payload))
