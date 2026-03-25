from dataclasses import asdict, dataclass
from datetime import datetime
from typing import cast

from app.application.conversations.commands import HandleInboundConversationMessageCommand
from app.application.conversations.kernel.plans import AssistantActionPlan
from app.application.conversations.kernel.results import (
    AssistantConfirmationResult,
    AssistantDisambiguationResult,
    AssistantExecutionResult,
)
from app.application.conversations.kernel.state import AssistantTurnContext
from app.infrastructure.types import JSONObject, JSONValue

KernelExecutionResult = (
    AssistantExecutionResult | AssistantDisambiguationResult | AssistantConfirmationResult | None
)


@dataclass(slots=True, frozen=True)
class ConversationKernelOutcome:
    turn_context: AssistantTurnContext
    plan: AssistantActionPlan
    execution_result: KernelExecutionResult
    response_text: str | None
    handled_by: str | None
    reason: str | None
    assistant_turn_state: JSONObject | None


class ConversationKernelFacade:
    """统一 assistant kernel 主流程，供 canonical path 与 legacy adapter 共用。"""

    def __init__(
        self,
        *,
        turn_context_builder: object,
        planner: object,
        executor: object,
        renderer: object,
    ) -> None:
        self.turn_context_builder = turn_context_builder
        self.planner = planner
        self.executor = executor
        self.renderer = renderer

    async def handle(
        self,
        command: HandleInboundConversationMessageCommand,
        *,
        conversation_id: str,
        session_id: str,
    ) -> ConversationKernelOutcome:
        turn_context = await self.turn_context_builder.build(
            conversation_id=conversation_id,
            session_id=session_id,
            latest_user_text=command.text,
        )
        plan = await self.planner.plan(command, turn_context=turn_context)
        execution_result = await self.executor.execute(
            plan,
            command=command,
            turn_context=turn_context,
        )
        if execution_result is None:
            return ConversationKernelOutcome(
                turn_context=turn_context,
                plan=plan,
                execution_result=None,
                response_text=None,
                handled_by=None,
                reason=None,
                assistant_turn_state=None,
            )

        response_text = self.renderer.render(execution_result, turn_context=turn_context)
        return ConversationKernelOutcome(
            turn_context=turn_context,
            plan=plan,
            execution_result=execution_result,
            response_text=response_text,
            handled_by=_handled_by_for_action(plan.action),
            reason=_reason_for_result(plan.intent, plan.action, plan.reasoning, execution_result),
            assistant_turn_state=_build_assistant_turn_state(
                plan=plan,
                plan_action=plan.action,
                execution_result=execution_result,
            ),
        )

    @staticmethod
    def build_debug_payload(outcome: ConversationKernelOutcome) -> JSONObject:
        return {
            "stage": "kernel",
            "turn_context": _serialize_turn_context(outcome.turn_context),
            "plan": _serialize_plan(outcome.plan),
            "execution_result": _serialize_execution_result(outcome.execution_result),
            "response_text": outcome.response_text,
        }


def _handled_by_for_action(action: str | None) -> str | None:
    if action in {
        "create_task",
        "list_tasks",
        "complete_task",
        "cancel_task",
        "convert_reminder_to_task",
    }:
        return "task"
    if action in {
        "create_reminder",
        "list_reminders",
        "cancel_reminder",
        "reschedule_reminder",
        "retry_failed_reminder",
        "convert_task_to_reminder",
    }:
        return "reminder"
    if action in {"create_memory", "list_memories", "archive_memory"}:
        return "memory"
    if action in {"show_overview", "show_activity"}:
        return "overview"
    if action in {"reply_greeting", "show_help"}:
        return "conversation"
    return None


def _reason_for_result(
    intent: str,
    action: str | None,
    reasoning: str | None,
    result: AssistantExecutionResult | AssistantDisambiguationResult | AssistantConfirmationResult,
) -> str:
    source = reasoning if reasoning in {"rules", "llm"} else "kernel"
    if isinstance(result, AssistantDisambiguationResult):
        return f"{action or 'conversation'}_needs_disambiguation"
    if isinstance(result, AssistantConfirmationResult):
        return f"{action or 'conversation'}_needs_confirmation"
    if not result.success:
        return f"{intent}_feedback"
    action_reason_map = {
        "reply_greeting": f"greeting_replied_via_{source}",
        "show_help": f"help_shown_via_{source}",
        "create_task": f"task_created_via_{source}",
        "list_tasks": f"task_listed_via_{source}",
        "complete_task": f"task_completed_via_{source}",
        "cancel_task": f"task_canceled_via_{source}",
        "create_reminder": f"reminder_created_via_{source}",
        "cancel_reminder": f"reminder_canceled_via_{source}",
        "reschedule_reminder": f"reminder_rescheduled_via_{source}",
        "retry_failed_reminder": f"reminder_retried_via_{source}",
        "list_reminders": f"reminder_listed_via_{source}",
        "convert_task_to_reminder": f"task_converted_to_reminder_via_{source}",
        "convert_reminder_to_task": f"reminder_converted_to_task_via_{source}",
        "create_memory": f"memory_created_via_{source}",
        "archive_memory": f"memory_archived_via_{source}",
        "list_memories": f"memory_listed_via_{source}",
        "show_overview": f"overview_shown_via_{source}",
        "show_activity": f"activity_shown_via_{source}",
    }
    return action_reason_map.get(result.action, f"{intent}_handled")


