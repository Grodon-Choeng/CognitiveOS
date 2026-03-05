from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any, Literal

ToolStatus = Literal["ok", "error"]
ToolHandler = Callable[["ToolContext", dict[str, Any]], Awaitable["ToolResult"]]


@dataclass(slots=True)
class ToolContext:
    run_id: str
    user_id: str
    provider: str
    text: str
    channel_id: int | None
    state: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ToolResult:
    status: ToolStatus
    observation: str
    data: dict[str, Any] = field(default_factory=dict)
    message: str = ""


@dataclass(slots=True)
class AgentTool:
    name: str
    description: str
    usage: str
    input_schema: dict[str, Any]
    handler: ToolHandler


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, AgentTool] = {}

    def register(self, tool: AgentTool) -> None:
        self._tools[tool.name] = tool

    def get(self, name: str) -> AgentTool | None:
        return self._tools.get(name)

    def list_tools(self) -> list[AgentTool]:
        return list(self._tools.values())

    def names(self) -> set[str]:
        return set(self._tools.keys())

    async def execute(self, name: str, ctx: ToolContext, args: dict[str, Any]) -> ToolResult:
        tool = self.get(name)
        if tool is None:
            return ToolResult(status="error", observation="unknown_action")
        return await tool.handler(ctx, args)
