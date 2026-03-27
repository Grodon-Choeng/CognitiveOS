import json
import logging
from dataclasses import dataclass

from app.application.conversations.commands import HandleInboundConversationMessageCommand
from app.application.conversations.kernel.facade import ConversationKernelOutcome
from app.application.conversations.kernel.plans import AssistantActionPlan
from app.application.conversations.kernel.results import AssistantExecutionResult
from app.application.conversations.kernel.state import (
    AssistantTurnContext,
    AssistantTurnContextBuilder,
)
from app.application.conversations.kernel.tool_registry import (
    RegistryToolRuntime,
    ToolExecutionContext,
    ToolRegistry,
)
from app.infrastructure.agents.models import (
    AgentChatTurnRequest,
    AgentToolCall,
    ChatMessage,
)
from app.infrastructure.agents.runtime import AgentChatRuntime
from app.infrastructure.tools.mcp.protocol import ToolCall, ToolExecutionOptions, ToolResult
from app.infrastructure.tools.runtime.executor import RecordingToolRuntime
from app.infrastructure.types import JSONObject
from app.observability.context import current_trace_fields
from app.observability.tool_invocations import ToolInvocationRecorder

logger = logging.getLogger(__name__)


@dataclass(slots=True, frozen=True)
class ReActKernelResult:
    response_text: str
    reason: str
    success: bool
    iterations: int
    tool_history: list[JSONObject]


