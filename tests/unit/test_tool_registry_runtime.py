import json
from dataclasses import dataclass
from datetime import UTC, datetime

import pytest
from pydantic import Field

from app.application.conversations.commands import HandleInboundConversationMessageCommand
from app.application.conversations.kernel.state import AssistantTurnContext
from app.application.conversations.kernel.tool_registry import (
    RegistryToolRuntime,
    ToolExecutionContext,
    ToolInputModel,
    ToolRegistry,
    build_default_tool_registry,
)
from app.infrastructure.tools.mcp.protocol import ToolCall, ToolExecutionOptions


class EchoInput(ToolInputModel):
    text: str = Field(..., description="回显文本。")


@dataclass(slots=True, frozen=True)
class EchoPayload:
    text: str
    created_at: datetime


class UnusedToolService:
    pass


def _build_execution_context() -> ToolExecutionContext:
    command = HandleInboundConversationMessageCommand(
        channel="web",
        message_type="text",
        user_identity="user-1",
        external_message_id=None,
        root_message_id=None,
        parent_message_id=None,
        chat_id=None,
        thread_id=None,
        text="测试",
        raw_payload={"text": "测试"},
    )
    return ToolExecutionContext(
        command=command,
        conversation_id="conversation-1",
        session_id="session-1",
        turn_context=AssistantTurnContext(
            conversation_id="conversation-1",
            session_id="session-1",
            latest_user_text="测试",
        ),
        trace_id="trace-1",
        chain_id="chain-1",
        request_id="request-1",
    )


@pytest.mark.asyncio
async def test_registry_tool_runtime_serializes_successful_output() -> None:
    registry = ToolRegistry()

    async def echo_handler(payload, context):  # noqa: ANN001
        return EchoPayload(
            text=f"{payload.text}:{context.conversation_id}",
            created_at=datetime(2026, 3, 27, 8, 0, tzinfo=UTC),
        )

    registry.register(
        name="echo.run",
        description="回显测试工具。",
        input_model=EchoInput,
        handler=echo_handler,
    )
    runtime = RegistryToolRuntime(registry=registry, execution_context=_build_execution_context())

    result = await runtime.execute(
        ToolCall(
            name="echo.run",
            arguments={"text": "hello"},
        )
    )

    assert result.is_error is False
    parsed = json.loads(result.content)
    assert parsed == {
        "text": "hello:conversation-1",
        "created_at": "2026-03-27T08:00:00+00:00",
    }


@pytest.mark.asyncio
async def test_registry_tool_runtime_returns_validation_error() -> None:
    registry = ToolRegistry()

    async def echo_handler(payload, context):  # noqa: ANN001
        _ = (payload, context)
        return {"ok": True}

    registry.register(
        name="echo.run",
        description="回显测试工具。",
        input_model=EchoInput,
        handler=echo_handler,
    )
    runtime = RegistryToolRuntime(registry=registry, execution_context=_build_execution_context())

    result = await runtime.execute(ToolCall(name="echo.run", arguments={}))

    assert result.is_error is True
    assert result.error is not None
    assert result.error.code == "ToolValidationError"
    parsed = json.loads(result.content)
    assert parsed["error"]["code"] == "ToolValidationError"


@pytest.mark.asyncio
async def test_registry_tool_runtime_retries_and_returns_tool_error() -> None:
    registry = ToolRegistry()
    attempts = {"count": 0}

    async def failing_handler(payload, context):  # noqa: ANN001
        _ = (payload, context)
        attempts["count"] += 1
        raise RuntimeError("boom")

    registry.register(
        name="echo.run",
        description="回显测试工具。",
        input_model=EchoInput,
        handler=failing_handler,
    )
    runtime = RegistryToolRuntime(registry=registry, execution_context=_build_execution_context())

    result = await runtime.execute(
        ToolCall(name="echo.run", arguments={"text": "hello"}),
        ToolExecutionOptions(retry_limit=1),
    )

    assert attempts["count"] == 2
    assert result.is_error is True
    assert result.error is not None
    assert result.error.code == "RuntimeError"
    parsed = json.loads(result.content)
    assert parsed["error"]["details"]["attempt_count"] == 2


@pytest.mark.asyncio
async def test_default_tool_registry_registers_background_worker_tool() -> None:
    registry = build_default_tool_registry(
        reminder_service=UnusedToolService(),
        task_service=UnusedToolService(),
        memory_service=UnusedToolService(),
        overview_service=UnusedToolService(),
    )
    runtime = RegistryToolRuntime(registry=registry, execution_context=_build_execution_context())

    result = await runtime.execute(
        ToolCall(
            name="system.spawn_background_worker",
            arguments={"goal": "整理最近 30 天的待办与提醒并给出规划"},
        )
    )

    assert registry.get("system.spawn_background_worker") is not None
    assert result.is_error is False
    parsed = json.loads(result.content)
    assert parsed == {
        "status": "background_workflow_started",
        "goal": "整理最近 30 天的待办与提醒并给出规划",
    }
