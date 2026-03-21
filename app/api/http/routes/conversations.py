from dataclasses import asdict
from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.http.deps.services import get_conversation_service
from app.api.http.schemas.conversation import (
    ConversationMessageRequest,
    ConversationMessageResponse,
)
from app.application.conversations.commands import HandleInboundConversationMessageCommand
from app.application.conversations.service import ConversationApplicationService

router = APIRouter(prefix="/conversations", tags=["conversations"])


@router.post("/messages", summary="接收内部统一消息入口")
async def receive_conversation_message(
    payload: ConversationMessageRequest,
    service: Annotated[ConversationApplicationService, Depends(get_conversation_service)],
) -> ConversationMessageResponse:
    command = HandleInboundConversationMessageCommand(
        channel=payload.channel,
        message_type=payload.message_type,
        user_identity=payload.user_identity,
        external_message_id=payload.external_message_id,
        root_message_id=payload.root_message_id,
        parent_message_id=payload.parent_message_id,
        chat_id=payload.chat_id,
        thread_id=payload.thread_id,
        text=payload.text,
        raw_payload=payload.raw_payload or payload.model_dump(mode="json"),
    )
    result = await service.handle_inbound_message(command)
    return ConversationMessageResponse(**asdict(result))
