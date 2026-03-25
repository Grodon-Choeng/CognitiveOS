from dataclasses import dataclass

from app.application.reminders.commands import HandleReminderInboundMessageCommand
from app.domain.reminders.entities import Reminder, ReminderStatus
from app.domain.reminders.repository import ReminderRepository


@dataclass(slots=True, frozen=True)
class ReminderInboundMatch:
    reminder: Reminder
    source: str


class ReminderInboundMatcher:
    def __init__(self, repository: ReminderRepository) -> None:
        self.repository = repository

    async def match(
        self,
        command: HandleReminderInboundMessageCommand,
    ) -> ReminderInboundMatch | None:
        reminder = await self._match_by_exact_message_relation(command)
        if reminder is not None:
            return ReminderInboundMatch(reminder=reminder, source="exact_message_relation")

        reminder = await self._match_by_conversation(command)
        if reminder is not None:
            return ReminderInboundMatch(reminder=reminder, source="same_conversation_pending")

        reminder = await self._match_by_chat_and_thread(command)
        if reminder is not None:
            return ReminderInboundMatch(reminder=reminder, source="same_thread_recent_dispatch")

        reminder = await self._match_by_chat(command)
        if reminder is not None:
            return ReminderInboundMatch(reminder=reminder, source="same_chat_recent_dispatch")

        reminder = await self.repository.get_latest_pending_by_dispatch(
            channel=command.channel,
            recipient_id=command.sender_id,
        )
        if reminder is None:
            return None
        return ReminderInboundMatch(reminder=reminder, source="latest_pending_by_dispatch")

    async def _match_by_conversation(
        self,
        command: HandleReminderInboundMessageCommand,
    ) -> Reminder | None:
        if not command.conversation_id:
            return None
        return await self.repository.get_latest_pending_by_conversation(command.conversation_id)

    async def _match_by_exact_message_relation(
        self,
        command: HandleReminderInboundMessageCommand,
    ) -> Reminder | None:
        for candidate_dispatch_message_id in (
            command.parent_message_id,
            command.root_message_id,
        ):
            if not candidate_dispatch_message_id:
                continue
            reminder = await self.repository.get_by_dispatch_message_id(
                candidate_dispatch_message_id
            )
            if reminder is not None and reminder.status == ReminderStatus.PENDING:
                return reminder
        return None

    async def _match_by_chat_and_thread(
        self,
        command: HandleReminderInboundMessageCommand,
    ) -> Reminder | None:
        if not command.chat_id or not command.thread_id:
            return None

        return await self.repository.get_latest_pending_by_dispatch_chat(
            channel=command.channel,
            recipient_id=command.sender_id,
            chat_id=command.chat_id,
            thread_id=command.thread_id,
        )

    async def _match_by_chat(
        self,
        command: HandleReminderInboundMessageCommand,
    ) -> Reminder | None:
        if not command.chat_id:
            return None

        return await self.repository.get_latest_pending_by_dispatch_chat(
            channel=command.channel,
            recipient_id=command.sender_id,
            chat_id=command.chat_id,
            thread_id=None,
        )
