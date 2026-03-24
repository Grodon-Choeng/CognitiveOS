import json
import logging
from dataclasses import dataclass
from datetime import datetime
from time import perf_counter
from typing import Protocol, cast

from app.application.audit.dto import AuditEventPageDTO
from app.application.conversations.commands import HandleInboundConversationMessageCommand
from app.application.conversations.dto import ConversationInboundResult
from app.application.conversations.kernel.plans import AssistantActionPlan
from app.application.conversations.kernel.results import (
    AssistantConfirmationResult,
    AssistantDisambiguationResult,
    AssistantExecutionResult,
)
from app.application.conversations.kernel.state import AssistantTurnContext
from app.application.conversations.ports import ConversationContextResolver
from app.infrastructure.llm.gateway import LLMGateway
from app.infrastructure.llm.models import GenerateRequest
from app.infrastructure.types import JSONObject, JSONValue
from app.observability.message_events import MessageEventRecord, MessageEventRecorder

logger = logging.getLogger(__name__)

ConversationExecutionResult = (
    AssistantExecutionResult | AssistantDisambiguationResult | AssistantConfirmationResult | None
)


class ConversationMessageHistoryReader(Protocol):
    async def list_events(
        self,
        *,
        kind: str,
        conversation_id: str | None = None,
        session_id: str | None = None,
        success: bool | None = None,
        channel: str | None = None,
        provider: str | None = None,
        tool_name: str | None = None,
        workflow_type: str | None = None,
        recorded_after: datetime | None = None,
        recorded_before: datetime | None = None,
        cursor: str | None = None,
        limit: int = 50,
    ) -> AuditEventPageDTO: ...


class ReminderFastPathHandler(Protocol):
    async def handle(
        self,
        command: HandleInboundConversationMessageCommand,
        *,
        conversation_id: str,
        session_id: str,
    ) -> ConversationInboundResult | None: ...


class TurnContextBuilder(Protocol):
    async def build(
        self,
        *,
        conversation_id: str,
        session_id: str,
        latest_user_text: str | None,
    ) -> AssistantTurnContext: ...


class ConversationPlanner(Protocol):
    async def plan(
        self,
        command: HandleInboundConversationMessageCommand,
        *,
        turn_context: AssistantTurnContext,
    ) -> AssistantActionPlan: ...


class ConversationExecutor(Protocol):
    async def execute(
        self,
        plan: AssistantActionPlan,
        *,
        command: HandleInboundConversationMessageCommand,
        turn_context: AssistantTurnContext,
    ) -> ConversationExecutionResult: ...


class ConversationRenderer(Protocol):
    def render(
        self,
        result: AssistantExecutionResult
        | AssistantDisambiguationResult
        | AssistantConfirmationResult,
        *,
        turn_context: AssistantTurnContext,
    ) -> str: ...


@dataclass(slots=True, frozen=True)
class _ConversationTurnOutcome:
    result: ConversationInboundResult
    assistant_turn_state: JSONObject | None = None


