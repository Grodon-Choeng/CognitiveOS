from time import perf_counter
from typing import Protocol

from app.infrastructure.tools.mcp.protocol import ToolCall, ToolExecutionOptions, ToolResult
from app.observability.tool_invocations import (
    ToolInvocationRecord,
    ToolInvocationRecorder,
    build_tool_raw_input,
    build_tool_raw_output,
)


class ToolRuntime(Protocol):
    async def execute(
        self,
        call: ToolCall,
        options: ToolExecutionOptions | None = None,
    ) -> ToolResult: ...


class NoopToolRuntime:
    async def execute(
        self,
        call: ToolCall,
        options: ToolExecutionOptions | None = None,
    ) -> ToolResult:
        _ = (call, options)
        raise NotImplementedError("工具执行运行时尚未接入具体实现。")


class RecordingToolRuntime:
    def __init__(
        self,
        inner: ToolRuntime,
        recorder: ToolInvocationRecorder,
    ) -> None:
        self.inner = inner
        self.recorder = recorder

    async def execute(
        self,
        call: ToolCall,
        options: ToolExecutionOptions | None = None,
    ) -> ToolResult:
        started_at = perf_counter()
        effective_options = options or call.options

        try:
            result = await self.inner.execute(call, options)
        except Exception as exc:
            await self.recorder.record(
                ToolInvocationRecord.create(
                    tool_name=call.name,
                    session_id=call.session_id,
                    conversation_id=call.conversation_id,
                    trace_id=call.trace_id,
                    chain_id=call.chain_id,
                    request_id=call.request_id,
                    latency_ms=(perf_counter() - started_at) * 1000,
                    timeout_seconds=effective_options.timeout_seconds,
                    retry_limit=effective_options.retry_limit,
                    success=False,
                    error_code=type(exc).__name__,
                    error_message=str(exc),
                    raw_input=build_tool_raw_input(call),
                    raw_output={},
                    metadata=call.metadata,
                )
            )
            raise

        await self.recorder.record(
            ToolInvocationRecord.create(
                tool_name=call.name,
                session_id=call.session_id,
                conversation_id=call.conversation_id,
                trace_id=call.trace_id,
                chain_id=call.chain_id,
                request_id=call.request_id,
                latency_ms=(perf_counter() - started_at) * 1000,
                timeout_seconds=effective_options.timeout_seconds,
                retry_limit=effective_options.retry_limit,
                success=not result.is_error,
                error_code=result.error.code if result.error else None,
                error_message=result.error.message if result.error else None,
                raw_input=build_tool_raw_input(call),
                raw_output=build_tool_raw_output(result),
                metadata={**call.metadata, **result.metadata},
            )
        )
        return result
