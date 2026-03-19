from typing import Protocol

from app.infrastructure.tools.mcp.protocol import ToolCall, ToolExecutionOptions, ToolResult


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
