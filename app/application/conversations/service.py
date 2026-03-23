import json
from datetime import datetime
from time import perf_counter
from typing import Protocol

from app.application.audit.dto import AuditEventPageDTO
from app.application.conversations.commands import HandleInboundConversationMessageCommand
from app.application.conversations.dto import ConversationInboundResult
from app.application.conversations.handlers import ConversationInboundHandler
from app.application.conversations.ports import ConversationContextResolver
from app.infrastructure.llm.gateway import LLMGateway
from app.infrastructure.llm.models import GenerateRequest
from app.observability.message_events import MessageEventRecord, MessageEventRecorder


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
        except Exception:
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
        except Exception:
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
        conversation_context_resolver: ConversationContextResolver,
        message_event_recorder: MessageEventRecorder,
        handlers: list[ConversationInboundHandler],
        fallback_responder: LLMConversationFallbackResponder | None = None,
    ) -> None:
        self.conversation_context_resolver = conversation_context_resolver
        self.message_event_recorder = message_event_recorder
        self.handlers = handlers
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
            result = await self._dispatch_to_handlers(
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
                )
            )
            raise

        await self.message_event_recorder.record(
            _build_inbound_record(
                command=command,
                conversation_id=conversation_context.conversation_id,
                session_id=conversation_context.session_id,
                handled=result.handled,
                handled_by=result.handled_by,
                reason=result.reason,
                response_text=result.response_text,
                success=True,
                error_code=None,
                error_message=None,
                latency_ms=(perf_counter() - started_at) * 1000,
            )
        )
        return result

    async def _dispatch_to_handlers(
        self,
        *,
        command: HandleInboundConversationMessageCommand,
        conversation_id: str,
        session_id: str,
    ) -> ConversationInboundResult:
        for handler in self.handlers:
            result = await handler.handle(
                command,
                conversation_id=conversation_id,
                session_id=session_id,
            )
            if result is not None and result.handled:
                return result

        if self.fallback_responder is not None:
            fallback_reply = await self.fallback_responder.generate_reply(
                command=command,
                conversation_id=conversation_id,
                session_id=session_id,
            )
            if fallback_reply is not None:
                return ConversationInboundResult(
                    handled=True,
                    conversation_id=conversation_id,
                    session_id=session_id,
                    handled_by="conversation",
                    reason="llm_fallback_replied",
                    response_text=fallback_reply,
                )

        return ConversationInboundResult(
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
) -> MessageEventRecord:
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
        metadata={
            "handled": handled,
            "handled_by": handled_by,
            "reason": reason,
            "response_text": response_text,
        },
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
