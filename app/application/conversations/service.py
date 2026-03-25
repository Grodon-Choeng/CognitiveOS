import json
import logging
from dataclasses import dataclass, replace
from datetime import datetime
from time import perf_counter
from typing import Protocol

from app.application.audit.dto import AuditEventPageDTO
from app.application.conversations.commands import HandleInboundConversationMessageCommand
from app.application.conversations.dto import (
    ConversationFastPathResult,
    ConversationInboundResult,
)
from app.application.conversations.kernel.facade import ConversationKernelFacade
from app.application.conversations.ports import AssistantTurnStateStore, ConversationContextResolver
from app.infrastructure.llm.gateway import LLMGateway
from app.infrastructure.llm.models import GenerateRequest
from app.infrastructure.types import JSONObject
from app.observability.context import current_trace_fields
from app.observability.message_events import MessageEventRecord, MessageEventRecorder

logger = logging.getLogger(__name__)


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
    ) -> ConversationFastPathResult | None: ...


@dataclass(slots=True, frozen=True)
class _ConversationTurnOutcome:
    result: ConversationInboundResult
    assistant_turn_state: JSONObject | None = None
    debug: JSONObject | None = None


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
            trace_id, chain_id, request_id = current_trace_fields()
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
                    trace_id=trace_id,
                    chain_id=chain_id,
                    request_id=request_id,
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
        kernel_facade: ConversationKernelFacade,
        turn_state_store: AssistantTurnStateStore | None,
        fallback_responder: LLMConversationFallbackResponder | None = None,
    ) -> None:
        self.conversation_context_resolver = conversation_context_resolver
        self.message_event_recorder = message_event_recorder
        self.reminder_handler = reminder_handler
        self.kernel_facade = kernel_facade
        self.turn_state_store = turn_state_store
        self.fallback_responder = fallback_responder
        self.turn_context_builder = kernel_facade.turn_context_builder
        self.planner = kernel_facade.planner
        self.executor = kernel_facade.executor
        self.renderer = kernel_facade.renderer

    async def handle_inbound_message(
        self,
        command: HandleInboundConversationMessageCommand,
        include_debug: bool = False,
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

        if outcome.assistant_turn_state is not None and self.turn_state_store is not None:
            await self.turn_state_store.save(
                conversation_id=conversation_context.conversation_id,
                session_id=conversation_context.session_id,
                state=outcome.assistant_turn_state,
            )

        final_result = outcome.result
        if include_debug and outcome.debug is not None:
            final_result = replace(final_result, debug=outcome.debug)

        await self.message_event_recorder.record(
            _build_inbound_record(
                command=command,
                conversation_id=conversation_context.conversation_id,
                session_id=conversation_context.session_id,
                handled=final_result.handled,
                handled_by=final_result.handled_by,
                reason=final_result.reason,
                response_text=final_result.response_text,
                success=True,
                error_code=None,
                error_message=None,
                latency_ms=(perf_counter() - started_at) * 1000,
                assistant_turn_state=outcome.assistant_turn_state,
            )
        )
        return final_result

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
        if reminder_result is not None and reminder_result.decision != "pass_to_kernel":
            return _ConversationTurnOutcome(
                result=ConversationInboundResult(
                    handled=True,
                    conversation_id=conversation_id,
                    session_id=session_id,
                    handled_by=reminder_result.handled_by,
                    reason=reminder_result.reason,
                    response_text=reminder_result.response_text,
                ),
                assistant_turn_state=reminder_result.assistant_turn_state,
                debug=reminder_result.debug,
            )

        kernel_outcome = await self.kernel_facade.handle(
            command,
            conversation_id=conversation_id,
            session_id=session_id,
        )
        if kernel_outcome.execution_result is not None and kernel_outcome.response_text is not None:
            result = ConversationInboundResult(
                handled=True,
                conversation_id=conversation_id,
                session_id=session_id,
                handled_by=kernel_outcome.handled_by,
                reason=kernel_outcome.reason,
                response_text=kernel_outcome.response_text,
            )
            return _ConversationTurnOutcome(
                result=result,
                assistant_turn_state=kernel_outcome.assistant_turn_state,
                debug=self.kernel_facade.build_debug_payload(kernel_outcome),
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
                    debug={
                        "stage": "fallback",
                        "response_text": fallback_reply,
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
            debug={"stage": "no_handler", "response_text": "default_guidance"},
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
    trace_id, chain_id, request_id = current_trace_fields()
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
        trace_id=trace_id,
        chain_id=chain_id,
        request_id=request_id,
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
