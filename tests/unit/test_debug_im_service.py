from dataclasses import dataclass

import pytest

from app.application.conversations.commands import HandleInboundConversationMessageCommand
from app.application.conversations.dto import ConversationInboundResult
from app.application.debug_im.commands import SendDebugIMMessageCommand
from app.application.debug_im.dto import (
    DebugIMMessageDTO,
    DebugIMMessageListDTO,
    DebugIMSessionListDTO,
)
from app.application.debug_im.queries import (
    ListDebugIMMessagesQuery,
    ListDebugIMSessionsQuery,
    PollDebugIMMessagesQuery,
)
from app.application.debug_im.service import DebugIMApplicationService


@dataclass
class FakeInboundProcessor:
    result: ConversationInboundResult

    def __post_init__(self) -> None:
        self.commands: list[HandleInboundConversationMessageCommand] = []

    async def handle_message(
        self,
        command: HandleInboundConversationMessageCommand,
    ) -> ConversationInboundResult:
        self.commands.append(command)
        return self.result


class FakeDebugIMMessageStore:
    def __init__(self) -> None:
        self.replied_message: DebugIMMessageDTO | None = None
        self.messages = DebugIMMessageListDTO(items=[])
        self.sessions = DebugIMSessionListDTO(items=[])
        self.poll_messages = DebugIMMessageListDTO(items=[])

    async def list_messages(
        self,
        *,
        user_identity: str,
        chat_id: str | None,
        thread_id: str | None,
        limit: int,
    ) -> DebugIMMessageListDTO:
        self.last_list_messages = (user_identity, chat_id, thread_id, limit)
        return self.messages

    async def list_messages_after(
        self,
        *,
        user_identity: str,
        chat_id: str | None,
        thread_id: str | None,
        after_recorded_at: str | None,
        after_event_id: str | None,
        limit: int,
    ) -> DebugIMMessageListDTO:
        self.last_poll = (
            user_identity,
            chat_id,
            thread_id,
            after_recorded_at,
            after_event_id,
            limit,
        )
        return self.poll_messages

    async def list_sessions(
        self,
        *,
        user_identity: str | None,
        limit: int,
    ) -> DebugIMSessionListDTO:
        self.last_list_sessions = (user_identity, limit)
        return self.sessions

    async def get_message_by_external_id(
        self,
        *,
        user_identity: str,
        external_message_id: str,
        chat_id: str | None,
        thread_id: str | None,
    ) -> DebugIMMessageDTO | None:
        self.last_lookup = (user_identity, external_message_id, chat_id, thread_id)
        return self.replied_message


@pytest.mark.asyncio
async def test_debug_im_service_builds_reply_message_context() -> None:
    processor = FakeInboundProcessor(
        ConversationInboundResult(
            handled=True,
            conversation_id="conversation-1",
            session_id="session-1",
            handled_by="reminder",
            reason="reply_handled",
            response_text="好的。",
        )
    )
    store = FakeDebugIMMessageStore()
    store.replied_message = DebugIMMessageDTO(
        event_id="event-1",
        recorded_at="2026-03-25T00:00:00+00:00",
        direction="outbound",
        channel="debug_im",
        user_identity="debug-user",
        chat_id="chat-1",
        thread_id="thread-1",
        conversation_id="conversation-1",
        session_id="session-1",
        external_message_id="dbgout_1",
        root_message_id="dbgroot_1",
        parent_message_id=None,
        text="提醒你开会",
        success=True,
        metadata={},
    )
    service = DebugIMApplicationService(
        inbound_processor=processor,
        message_store=store,
    )

    result = await service.send_message(
        SendDebugIMMessageCommand(
            user_identity="debug-user",
            text="收到",
            reply_to_message_id="dbgout_1",
        )
    )

    assert result.accepted is True
    assert processor.commands[0].channel == "debug_im"
    assert processor.commands[0].parent_message_id == "dbgout_1"
    assert processor.commands[0].root_message_id == "dbgroot_1"
    assert processor.commands[0].chat_id == "chat-1"
    assert processor.commands[0].thread_id == "thread-1"
    assert processor.commands[0].external_message_id.startswith("dbgmsg_")


@pytest.mark.asyncio
async def test_debug_im_service_delegates_message_queries() -> None:
    processor = FakeInboundProcessor(
        ConversationInboundResult(
            handled=True,
            conversation_id="conversation-1",
            session_id="session-1",
            handled_by="conversation",
            reason="handled",
            response_text="ok",
        )
    )
    store = FakeDebugIMMessageStore()
    service = DebugIMApplicationService(
        inbound_processor=processor,
        message_store=store,
    )

    await service.list_messages(
        ListDebugIMMessagesQuery(
            user_identity="debug-user",
            chat_id="chat-1",
            thread_id=None,
            limit=10,
        )
    )
    await service.list_messages_after(
        PollDebugIMMessagesQuery(
            user_identity="debug-user",
            chat_id="chat-1",
            thread_id=None,
            after_recorded_at="2026-03-25T00:00:00+00:00",
            after_event_id="event-1",
            limit=20,
        )
    )
    await service.list_sessions(ListDebugIMSessionsQuery(user_identity="debug-user", limit=5))

    assert store.last_list_messages == ("debug-user", "chat-1", None, 10)
    assert store.last_poll == (
        "debug-user",
        "chat-1",
        None,
        "2026-03-25T00:00:00+00:00",
        "event-1",
        20,
    )
    assert store.last_list_sessions == ("debug-user", 5)