class ReActAgentKernel:
    def __init__(
        self,
        *,
        turn_context_builder: AssistantTurnContextBuilder,
        agent_runtime: AgentChatRuntime,
        tool_registry: ToolRegistry,
        tool_invocation_recorder: ToolInvocationRecorder,
        provider: str,
        model: str,
        api_key_suffix: str | None = None,
        max_iterations: int = 5,
        tool_timeout_seconds: float = 15.0,
        tool_retry_limit: int = 0,
    ) -> None:
        self.turn_context_builder = turn_context_builder
        self.agent_runtime = agent_runtime
        self.tool_registry = tool_registry
        self.tool_invocation_recorder = tool_invocation_recorder
        self.provider = provider
        self.model = model
        self.api_key_suffix = api_key_suffix
        self.max_iterations = max_iterations
        self.tool_timeout_seconds = tool_timeout_seconds
        self.tool_retry_limit = tool_retry_limit
        # 兼容 `ConversationApplicationService` 对旧 facade 属性的访问。
        self.planner = None
        self.executor = None
        self.renderer = None

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
        plan = AssistantActionPlan(
            intent="react_agent",
            action="react_agent_loop",
            object_type=None,
            object_id=None,
            confidence=1.0,
            reasoning="llm",
        )
        if command.message_type != "text" or command.text is None or not command.text.strip():
            return ConversationKernelOutcome(
                turn_context=turn_context,
                plan=plan,
                execution_result=None,
                response_text=None,
                handled_by=None,
                reason=None,
                assistant_turn_state=None,
            )

        result = await self._run_loop(
            command=command,
            conversation_id=conversation_id,
            session_id=session_id,
            turn_context=turn_context,
        )
        execution_result = AssistantExecutionResult(
            success=result.success,
            action="react_agent_loop",
            payload={
                "iterations": result.iterations,
                "tool_history": result.tool_history,
                "reason": result.reason,
            },
            message_hint=result.response_text,
        )
        return ConversationKernelOutcome(
            turn_context=turn_context,
            plan=plan,
            execution_result=execution_result,
            response_text=result.response_text,
            handled_by="agent",
            reason=result.reason,
            assistant_turn_state=_build_assistant_turn_state(result),
        )

    @staticmethod
    def build_debug_payload(outcome: ConversationKernelOutcome) -> JSONObject:
        payload = {}
        execution_result = outcome.execution_result
        if isinstance(execution_result, AssistantExecutionResult):
            payload = execution_result.payload
        return {
            "stage": "react_kernel",
            "reason": outcome.reason,
            "response_text": outcome.response_text,
            "payload": payload,
        }

    async def _run_loop(
        self,
        *,
        command: HandleInboundConversationMessageCommand,
        conversation_id: str,
        session_id: str,
        turn_context: AssistantTurnContext,
    ) -> ReActKernelResult:
        trace_id, chain_id, request_id = current_trace_fields()
        messages = [
            ChatMessage(role="user", content=command.text),
        ]
        tool_history: list[JSONObject] = []

        for iteration in range(1, self.max_iterations + 1):
            try:
                result = await self.agent_runtime.run_chat_turn(
                    AgentChatTurnRequest(
                        system_prompt=_build_system_prompt(turn_context),
                        messages=messages,
                        tools=self.tool_registry.definitions(),
                        provider=self.provider,
                        model=self.model,
                        api_key_suffix=self.api_key_suffix,
                        conversation_id=conversation_id,
                        session_id=session_id,
                        trace_id=trace_id,
                        chain_id=chain_id,
                        request_id=request_id,
                        metadata={
                            "component": "react_agent_kernel",
                            "iteration": iteration,
                        },
                    )
                )
            except Exception as exc:
                logger.warning(
                    "ReAct agent 调用模型失败，回退到友好降级回复。",
                    extra={
                        "conversation_id": conversation_id,
                        "session_id": session_id,
                        "iteration": iteration,
                        "error_type": type(exc).__name__,
                        "error_message": str(exc),
                    },
                )
                return ReActKernelResult(
                    response_text="这次处理没有稳定完成，我先停在这里。你可以换个说法，或者把目标拆成更短的一句再试一次。",
                    reason="react_agent_runtime_error",
                    success=False,
                    iterations=iteration,
                    tool_history=tool_history,
                )

            if result.tool_calls:
                tool_results = await self._execute_tool_calls(
                    command=command,
                    conversation_id=conversation_id,
                    session_id=session_id,
                    turn_context=turn_context,
                    trace_id=trace_id,
                    chain_id=chain_id,
                    request_id=request_id,
                    iteration=iteration,
                    tool_calls=result.tool_calls,
                )
                tool_history.extend(tool_results.history_items)
                messages.append(
                    ChatMessage(
                        role="assistant",
                        content=result.output_text,
                        tool_calls=result.tool_calls,
                    )
                )
                messages.extend(tool_results.messages)
                continue

            if result.output_text and result.output_text.strip():
                return ReActKernelResult(
                    response_text=result.output_text.strip(),
                    reason="react_agent_completed",
                    success=True,
                    iterations=iteration,
                    tool_history=tool_history,
                )

            logger.warning(
                "ReAct agent 返回了无法处理的空响应。",
                extra={
                    "conversation_id": conversation_id,
                    "session_id": session_id,
                    "iteration": iteration,
                },
            )
            return ReActKernelResult(
                response_text="我这次没有生成稳定结果。你可以直接告诉我你要执行的动作，我再重新试一次。",
                reason="react_agent_invalid_response",
                success=False,
                iterations=iteration,
                tool_history=tool_history,
            )

        return ReActKernelResult(
            response_text="这次请求涉及的步骤有点多，我先停在这里以避免误操作。你可以把目标拆成两三步继续告诉我。",
            reason="react_agent_max_iterations",
            success=False,
            iterations=self.max_iterations,
            tool_history=tool_history,
        )

    async def _execute_tool_calls(
        self,
        *,
        command: HandleInboundConversationMessageCommand,
        conversation_id: str,
        session_id: str,
        turn_context: AssistantTurnContext,
        trace_id: str | None,
        chain_id: str | None,
        request_id: str | None,
        iteration: int,
        tool_calls: list[AgentToolCall],
    ) -> "_ToolExecutionBundle":
        execution_context = ToolExecutionContext(
            command=command,
            conversation_id=conversation_id,
            session_id=session_id,
            turn_context=turn_context,
            trace_id=trace_id,
            chain_id=chain_id,
            request_id=request_id,
        )
        runtime = RecordingToolRuntime(
            RegistryToolRuntime(
                registry=self.tool_registry,
                execution_context=execution_context,
            ),
            self.tool_invocation_recorder,
        )
        messages: list[ChatMessage] = []
        history_items: list[JSONObject] = []
        for tool_call in tool_calls:
            result = await runtime.execute(
                ToolCall(
                    name=tool_call.name,
                    session_id=session_id,
                    conversation_id=conversation_id,
                    trace_id=trace_id,
                    chain_id=chain_id,
                    request_id=request_id,
                    arguments=tool_call.arguments,
                    metadata={
                        "source": "react_agent_kernel",
                        "iteration": iteration,
                    },
                    options=ToolExecutionOptions(
                        timeout_seconds=self.tool_timeout_seconds,
                        retry_limit=self.tool_retry_limit,
                    ),
                )
            )
            messages.append(
                ChatMessage(
                    role="tool",
                    name=tool_call.name,
                    tool_call_id=tool_call.id,
                    content=result.content,
                )
            )
            history_items.append(_build_tool_history_item(tool_call=tool_call, result=result))
        return _ToolExecutionBundle(messages=messages, history_items=history_items)


