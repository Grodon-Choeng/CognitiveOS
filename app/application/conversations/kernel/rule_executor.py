from collections.abc import Callable
from datetime import datetime
from zoneinfo import ZoneInfo

from app.application.conversations.commands import HandleInboundConversationMessageCommand
from app.application.conversations.kernel.results import AssistantExecutionResult
from app.application.conversations.kernel.state import AssistantTurnContext
from app.application.conversations.kernel.structured_plans import StructuredRulePlan
from app.application.memory.commands import CreateMemoryCommand
from app.application.reminders.commands import CreateReminderCommand
from app.domain.reminders.value_objects import ReminderRecurrence, next_remind_at_for_recurrence


class RuleExecutor:
    def __init__(
        self,
        *,
        reminder_service: object,
        memory_service: object,
        now_provider: Callable[[], datetime] | None = None,
    ) -> None:
        self.reminder_service = reminder_service
        self.memory_service = memory_service
        self.now_provider = now_provider or _default_now_provider

    async def preview(
        self,
        *,
        structured_plan: StructuredRulePlan,
    ) -> AssistantExecutionResult:
        preview_items = [item.summary for item in structured_plan.rule_items]
        preview_items.extend(item.summary for item in structured_plan.overrides)
        preview_items.extend(item.summary for item in structured_plan.constraints)
        return AssistantExecutionResult(
            success=True,
            action="complex_plan_preview",
            payload={
                "structured_plan": structured_plan.to_dict(),
                "preview_items": preview_items,
            },
        )

    async def execute(
        self,
        *,
        structured_plan: StructuredRulePlan,
        command: HandleInboundConversationMessageCommand,
        turn_context: AssistantTurnContext,
    ) -> AssistantExecutionResult:
        created_recurring_reminders: list[dict[str, str]] = []
        created_one_off_reminders: list[dict[str, str]] = []

        for rule_item in structured_plan.rule_items:
            recurrence = _build_recurrence(
                rule_item.schedule.weekdays,
                rule_item.schedule.hour,
                rule_item.schedule.minute,
            )
            if recurrence is None:
                continue
            remind_at = next_remind_at_for_recurrence(
                recurrence,
                timezone=rule_item.schedule.timezone,
                after=self.now_provider().astimezone(ZoneInfo(rule_item.schedule.timezone)),
            )
            reminder = await self.reminder_service.create_reminder(
                CreateReminderCommand(
                    text=rule_item.reminder_text,
                    remind_at=remind_at,
                    timezone=rule_item.schedule.timezone,
                    recurrence=recurrence,
                    conversation_id=turn_context.conversation_id,
                    session_id=turn_context.session_id,
                    source_channel=command.channel,
                    source_user_id=command.user_identity,
                    source_chat_id=command.chat_id,
                    source_thread_id=command.thread_id,
                    dispatch_channel=command.channel,
                    dispatch_recipient_id=command.user_identity,
                    dispatch_chat_id=command.chat_id,
                    dispatch_thread_id=command.thread_id,
                )
            )
            created_recurring_reminders.append(
                {
                    "object_type": "reminder",
                    "object_id": reminder.reminder_id,
                    "title": reminder.text,
                    "when": reminder.remind_at.isoformat(),
                    "timezone": reminder.timezone,
                    "schedule_kind": "recurring",
                    "schedule_label": rule_item.schedule.label or rule_item.summary,
                }
            )

        for override in structured_plan.overrides:
            target_date = override.schedule.local_date
            if target_date is None:
                continue
            matched_rule_items = [
                item
                for item in structured_plan.rule_items
                if item.rule_id in override.applies_to_rule_ids
            ]
            for rule_item in matched_rule_items:
                remind_at = _build_override_datetime(
                    local_date=target_date,
                    hour=rule_item.schedule.hour,
                    minute=rule_item.schedule.minute,
                    timezone=rule_item.schedule.timezone,
                )
                reminder = await self.reminder_service.create_reminder(
                    CreateReminderCommand(
                        text=rule_item.reminder_text,
                        remind_at=remind_at,
                        timezone=rule_item.schedule.timezone,
                        conversation_id=turn_context.conversation_id,
                        session_id=turn_context.session_id,
                        source_channel=command.channel,
                        source_user_id=command.user_identity,
                        source_chat_id=command.chat_id,
                        source_thread_id=command.thread_id,
                        dispatch_channel=command.channel,
                        dispatch_recipient_id=command.user_identity,
                        dispatch_chat_id=command.chat_id,
                        dispatch_thread_id=command.thread_id,
                    )
                )
                created_one_off_reminders.append(
                    {
                        "object_type": "reminder",
                        "object_id": reminder.reminder_id,
                        "title": reminder.text,
                        "when": reminder.remind_at.isoformat(),
                        "timezone": reminder.timezone,
                        "schedule_kind": "one_off",
                    }
                )

        memory = None
        if structured_plan.constraints:
            memory = await self.memory_service.create_memory(
                CreateMemoryCommand(
                    content="\n".join(
                        [
                            "复杂规则约束：",
                            *[
                                f"- {constraint.note_text}"
                                for constraint in structured_plan.constraints
                            ],
                        ]
                    ),
                    memory_type="preference",
                    conversation_id=turn_context.conversation_id,
                    session_id=turn_context.session_id,
                    source_channel=command.channel,
                    source_user_id=command.user_identity,
                    source_chat_id=command.chat_id,
                    source_thread_id=command.thread_id,
                )
            )

        return AssistantExecutionResult(
            success=True,
            action="complex_plan_executed",
            object_type="memory" if memory is not None else "reminder",
            object_id=memory.memory_id if memory is not None else None,
            object_title=memory.content if memory is not None else None,
            payload={
                "structured_plan": structured_plan.to_dict(),
                "created_recurring_reminders": created_recurring_reminders,
                "created_one_off_reminders": created_one_off_reminders,
                "memory": (
                    {
                        "object_type": "memory",
                        "object_id": memory.memory_id,
                        "title": memory.content,
                    }
                    if memory is not None
                    else None
                ),
            },
        )


def _build_override_datetime(
    *,
    local_date: str,
    hour: int | None,
    minute: int | None,
    timezone: str,
) -> datetime:
    target_date = datetime.fromisoformat(local_date).date()
    tzinfo = ZoneInfo(timezone)
    return datetime(
        target_date.year,
        target_date.month,
        target_date.day,
        hour or 9,
        minute or 0,
        tzinfo=tzinfo,
    )


def _build_recurrence(
    weekdays: list[str],
    hour: int | None,
    minute: int | None,
) -> ReminderRecurrence | None:
    if weekdays != ["mon", "tue", "wed", "thu", "fri"]:
        return None
    return ReminderRecurrence(
        recurrence_type="weekly_by_weekdays",
        weekdays=tuple(weekdays),
        hour=hour or 9,
        minute=minute or 0,
    )


def _default_now_provider() -> datetime:
    return datetime.now(ZoneInfo("UTC"))
