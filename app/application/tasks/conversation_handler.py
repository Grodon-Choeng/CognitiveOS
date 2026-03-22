from typing import Protocol

from app.application.conversations.commands import HandleInboundConversationMessageCommand
from app.application.conversations.dto import ConversationInboundResult
from app.application.tasks.commands import CreateTaskCommand
from app.application.tasks.dto import TaskDTO

TASK_PREFIXES = ("待办", "todo", "task")


class TaskCreator(Protocol):
    async def create_task(self, command: CreateTaskCommand) -> TaskDTO: ...


class TaskConversationHandler:
    name = "task"

    def __init__(self, task_service: TaskCreator) -> None:
        self.task_service = task_service

    async def handle(
        self,
        command: HandleInboundConversationMessageCommand,
        *,
        conversation_id: str,
        session_id: str,
    ) -> ConversationInboundResult | None:
        task_title = _extract_task_title(command)
        if task_title is None:
            return None

        await self.task_service.create_task(
            CreateTaskCommand(
                title=task_title,
                conversation_id=conversation_id,
                session_id=session_id,
                source_channel=command.channel,
                source_user_id=command.user_identity,
                source_chat_id=command.chat_id,
                source_thread_id=command.thread_id,
            )
        )
        return ConversationInboundResult(
            handled=True,
            conversation_id=conversation_id,
            session_id=session_id,
            handled_by=self.name,
            reason="task_created",
        )


def _extract_task_title(command: HandleInboundConversationMessageCommand) -> str | None:
    if command.message_type != "text" or command.text is None:
        return None

    normalized_text = command.text.strip()
    if not normalized_text:
        return None

    lowered_text = normalized_text.casefold()
    for prefix in TASK_PREFIXES:
        if lowered_text == prefix:
            return None
        if lowered_text.startswith(prefix.casefold()):
            candidate = normalized_text[len(prefix) :].lstrip("：: \n\t")
            if candidate:
                return candidate
    return None
