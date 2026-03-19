from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True, frozen=True)
class ToolDefinition:
    name: str
    description: str
    input_schema: dict[str, Any] = field(default_factory=dict)
    output_schema: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True, frozen=True)
class ToolExecutionOptions:
    timeout_seconds: float | None = None
    retry_limit: int = 0
    trace_metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True, frozen=True)
class ToolCall:
    name: str
    arguments: dict[str, Any] = field(default_factory=dict)
    options: ToolExecutionOptions = field(default_factory=ToolExecutionOptions)


@dataclass(slots=True, frozen=True)
class ToolError:
    code: str
    message: str


@dataclass(slots=True, frozen=True)
class ToolResult:
    content: str
    is_error: bool = False
    error: ToolError | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