class LLMConversationFallbackResponder:
    def __init__(
        self,
        *,
        llm_gateway: LLMGateway | None,
        model: str | None,
        api_key_suffix: str | None,
        history_reader: ConversationMessageHistoryReader,
        provider: str = "openai",
    ) -> None:
        self.llm_gateway = llm_gateway
        self.model = model
        self.api_key_suffix = api_key_suffix
        self.history_reader = history_reader
        self.provider = provider

    async def generate_reply(
        self,
        *,
        command: HandleInboundConversationMessageCommand,
        conversation_id: str,
        session_id: str,
    ) -> str | None:
        if self.llm_gateway is None or self.model is None:
            return None
        if command.message_type != "text" or command.text is None:
            return None

        history_text = await self._build_history_text(
            conversation_id=conversation_id,
            session_id=session_id,
        )
        try:
            result = await self.llm_gateway.generate(
                GenerateRequest(
                    prompt=_build_fallback_prompt(
                        latest_user_text=command.text,
                        history_text=history_text,
                    ),
                    system_prompt=_build_fallback_system_prompt(),
                    provider=self.provider,
                    model=self.model,
                    api_key_suffix=self.api_key_suffix,
                    conversation_id=conversation_id,
                    session_id=session_id,
                    metadata={"component": "conversation_fallback_responder"},
                )
            )
        except Exception as exc:
            logger.warning(
                "对话兜底回复调用 LLM 失败，回退到无回复状态。",
                extra={
                    "conversation_id": conversation_id,
                    "session_id": session_id,
                    "error_type": type(exc).__name__,
                    "error_message": str(exc),
                },
            )
            return None
        return _parse_fallback_reply(result.content)

    async def _build_history_text(
        self,
        *,
        conversation_id: str,
        session_id: str,
    ) -> str:
        try:
            page = await self.history_reader.list_events(
                kind="message",
                conversation_id=conversation_id,
                session_id=session_id,
                limit=12,
            )
        except Exception as exc:
            logger.warning(
                "读取对话历史失败，使用空历史继续处理。",
                extra={
                    "conversation_id": conversation_id,
                    "session_id": session_id,
                    "error_type": type(exc).__name__,
                    "error_message": str(exc),
                },
            )
            return "暂无最近对话。"

        lines: list[str] = []
        for event in reversed(page.items):
            payload = event.payload
            direction = payload.get("direction")
            text = payload.get("text")
            if not isinstance(direction, str) or not isinstance(text, str) or not text.strip():
                continue
            speaker = "assistant" if direction == "outbound" else "user"
            lines.append(f"{speaker}: {text.strip()}")
        return "\n".join(lines) if lines else "暂无最近对话。"


