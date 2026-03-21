from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from temporalio import activity

from app.infrastructure.db.models.reminder import ReminderModel
from app.infrastructure.integrations.messaging.base import (
    MessageTarget,
    MessagingAdapter,
    OutboundMessage,
)


class ReminderActivities:
    def __init__(
        self,
        messaging_adapter: MessagingAdapter,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        self.messaging_adapter = messaging_adapter
        self.session_factory = session_factory

    @activity.defn(name="send-reminder-message")
    async def send_reminder_message(
        self,
        reminder_id: str,
        text: str,
        dispatch_channel: str,
        dispatch_recipient_id: str,
        dispatch_chat_id: str | None = None,
        dispatch_thread_id: str | None = None,
    ) -> str:
        activity.logger.info(
            "开始发送提醒消息。",
            extra={
                "reminder_id": reminder_id,
                "dispatch_channel": dispatch_channel,
                "dispatch_recipient_id": dispatch_recipient_id,
            },
        )
        result = await self.messaging_adapter.send_message(
            target=MessageTarget(
                channel=dispatch_channel,
                recipient_id=dispatch_recipient_id,
            ),
            content=OutboundMessage(
                text=text,
                metadata={
                    "reminder_id": reminder_id,
                    "chat_id": dispatch_chat_id,
                    "thread_id": dispatch_thread_id,
                },
            ),
        )
        activity.logger.info(
            "提醒消息发送完成。",
            extra={
                "reminder_id": reminder_id,
                "external_message_id": result.external_message_id,
            },
        )
        return result.external_message_id or ""

    @activity.defn(name="record-dispatch-message-id")
    async def record_dispatch_message_id(
        self,
        reminder_id: str,
        dispatch_message_id: str,
    ) -> None:
        async with self.session_factory() as session:
            reminder = await session.get(ReminderModel, reminder_id)
            if reminder is None:
                activity.logger.warning(
                    "未找到需要记录外发消息 ID 的提醒。",
                    extra={"reminder_id": reminder_id},
                )
                return

            reminder.dispatch_message_id = dispatch_message_id
            await session.commit()
