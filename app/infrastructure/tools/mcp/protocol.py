from dataclasses import dataclass, field

from app.infrastructure.types import JSONObject


@dataclass(slots=True, frozen=True)
class ToolDefinition:
    name: str
    description: str
    input_schema: JSONObject = field(default_factory=dict)
    output_schema: JSONObject = field(default_factory=dict)


@dataclass(slots=True, frozen=True)
class ToolExecutionOptions:
    timeout_seconds: float | None = None
    retry_limit: int = 0
    trace_metadata: JSONObject = field(default_factory=dict)


@dataclass(slots=True, frozen=True)
class ToolCall:
    name: str
    session_id: str | None = None
    conversation_id: str | None = None
    trace_id: str | None = None
    chain_id: str | None = None
    request_id: str | None = None
    arguments: JSONObject = field(default_factory=dict)
    metadata: JSONObject = field(default_factory=dict)
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
    metadata: JSONObject = field(default_factory=dict)