class ConversationApplicationService:
    def __init__(
        self,
        *,
        conversation_context_resolver: ConversationContextResolver,
        message_event_recorder: MessageEventRecorder,
        reminder_handler: ReminderFastPathHandler,
        turn_context_builder: TurnContextBuilder,
        planner: ConversationPlanner,
        executor: ConversationExecutor,
        renderer: ConversationRenderer,
        fallback_responder: LLMConversationFallbackResponder | None = None,
    ) -> None:
        self.conversation_context_resolver = conversation_context_resolver
        self.message_event_recorder = message_event_recorder
        self.reminder_handler = reminder_handler
        self.turn_context_builder = turn_context_builder
        self.planner = planner
        self.executor = executor
        self.renderer = renderer
        self.fallback_responder = fallback_responder

    async def handle_inbound_message(
        self,
        command: HandleInboundConversationMessageCommand,
    ) -> ConversationInboundResult:
        conversation_context = await self.conversation_context_resolver.resolve_for_inbound(
            source_channel=command.channel,
            source_user_id=command.user_identity,
            source_chat_id=command.chat_id,
            source_thread_id=command.thread_id,
        )
        started_at = perf_counter()

        try:
            outcome = await self._handle_with_kernel(
                command=command,
                conversation_id=conversation_context.conversation_id,
                session_id=conversation_context.session_id,
            )
        except Exception as exc:
            await self.message_event_recorder.record(
                _build_inbound_record(
                    command=command,
                    conversation_id=conversation_context.conversation_id,
                    session_id=conversation_context.session_id,
                    handled=False,
                    handled_by=None,
                    reason="handler_exception",
                    response_text=None,
                    success=False,
                    error_code=type(exc).__name__,
                    error_message=str(exc),
                    latency_ms=(perf_counter() - started_at) * 1000,
                    assistant_turn_state=None,
                )
            )
            raise

        await self.message_event_recorder.record(
            _build_inbound_record(
                command=command,
                conversation_id=conversation_context.conversation_id,
                session_id=conversation_context.session_id,
                handled=outcome.result.handled,
                handled_by=outcome.result.handled_by,
                reason=outcome.result.reason,
                response_text=outcome.result.response_text,
                success=True,
                error_code=None,
                error_message=None,
                latency_ms=(perf_counter() - started_at) * 1000,
                assistant_turn_state=outcome.assistant_turn_state,
            )
        )
        return outcome.result

    async def _handle_with_kernel(
        self,
        *,
        command: HandleInboundConversationMessageCommand,
        conversation_id: str,
        session_id: str,
    ) -> _ConversationTurnOutcome:
        reminder_result = await self.reminder_handler.handle(
            command,
            conversation_id=conversation_id,
            session_id=session_id,
        )
        if reminder_result is not None and reminder_result.handled:
            return _ConversationTurnOutcome(
                result=reminder_result,
                assistant_turn_state={
                    "dialogue_mode": "normal",
                    "last_assistant_action": {
                        "action_type": "reply_reminder",
                        "success": True,
                        "object_type": "reminder",
                        "object_id": None,
                        "summary": reminder_result.response_text or "提醒续执行已完成",
                    },
                },
            )

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
        if execution_result is not None:
            response_text = self.renderer.render(execution_result, turn_context=turn_context)
            result = ConversationInboundResult(
                handled=True,
                conversation_id=conversation_id,
                session_id=session_id,
                handled_by=_handled_by_for_action(plan.action),
                reason=_reason_for_result(
                    plan.intent,
                    plan.action,
                    plan.reasoning,
                    execution_result,
                ),
                response_text=response_text,
            )
            return _ConversationTurnOutcome(
                result=result,
                assistant_turn_state=_build_assistant_turn_state(
                    plan_action=plan.action,
                    execution_result=execution_result,
                ),
            )

        if self.fallback_responder is not None:
            fallback_reply = await self.fallback_responder.generate_reply(
                command=command,
                conversation_id=conversation_id,
                session_id=session_id,
            )
            if fallback_reply is not None:
                return _ConversationTurnOutcome(
                    result=ConversationInboundResult(
                        handled=True,
                        conversation_id=conversation_id,
                        session_id=session_id,
                        handled_by="conversation",
                        reason="llm_fallback_replied",
                        response_text=fallback_reply,
                    ),
                    assistant_turn_state={
                        "dialogue_mode": "normal",
                        "last_assistant_action": {
                            "action_type": "llm_fallback_reply",
                            "success": True,
                            "object_type": None,
                            "object_id": None,
                            "summary": fallback_reply,
                        },
                    },
                )

        return _ConversationTurnOutcome(
            result=ConversationInboundResult(
                handled=False,
                conversation_id=conversation_id,
                session_id=session_id,
                handled_by=None,
                reason="no_handler_accepted",
                response_text=(
                    "我还没听懂这句话，但我可以帮你记提醒、建待办、记住信息，"
                    "也能帮你查看概览、提醒、待办和记忆。"
                    "你也可以直接问我“你可以帮我做什么”。"
                ),
            ),
            assistant_turn_state={
                "dialogue_mode": "normal",
                "last_assistant_action": {
                    "action_type": "default_guidance_reply",
                    "success": True,
                    "object_type": None,
                    "object_id": None,
                    "summary": "未命中能力，返回引导说明。",
                },
            },
        )


def _build_inbound_record(
    *,
    command: HandleInboundConversationMessageCommand,
    conversation_id: str,
    session_id: str,
    handled: bool,
    handled_by: str | None,
    reason: str | None,
    response_text: str | None,
    success: bool,
    error_code: str | None,
    error_message: str | None,
    latency_ms: float,
    assistant_turn_state: JSONObject | None,
) -> MessageEventRecord:
    metadata: JSONObject = {
        "handled": handled,
        "handled_by": handled_by,
        "reason": reason,
        "response_text": response_text,
    }
    if assistant_turn_state is not None:
        metadata["assistant_turn_state"] = assistant_turn_state
    return MessageEventRecord.create(
        direction="inbound",
        channel=command.channel,
        message_type=command.message_type,
        user_identity=command.user_identity,
        external_message_id=command.external_message_id,
        root_message_id=command.root_message_id,
        parent_message_id=command.parent_message_id,
        chat_id=command.chat_id,
        thread_id=command.thread_id,
        conversation_id=conversation_id,
        session_id=session_id,
        trace_id=None,
        chain_id=None,
        request_id=None,
        latency_ms=latency_ms,
        text=command.text,
        success=success,
        error_code=error_code,
        error_message=error_message,
        raw_payload=command.raw_payload,
        metadata=metadata,
    )