@dataclass(slots=True, frozen=True)
class _ToolExecutionBundle:
    messages: list[ChatMessage]
    history_items: list[JSONObject]


def _build_tool_history_item(
    *,
    tool_call: AgentToolCall,
    result: ToolResult,
) -> JSONObject:
    item: JSONObject = {
        "tool_call_id": tool_call.id,
        "tool_name": tool_call.name,
        "is_error": result.is_error,
        "content": result.content,
    }
    if result.error is not None:
        item["error"] = {
            "code": result.error.code,
            "message": result.error.message,
        }
    return item


def _build_system_prompt(turn_context: AssistantTurnContext) -> str:
    context_payload = {
        "conversation_id": turn_context.conversation_id,
        "session_id": turn_context.session_id,
        "dialogue_mode": turn_context.dialogue_mode,
        "focused_object": (
            {
                "object_type": turn_context.focused_object.object_type,
                "object_id": turn_context.focused_object.object_id,
                "title": turn_context.focused_object.title,
            }
            if turn_context.focused_object is not None
            else None
        ),
        "visible_candidates": [
            {
                "object_type": candidate.object_type,
                "object_id": candidate.object_id,
                "title": candidate.title,
                "score": candidate.score,
                "reason": candidate.reason,
            }
            for candidate in turn_context.visible_candidates
        ],
        "recent_messages": turn_context.recent_messages,
        "working_set": {
            "pending_reminders": turn_context.metadata.get("pending_reminders", []),
            "pending_tasks": turn_context.metadata.get("pending_tasks", []),
            "active_memories": turn_context.metadata.get("active_memories", []),
            "failed_reminders": turn_context.metadata.get("failed_reminders", []),
            "recent_activity": turn_context.metadata.get("recent_activity", []),
        },
        "last_assistant_action": (
            {
                "action_type": turn_context.last_assistant_action.action_type,
                "success": turn_context.last_assistant_action.success,
                "object_type": turn_context.last_assistant_action.object_type,
                "object_id": turn_context.last_assistant_action.object_id,
                "summary": turn_context.last_assistant_action.summary,
            }
            if turn_context.last_assistant_action is not None
            else None
        ),
    }
    return (
        "你是 CognitiveOS 的 ReAct 对话执行内核。"
        "你可以自主决定是否调用工具，并且可以多轮调用工具后再给出最终答复。"
        "如果要调用工具，必须基于可用工具的 schema 严格填写参数。"
        "如果工具失败，不要假装成功；应根据 tool 返回的错误继续推理或向用户解释。"
        "当你已经拿到足够信息时，直接输出最终中文回复，不要再输出额外的 JSON 包装。"
        "下面是当前对话上下文：\n"
        f"{json.dumps(context_payload, ensure_ascii=False)}"
    )


def _build_assistant_turn_state(result: ReActKernelResult) -> JSONObject:
    return {
        "dialogue_mode": "normal",
        "agent_loop": {
            "iterations": result.iterations,
            "reason": result.reason,
            "tool_history": result.tool_history,
        },
        "last_assistant_action": {
            "action_type": "react_agent_loop",
            "success": result.success,
            "object_type": None,
            "object_id": None,
            "summary": result.response_text,
        },
    }