def _build_assistant_turn_state(
    *,
    plan: AssistantActionPlan,
    plan_action: str | None,
    execution_result: AssistantExecutionResult
    | AssistantDisambiguationResult
    | AssistantConfirmationResult,
) -> JSONObject:
    if isinstance(execution_result, AssistantDisambiguationResult):
        return {
            "dialogue_mode": "disambiguation",
            "visible_candidates": [
                {
                    "object_type": candidate.get("object_type"),
                    "object_id": candidate.get("object_id"),
                    "title": candidate.get("title"),
                    "score": 0.8,
                }
                for candidate in execution_result.candidates
                if isinstance(candidate, dict)
            ],
            "last_assistant_action": {
                "action_type": plan_action or "disambiguation",
                "success": True,
                "object_type": None,
                "object_id": None,
                "summary": execution_result.prompt,
            },
        }
    if isinstance(execution_result, AssistantConfirmationResult):
        state: JSONObject = {
            "dialogue_mode": "confirmation",
            "pending_confirmation": {
                "confirm_action": execution_result.confirm_action,
                "preview_text": execution_result.preview_text,
            },
            "last_assistant_action": {
                "action_type": execution_result.confirm_action,
                "success": True,
                "object_type": None,
                "object_id": None,
                "summary": execution_result.preview_text or execution_result.prompt,
            },
        }
        if plan.object_type is not None and plan.object_id is not None:
            state["focused_object"] = {
                "object_type": plan.object_type,
                "object_id": plan.object_id,
                "title": execution_result.preview_text,
            }
        return state

    state_payload: JSONObject = {
        "dialogue_mode": "normal",
        "last_assistant_action": {
            "action_type": execution_result.action,
            "success": execution_result.success,
            "object_type": execution_result.object_type,
            "object_id": execution_result.object_id,
            "summary": execution_result.object_title or execution_result.message_hint,
        },
    }
    if execution_result.object_type is not None and execution_result.object_id is not None:
        state_payload["focused_object"] = {
            "object_type": execution_result.object_type,
            "object_id": execution_result.object_id,
            "title": execution_result.object_title,
        }
    visible_candidates = _extract_visible_candidates(execution_result)
    if visible_candidates:
        state_payload["visible_candidates"] = cast(JSONValue, visible_candidates)
    return state_payload


def _extract_visible_candidates(execution_result: AssistantExecutionResult) -> list[JSONObject]:
    payload_items = execution_result.payload.get("items")
    if not isinstance(payload_items, list):
        return []
    candidates: list[JSONObject] = []
    for item in payload_items:
        if not isinstance(item, dict):
            continue
        object_type = item.get("object_type")
        object_id = item.get("object_id")
        title = item.get("title")
        if isinstance(object_type, str) and isinstance(object_id, str) and isinstance(title, str):
            candidates.append(
                {
                    "object_type": object_type,
                    "object_id": object_id,
                    "title": title,
                    "score": 0.9,
                }
            )
    return candidates


def _serialize_turn_context(turn_context: AssistantTurnContext) -> JSONObject:
    payload = asdict(turn_context)
    return cast(JSONObject, _json_safe(payload))


def _serialize_plan(plan: AssistantActionPlan) -> JSONObject:
    payload = asdict(plan)
    return cast(JSONObject, _json_safe(payload))


def _serialize_execution_result(result: KernelExecutionResult) -> JSONObject:
    if result is None:
        return {"result_type": "none"}
    if isinstance(result, AssistantExecutionResult):
        payload = asdict(result)
        payload["result_type"] = "execution"
        return cast(JSONObject, _json_safe(payload))
    if isinstance(result, AssistantDisambiguationResult):
        payload = asdict(result)
        payload["result_type"] = "disambiguation"
        return cast(JSONObject, _json_safe(payload))
    payload = asdict(result)
    payload["result_type"] = "confirmation"
    return cast(JSONObject, _json_safe(payload))


def _json_safe(value: object) -> JSONValue:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(key): _json_safe(item_value) for key, item_value in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, tuple):
        return [_json_safe(item) for item in value]
    return cast(JSONValue, value)
