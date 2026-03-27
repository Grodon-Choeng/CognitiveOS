from time import perf_counter
from typing import Protocol

from app.infrastructure.agents.models import (
    AgentChatTurnRequest,
    AgentChatTurnResult,
    AgentTurnRequest,
    AgentTurnResult,
)
from app.infrastructure.types import JSONObject
from app.observability.model_invocations import ModelInvocationRecord, ModelInvocationRecorder


class AgentRuntime(Protocol):
    async def run_turn(self, request: AgentTurnRequest) -> AgentTurnResult: ...


class AgentChatRuntime(Protocol):
    async def run_chat_turn(self, request: AgentChatTurnRequest) -> AgentChatTurnResult: ...


class NoopAgentRuntime:
    async def run_turn(self, request: AgentTurnRequest) -> AgentTurnResult:
        _ = request
        raise NotImplementedError("Agent 运行时尚未接入具体实现。")


class RecordingAgentRuntime:
    def __init__(
        self,
        inner: AgentRuntime,
        recorder: ModelInvocationRecorder,
    ) -> None:
        self.inner = inner
        self.recorder = recorder

    async def run_turn(self, request: AgentTurnRequest) -> AgentTurnResult:
        started_at = perf_counter()

        try:
            result = await self.inner.run_turn(request)
        except Exception as exc:
            await self.recorder.record(
                ModelInvocationRecord.create(
                    operation="agent.run_turn",
                    model_kind=request.model_kind,
                    provider=request.provider,
                    model=request.model,
                    api_key_suffix=request.api_key_suffix,
                    session_id=request.session_id,
                    conversation_id=request.conversation_id,
                    trace_id=request.trace_id,
                    chain_id=request.chain_id,
                    request_id=request.request_id,
                    latency_ms=(perf_counter() - started_at) * 1000,
                    success=False,
                    error_type=type(exc).__name__,
                    error_message=str(exc),
                    raw_input=_build_agent_raw_input(request),
                    raw_output={},
                    metadata={},
                )
            )
            raise

        await self.recorder.record(
            ModelInvocationRecord.create(
                operation="agent.run_turn",
                model_kind=request.model_kind,
                provider=result.provider or request.provider,
                model=result.model or request.model,
                api_key_suffix=request.api_key_suffix,
                session_id=request.session_id,
                conversation_id=request.conversation_id,
                trace_id=request.trace_id,
                chain_id=request.chain_id,
                request_id=request.request_id,
                latency_ms=(perf_counter() - started_at) * 1000,
                usage=result.usage,
                raw_input=_build_agent_raw_input(request),
                raw_output=_build_agent_raw_output(result),
                metadata=result.metadata,
            )
        )
        return result


class RecordingAgentChatRuntime:
    def __init__(
        self,
        inner: AgentChatRuntime,
        recorder: ModelInvocationRecorder,
    ) -> None:
        self.inner = inner
        self.recorder = recorder

    async def run_chat_turn(self, request: AgentChatTurnRequest) -> AgentChatTurnResult:
        started_at = perf_counter()

        try:
            result = await self.inner.run_chat_turn(request)
        except Exception as exc:
            await self.recorder.record(
                ModelInvocationRecord.create(
                    operation="agent.chat_turn",
                    model_kind=request.model_kind,
                    provider=request.provider,
                    model=request.model,
                    api_key_suffix=request.api_key_suffix,
                    session_id=request.session_id,
                    conversation_id=request.conversation_id,
                    trace_id=request.trace_id,
                    chain_id=request.chain_id,
                    request_id=request.request_id,
                    latency_ms=(perf_counter() - started_at) * 1000,
                    success=False,
                    error_type=type(exc).__name__,
                    error_message=str(exc),
                    raw_input=_build_agent_chat_raw_input(request),
                    raw_output={},
                    metadata=request.metadata,
                )
            )
            raise

        await self.recorder.record(
            ModelInvocationRecord.create(
                operation="agent.chat_turn",
                model_kind=request.model_kind,
                provider=result.provider or request.provider,
                model=result.model or request.model,
                api_key_suffix=request.api_key_suffix,
                session_id=request.session_id,
                conversation_id=request.conversation_id,
                trace_id=request.trace_id,
                chain_id=request.chain_id,
                request_id=request.request_id,
                latency_ms=(perf_counter() - started_at) * 1000,
                usage=result.usage,
                raw_input=_build_agent_chat_raw_input(request),
                raw_output=_build_agent_chat_raw_output(result),
                metadata={**request.metadata, **result.metadata},
            )
        )
        return result


def _build_agent_raw_input(request: AgentTurnRequest) -> JSONObject:
    if request.raw_input:
        return request.raw_input

    return {
        "user_message": request.user_message,
        "context": request.context,
    }


def _build_agent_raw_output(result: AgentTurnResult) -> JSONObject:
    if result.raw_output:
        return result.raw_output

    return {
        "output_text": result.output_text,
        "usage": _build_usage_payload(result.usage),
        "metadata": result.metadata,
    }


def _build_usage_payload(usage: dict[str, int]) -> JSONObject:
    return {key: value for key, value in usage.items()}


def _build_agent_chat_raw_input(request: AgentChatTurnRequest) -> JSONObject:
    if request.raw_input:
        return request.raw_input

    return {
        "system_prompt": request.system_prompt,
        "messages": [
            {
                "role": message.role,
                "content": message.content,
                "name": message.name,
                "tool_call_id": message.tool_call_id,
                "tool_calls": [
                    {
                        "id": tool_call.id,
                        "name": tool_call.name,
                        "arguments": tool_call.arguments,
                    }
                    for tool_call in message.tool_calls
                ],
            }
            for message in request.messages
        ],
        "tools": [
            {
                "name": tool.name,
                "description": tool.description,
                "input_schema": tool.input_schema,
            }
            for tool in request.tools
        ],
        "tool_choice": request.tool_choice,
        "metadata": request.metadata,
    }


def _build_agent_chat_raw_output(result: AgentChatTurnResult) -> JSONObject:
    if result.raw_output:
        return result.raw_output

    return {
        "output_text": result.output_text,
        "tool_calls": [
            {
                "id": tool_call.id,
                "name": tool_call.name,
                "arguments": tool_call.arguments,
            }
            for tool_call in result.tool_calls
        ],
        "stop_reason": result.stop_reason,
        "usage": _build_usage_payload(result.usage),
        "metadata": result.metadata,
    }
