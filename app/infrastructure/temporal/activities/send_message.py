from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from temporalio import activity

from app.infrastructure.db.models.reminder import ReminderModel
from app.infrastructure.integrations.messaging.base import (
    MessageTarget,
    MessagingAdapter,
    OutboundMessage,
)
from app.observability.context import bind_observability_context, reset_observability_context
from app.observability.workflow_events import WorkflowEventRecord, WorkflowEventRecorder


class ReminderActivities:
    def __init__(
        self,
        messaging_adapter: MessagingAdapter,
        session_factory: async_sessionmaker[AsyncSession],
        workflow_event_recorder: WorkflowEventRecorder,
    ) -> None:
        self.messaging_adapter = messaging_adapter
        self.session_factory = session_factory
        self.workflow_event_recorder = workflow_event_recorder

    @activity.defn(name="send-reminder-message")
    async def send_reminder_message(
        self,
        reminder_id: str,
        text: str,
        conversation_id: str | None,
        session_id: str | None,
        trace_id: str | None,
        chain_id: str | None,
        request_id: str | None,
        dispatch_channel: str,
        dispatch_recipient_id: str,
        dispatch_chat_id: str | None = None,
        dispatch_thread_id: str | None = None,
    ) -> str:
        token = bind_observability_context(
            trace_id=trace_id,
            chain_id=chain_id,
            request_id=request_id,
            process_role="worker",
        )
        activity_info = activity.info()
        workflow_id = activity_info.workflow_id or ""
        workflow_type = activity_info.workflow_type or ""
        try:
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
                        "conversation_id": conversation_id,
                        "session_id": session_id,
                        "chat_id": dispatch_chat_id,
                        "thread_id": dispatch_thread_id,
                        "trace_id": trace_id,
                        "chain_id": chain_id,
                        "request_id": request_id,
                        "workflow_id": workflow_id,
                        "workflow_type": workflow_type,
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
            await self.workflow_event_recorder.record(
                WorkflowEventRecord.create(
                    workflow_id=workflow_id,
                    workflow_type=workflow_type,
                    event_type="message_dispatched",
                    conversation_id=conversation_id,
                    session_id=session_id,
                    trace_id=trace_id,
                    chain_id=chain_id,
                    request_id=request_id,
                    message="提醒消息发送完成。",
                    payload={
                        "reminder_id": reminder_id,
                        "dispatch_channel": dispatch_channel,
                        "dispatch_recipient_id": dispatch_recipient_id,
                        "external_message_id": result.external_message_id,
                    },
                )
            )
            return result.external_message_id or ""
        finally:
            reset_observability_context(token)

    @activity.defn(name="record-dispatch-message-id")
    async def record_dispatch_message_id(
        self,
        reminder_id: str,
        dispatch_message_id: str,
        trace_id: str | None,
        chain_id: str | None,
        request_id: str | None,
    ) -> None:
        token = bind_observability_context(
            trace_id=trace_id,
            chain_id=chain_id,
            request_id=request_id,
            process_role="worker",
        )
        activity_info = activity.info()
        workflow_id = activity_info.workflow_id or ""
        workflow_type = activity_info.workflow_type or ""
        try:
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
            await self.workflow_event_recorder.record(
                WorkflowEventRecord.create(
                    workflow_id=workflow_id,
                    workflow_type=workflow_type,
                    event_type="dispatch_message_id_recorded",
                    conversation_id=reminder.conversation_id if reminder is not None else None,
                    session_id=reminder.session_id if reminder is not None else None,
                    trace_id=trace_id,
                    chain_id=chain_id,
                    request_id=request_id,
                    message="已记录外发消息 ID。",
                    payload={
                        "reminder_id": reminder_id,
                        "dispatch_message_id": dispatch_message_id,
                    },
                )
            )
        finally:
            reset_observability_context(token)
