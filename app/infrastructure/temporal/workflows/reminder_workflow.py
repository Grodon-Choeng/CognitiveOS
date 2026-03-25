from dataclasses import dataclass
from datetime import timedelta

from temporalio import workflow

REMINDER_WORKFLOW_NAME = "reminder-workflow"
RECORD_USER_REPLY_SIGNAL = "record-user-reply"


@dataclass(slots=True, frozen=True)
class ReminderWorkflowInput:
    reminder_id: str
    text: str
    remind_at: str
    timezone: str
    dispatch_channel: str
    dispatch_recipient_id: str
    conversation_id: str | None = None
    session_id: str | None = None
    trace_id: str | None = None
    chain_id: str | None = None
    request_id: str | None = None
    dispatch_chat_id: str | None = None
    dispatch_thread_id: str | None = None


@dataclass(slots=True)
class ReminderWorkflowState:
    reminder_id: str = ""
    status: str = "pending"
    last_reply_text: str | None = None
    reply_received: bool = False
    dispatch_message_id: str | None = None


@workflow.defn(name=REMINDER_WORKFLOW_NAME)
class ReminderWorkflow:
    def __init__(self) -> None:
        self.state = ReminderWorkflowState()

    @workflow.run
    async def run(self, workflow_input: ReminderWorkflowInput) -> str:
        self.state.reminder_id = workflow_input.reminder_id
        self.state.status = "sending_message"
        workflow.logger.info(
            "提醒工作流已启动，准备发送提醒消息。",
            extra={
                "reminder_id": workflow_input.reminder_id,
                "trace_id": workflow_input.trace_id,
                "chain_id": workflow_input.chain_id,
                "request_id": workflow_input.request_id,
            },
        )
        dispatch_message_id = await workflow.execute_activity(
            "send-reminder-message",
            args=[
                workflow_input.reminder_id,
                workflow_input.text,
                workflow_input.conversation_id,
                workflow_input.session_id,
                workflow_input.trace_id,
                workflow_input.chain_id,
                workflow_input.request_id,
                workflow_input.dispatch_channel,
                workflow_input.dispatch_recipient_id,
                workflow_input.dispatch_chat_id,
                workflow_input.dispatch_thread_id,
            ],
            start_to_close_timeout=timedelta(seconds=30),
        )
        await workflow.execute_activity(
            "record-dispatch-message-id",
            args=[
                workflow_input.reminder_id,
                dispatch_message_id,
                workflow_input.trace_id,
                workflow_input.chain_id,
                workflow_input.request_id,
            ],
            start_to_close_timeout=timedelta(seconds=10),
        )
        self.state.dispatch_message_id = dispatch_message_id
        self.state.status = "waiting_for_reply"
        workflow.logger.info(
            "提醒消息已发送，等待后续回复信号。",
            extra={
                "reminder_id": workflow_input.reminder_id,
                "trace_id": workflow_input.trace_id,
                "chain_id": workflow_input.chain_id,
                "request_id": workflow_input.request_id,
            },
        )
        await workflow.wait_condition(lambda: self.state.reply_received)
        self.state.status = "completed"
        workflow.logger.info(
            "提醒工作流已收到用户回复，流程结束。",
            extra={
                "reminder_id": workflow_input.reminder_id,
                "trace_id": workflow_input.trace_id,
                "chain_id": workflow_input.chain_id,
                "request_id": workflow_input.request_id,
            },
        )
        return f"提醒已完成:{workflow_input.reminder_id}"

    @workflow.signal(name=RECORD_USER_REPLY_SIGNAL)
    async def record_user_reply(self, reply_text: str) -> None:
        self.state.last_reply_text = reply_text
        self.state.reply_received = True

    @workflow.query(name="get-state")
    def get_state(self) -> ReminderWorkflowState:
        return self.state
