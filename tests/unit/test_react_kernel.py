import json

import pytest
from pydantic import Field

from app.application.conversations.commands import HandleInboundConversationMessageCommand
from app.application.conversations.dto import ConversationFastPathResult
from app.application.conversations.kernel.react_kernel import ReActAgentKernel
from app.application.conversations.kernel.state import AssistantTurnContext
from app.application.conversations.kernel.tool_registry import (
    ToolInputModel,
    ToolRegistry,
)
from app.application.conversations.ports import (
    ConversationContextResolver,
    ResolvedConversationContext,
)
from app.application.conversations.service import ConversationApplicationService
from app.infrastructure.agents.models import AgentChatTurnResult, AgentToolCall
from app.infrastructure.types import JSONObject
from app.observability.tool_invocations import ToolInvocationRecord


class ListTasksInput(ToolInputModel):
    limit: int = Field(default=1, ge=1, le=20)


class FakeTurnContextBuilder:
    async def build(
        self,
        *,
        conversation_id: str,
        session_id: str,
        latest_user_text: str | None,
    ) -> AssistantTurnContext:
        return AssistantTurnContext(
            conversation_id=conversation_id,
            session_id=session_id,
            latest_user_text=latest_user_text,
            recent_messages=["assistant: 你好", "user: 帮我看一下待办"],
            metadata={
                "pending_tasks": [
                    {
                        "object_type": "task",
                        "object_id": "task-1",
                        "title": "写周报",
                    }
                ]
            },
        )


class SequencedAgentRuntime:
    def __init__(self, results: list[AgentChatTurnResult]) -> None:
        self.results = results
        self.requests: list[object] = []

    async def run_chat_turn(self, request):  # noqa: ANN001
        self.requests.append(request)
        return self.results.pop(0)


class FakeToolInvocationRecorder:
    def __init__(self) -> None:
        self.records: list[ToolInvocationRecord] = []

    async def record(self, record: ToolInvocationRecord) -> None:
        self.records.append(record)


class FakeConversationContextResolver(ConversationContextResolver):
    async def resolve_for_outbound(
        self,
        *,
        provided_conversation_id: str | None,
        provided_session_id: str | None,
        source_channel: str | None,
        source_user_id: str | None,
        source_chat_id: str | None,
        source_thread_id: str | None,
    ) -> ResolvedConversationContext:
        _ = (
            provided_conversation_id,
            provided_session_id,
            source_channel,
            source_user_id,
            source_chat_id,
            source_thread_id,
        )
        return ResolvedConversationContext(
            conversation_id="conversation-1",
            session_id="session-1",
        )

    async def resolve_for_inbound(
        self,
        *,
        source_channel: str,
        source_user_id: str,
        source_chat_id: str | None,
        source_thread_id: str | None,
    ) -> ResolvedConversationContext:
        _ = (source_channel, source_user_id, source_chat_id, source_thread_id)
        return ResolvedConversationContext(
            conversation_id="conversation-1",
            session_id="session-1",
        )


class FakeReminderHandler:
    async def handle(
        self,
        command: HandleInboundConversationMessageCommand,
        *,
        conversation_id: str,
        session_id: str,
    ) -> ConversationFastPathResult:
        _ = (command, conversation_id, session_id)
        return ConversationFastPathResult(
            decision="pass_to_kernel",
            conversation_id=conversation_id,
            session_id=session_id,
        )


class FakeTurnStateStore:
    def __init__(self) -> None:
        self.saved: list[tuple[str, str, JSONObject]] = []

    async def load(
        self,
        *,
        conversation_id: str,
        session_id: str,
    ) -> JSONObject | None:
        _ = (conversation_id, session_id)
        return None

    async def save(
        self,
        *,
        conversation_id: str,
        session_id: str,
        state: JSONObject,
    ) -> None:
        self.saved.append((conversation_id, session_id, state))


class FakeMessageEventRecorder:
    async def record(self, record) -> None:  # noqa: ANN001
        _ = record


class FakeKernelFacade:
    def __init__(self) -> None:
        self.turn_context_builder = object()
        self.planner = object()
        self.executor = object()
        self.renderer = object()
        self.calls: list[str | None] = []

    async def handle(
        self,
        command: HandleInboundConversationMessageCommand,
        *,
        conversation_id: str,
        session_id: str,
    ):  # noqa: ANN201
        _ = (conversation_id, session_id)
        self.calls.append(command.text)
        raise AssertionError("开启 ReAct 开关后不应走旧 kernel facade。")

    @staticmethod
    def build_debug_payload(outcome):  # noqa: ANN001, ANN205
        _ = outcome
        return {"stage": "kernel"}


def _build_command(text: str) -> HandleInboundConversationMessageCommand:
    return HandleInboundConversationMessageCommand(
        channel="web",
        message_type="text",
        user_identity="user-1",
        external_message_id=None,
        root_message_id=None,
        parent_message_id=None,
        chat_id=None,
        thread_id=None,
        text=text,
        raw_payload={"text": text},
    )


