from uuid import uuid4

from app.application.conversations.commands import HandleInboundConversationMessageCommand
from app.application.conversations.inbound_processor import ConversationInboundProcessor
from app.application.debug_im.commands import SendDebugIMMessageCommand
from app.application.debug_im.dto import (
    DebugIMMessageListDTO,
    DebugIMSendMessageDTO,
    DebugIMSessionListDTO,
)
from app.application.debug_im.ports import DebugIMMessageStore
from app.application.debug_im.queries import (
    ListDebugIMMessagesQuery,
    ListDebugIMSessionsQuery,
    PollDebugIMMessagesQuery,
)
from app.infrastructure.types import JSONObject


class DebugIMApplicationService:
    def __init__(
        self,
        inbound_processor: ConversationInboundProcessor,
        message_store: DebugIMMessageStore,
    ) -> None:
        self.inbound_processor = inbound_processor
        self.message_store = message_store

    async def send_message(
        self,
        command: SendDebugIMMessageCommand,
    ) -> DebugIMSendMessageDTO:
        replied_message = None
        if command.reply_to_message_id is not None:
            replied_message = await self.message_store.get_message_by_external_id(
                user_identity=command.user_identity,
                external_message_id=command.reply_to_message_id,
                chat_id=command.chat_id,
                thread_id=command.thread_id,
            )

        message_id = _new_debug_im_message_id()
        chat_id = (
            command.chat_id
            if command.chat_id is not None
            else _optional_attr(
                replied_message,
                "chat_id",
            )
        )
        thread_id = (
            command.thread_id
            if command.thread_id is not None
            else _optional_attr(replied_message, "thread_id")
        )
        root_message_id = _resolve_root_message_id(
            message_id=message_id,
            reply_to_message_id=command.reply_to_message_id,
            replied_message_root_id=_optional_attr(replied_message, "root_message_id"),
        )

        result = await self.inbound_processor.handle_message(
            HandleInboundConversationMessageCommand(
                channel="debug_im",
                message_type="text",
                user_identity=command.user_identity,
                external_message_id=message_id,
                root_message_id=root_message_id,
                parent_message_id=command.reply_to_message_id,
                chat_id=chat_id,
                thread_id=thread_id,
                text=command.text,
                raw_payload=command.raw_payload
                or _build_default_raw_payload(
                    user_identity=command.user_identity,
                    message_id=message_id,
                    text=command.text,
                    chat_id=chat_id,
                    thread_id=thread_id,
                    reply_to_message_id=command.reply_to_message_id,
                    root_message_id=root_message_id,
                ),
            )
        )
        return DebugIMSendMessageDTO(
            accepted=True,
            conversation_id=result.conversation_id,
            session_id=result.session_id,
            message_id=message_id,
            handled=result.handled,
            handled_by=result.handled_by,
            reason=result.reason,
            response_text=result.response_text,
        )

    async def list_messages(
        self,
        query: ListDebugIMMessagesQuery,
    ) -> DebugIMMessageListDTO:
        return await self.message_store.list_messages(
            user_identity=query.user_identity,
            chat_id=query.chat_id,
            thread_id=query.thread_id,
            limit=query.limit,
        )

    async def list_messages_after(
        self,
        query: PollDebugIMMessagesQuery,
    ) -> DebugIMMessageListDTO:
        return await self.message_store.list_messages_after(
            user_identity=query.user_identity,
            chat_id=query.chat_id,
            thread_id=query.thread_id,
            after_recorded_at=query.after_recorded_at,
            after_event_id=query.after_event_id,
            limit=query.limit,
        )

    async def list_sessions(
        self,
        query: ListDebugIMSessionsQuery,
    ) -> DebugIMSessionListDTO:
        return await self.message_store.list_sessions(
            user_identity=query.user_identity,
            limit=query.limit,
        )


def _new_debug_im_message_id() -> str:
    return f"dbgmsg_{uuid4()}"


def _resolve_root_message_id(
    *,
    message_id: str,
    reply_to_message_id: str | None,
    replied_message_root_id: str | None,
) -> str:
    if replied_message_root_id:
        return replied_message_root_id
    if reply_to_message_id:
        return reply_to_message_id
    return message_id


def _build_default_raw_payload(
    *,
    user_identity: str,
    message_id: str,
    text: str,
    chat_id: str | None,
    thread_id: str | None,
    reply_to_message_id: str | None,
    root_message_id: str,
) -> JSONObject:
    payload: JSONObject = {
        "channel": "debug_im",
        "message_id": message_id,
        "message_type": "text",
        "user_identity": user_identity,
        "text": text,
        "root_message_id": root_message_id,
    }
    if chat_id is not None:
        payload["chat_id"] = chat_id
    if thread_id is not None:
        payload["thread_id"] = thread_id
    if reply_to_message_id is not None:
        payload["reply_to_message_id"] = reply_to_message_id
    return payload


def _optional_attr(payload: object, key: str) -> str | None:
    if payload is None:
        return None
    value = getattr(payload, key, None)
    if isinstance(value, str):
        return value
    return None