def _build_fallback_system_prompt() -> str:
    return (
        "你是 CognitiveOS 的对话兜底回复助手。"
        "你必须优先根据最近对话理解用户当前这句话。"
        "用户的短句、追问、反问、确认、质疑通常都依赖上文，"
        "例如“是吗”“然后呢”“什么意思”“没有上下文？”这类话必须结合前面的 assistant 回复来回答。"
        "除非最近对话真的完全不足，否则不要说自己没有上下文，也不要重复帮助菜单。"
        "你不能编造已经完成的动作，也不要假装自己拥有提醒、待办、记忆之外的能力。"
        "如果用户在闲聊、追问、确认、问候，就自然简短回复。"
        "如果用户在问你能做什么，就清楚说明你现在能做提醒、待办、记忆、概览和查询。"
        "如果用户是在质疑你刚才的话，就先接住他的质疑，再顺着上文继续回答。"
        "回复要像正常聊天，不要机械，不要像 FAQ。"
        "如果上下文真的不足，就坦诚说明，并顺手给一个最自然的下一步建议。"
        '你必须返回 JSON，格式为 {"reply_text":"给用户的话"}。'
    )


def _build_fallback_prompt(*, latest_user_text: str, history_text: str) -> str:
    return (
        "下面是按时间顺序排列的最近对话，请先理解上下文再回复。\n\n"
        f"最近对话：\n{history_text}\n\n"
        f"当前用户消息：{latest_user_text}\n\n"
        "请基于上面的对话上下文，生成一句自然、简短、不机械的中文回复。"
    )


def _parse_fallback_reply(content: str) -> str | None:
    normalized = content.strip()
    if normalized.startswith("```"):
        lines = normalized.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        normalized = "\n".join(lines).strip()
    try:
        parsed = json.loads(normalized)
    except json.JSONDecodeError:
        return None
    if not isinstance(parsed, dict):
        return None
    reply_text = parsed.get("reply_text")
    if not isinstance(reply_text, str):
        return None
    cleaned = reply_text.strip()
    return cleaned or None


def _handled_by_for_action(action: str | None) -> str | None:
    if action in {"create_task", "list_tasks", "complete_task", "cancel_task"}:
        return "task"
    if action in {"create_reminder", "list_reminders", "cancel_reminder"}:
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
        "list_reminders": f"reminder_listed_via_{source}",
        "create_memory": f"memory_created_via_{source}",
        "archive_memory": f"memory_archived_via_{source}",
        "list_memories": f"memory_listed_via_{source}",
        "show_overview": f"overview_shown_via_{source}",
        "show_activity": f"activity_shown_via_{source}",
    }
    return action_reason_map.get(result.action, f"{intent}_handled")


def _build_assistant_turn_state(
    *,
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
        return {
            "dialogue_mode": "confirmation",
            "last_assistant_action": {
                "action_type": execution_result.confirm_action,
                "success": True,
                "object_type": None,
                "object_id": None,
                "summary": execution_result.preview_text or execution_result.prompt,
            },
        }

    state: JSONObject = {
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
        state["focused_object"] = {
            "object_type": execution_result.object_type,
            "object_id": execution_result.object_id,
            "title": execution_result.object_title,
        }
    visible_candidates = _extract_visible_candidates(execution_result)
    if visible_candidates:
        state["visible_candidates"] = cast(JSONValue, visible_candidates)
    return state


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