def _build_registry(*, failing: bool = False) -> ToolRegistry:
    registry = ToolRegistry()

    async def list_tasks(payload, context):  # noqa: ANN001
        _ = context
        if failing:
            raise RuntimeError("任务服务失败")
        return {"items": [{"title": "写周报"}], "limit": payload.limit}

    registry.register(
        name="tasks.list",
        description="列出待办。",
        input_model=ListTasksInput,
        handler=list_tasks,
    )
    return registry


@pytest.mark.asyncio
async def test_react_kernel_works_with_conversation_service_and_saves_state() -> None:
    runtime = SequencedAgentRuntime(
        [
            AgentChatTurnResult(
                tool_calls=[
                    AgentToolCall(
                        id="call_1",
                        name="tasks.list",
                        arguments={"limit": 1},
                    )
                ]
            ),
            AgentChatTurnResult(output_text="我查到 1 条待办：写周报。"),
        ]
    )
    tool_recorder = FakeToolInvocationRecorder()
    kernel = ReActAgentKernel(
        turn_context_builder=FakeTurnContextBuilder(),
        agent_runtime=runtime,
        tool_registry=_build_registry(),
        tool_invocation_recorder=tool_recorder,
        provider="openai",
        model="gpt-4.1-mini",
    )
    turn_state_store = FakeTurnStateStore()
    kernel_facade = FakeKernelFacade()
    service = ConversationApplicationService(
        conversation_context_resolver=FakeConversationContextResolver(),
        message_event_recorder=FakeMessageEventRecorder(),
        reminder_handler=FakeReminderHandler(),
        kernel_facade=kernel_facade,
        react_kernel=kernel,
        conversation_use_react_agent=True,
        turn_state_store=turn_state_store,
    )

    result = await service.handle_inbound_message(_build_command("看一下我的待办"))

    assert result.handled is True
    assert result.handled_by == "agent"
    assert result.reason == "react_agent_completed"
    assert result.response_text == "我查到 1 条待办：写周报。"
    assert len(runtime.requests) == 2
    second_request = runtime.requests[1]
    assert json.loads(second_request.messages[-1].content) == {
        "items": [{"title": "写周报"}],
        "limit": 1,
    }
    assert len(tool_recorder.records) == 1
    assert tool_recorder.records[0].tool_name == "tasks.list"
    saved_state = turn_state_store.saved[0][2]
    assert saved_state["agent_loop"]["iterations"] == 2
    assert kernel_facade.calls == []


@pytest.mark.asyncio
async def test_react_kernel_can_continue_after_tool_error() -> None:
    runtime = SequencedAgentRuntime(
        [
            AgentChatTurnResult(
                tool_calls=[
                    AgentToolCall(
                        id="call_1",
                        name="tasks.list",
                        arguments={"limit": 1},
                    )
                ]
            ),
            AgentChatTurnResult(output_text="任务服务暂时失败，我先把现状告诉你。"),
        ]
    )
    kernel = ReActAgentKernel(
        turn_context_builder=FakeTurnContextBuilder(),
        agent_runtime=runtime,
        tool_registry=_build_registry(failing=True),
        tool_invocation_recorder=FakeToolInvocationRecorder(),
        provider="openai",
        model="gpt-4.1-mini",
    )

    outcome = await kernel.handle(
        _build_command("看一下我的待办"),
        conversation_id="conversation-1",
        session_id="session-1",
    )

    assert outcome.reason == "react_agent_completed"
    assert outcome.response_text == "任务服务暂时失败，我先把现状告诉你。"
    execution_result = outcome.execution_result
    assert isinstance(execution_result, object)
    second_request = runtime.requests[1]
    tool_message = second_request.messages[-1]
    assert "RuntimeError" in tool_message.content


@pytest.mark.asyncio
async def test_react_kernel_returns_graceful_message_after_max_iterations() -> None:
    runtime = SequencedAgentRuntime(
        [
            AgentChatTurnResult(
                tool_calls=[
                    AgentToolCall(
                        id=f"call_{index}",
                        name="tasks.list",
                        arguments={"limit": 1},
                    )
                ]
            )
            for index in range(1, 6)
        ]
    )
    kernel = ReActAgentKernel(
        turn_context_builder=FakeTurnContextBuilder(),
        agent_runtime=runtime,
        tool_registry=_build_registry(),
        tool_invocation_recorder=FakeToolInvocationRecorder(),
        provider="openai",
        model="gpt-4.1-mini",
        max_iterations=5,
    )

    outcome = await kernel.handle(
        _build_command("把这个复杂请求跑完"),
        conversation_id="conversation-1",
        session_id="session-1",
    )

    assert outcome.reason == "react_agent_max_iterations"
    assert outcome.response_text is not None
    assert "步骤有点多" in outcome.response_text
    assert outcome.assistant_turn_state is not None
    assert outcome.assistant_turn_state["agent_loop"]["iterations"] == 5
