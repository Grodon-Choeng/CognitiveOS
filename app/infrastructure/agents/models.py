from dataclasses import dataclass, field
from typing import Literal

from app.infrastructure.tools.mcp.protocol import ToolDefinition
from app.infrastructure.types import JSONObject


@dataclass(slots=True, frozen=True)
class AgentTurnRequest:
    user_message: str
    conversation_id: str | None = None
    session_id: str | None = None
    trace_id: str | None = None
    chain_id: str | None = None
    request_id: str | None = None
    model_kind: str = "agent"
    provider: str | None = None
    model: str | None = None
    api_key_suffix: str | None = None
    context: JSONObject = field(default_factory=dict)
    raw_input: JSONObject = field(default_factory=dict)


@dataclass(slots=True, frozen=True)
class AgentTurnResult:
    output_text: str
    provider: str | None = None
    model: str | None = None
    usage: dict[str, int] = field(default_factory=dict)
    raw_output: JSONObject = field(default_factory=dict)
    metadata: JSONObject = field(default_factory=dict)


ChatMessageRole = Literal["user", "assistant", "tool"]


@dataclass(slots=True, frozen=True)
class AgentToolCall:
    id: str
    name: str
    arguments: JSONObject = field(default_factory=dict)


@dataclass(slots=True, frozen=True)
class ChatMessage:
    role: ChatMessageRole
    content: str | None = None
    name: str | None = None
    tool_call_id: str | None = None
    tool_calls: list[AgentToolCall] = field(default_factory=list)


@dataclass(slots=True, frozen=True)
class AgentChatTurnRequest:
    messages: list[ChatMessage]
    system_prompt: str | None = None
    tools: list[ToolDefinition] = field(default_factory=list)
    tool_choice: str = "auto"
    conversation_id: str | None = None
    session_id: str | None = None
    trace_id: str | None = None
    chain_id: str | None = None
    request_id: str | None = None
    model_kind: str = "agent"
    provider: str | None = None
    model: str | None = None
    api_key_suffix: str | None = None
    raw_input: JSONObject = field(default_factory=dict)
    metadata: JSONObject = field(default_factory=dict)


@dataclass(slots=True, frozen=True)
class AgentChatTurnResult:
    output_text: str | None = None
    tool_calls: list[AgentToolCall] = field(default_factory=list)
    stop_reason: str | None = None
    provider: str | None = None
    model: str | None = None
    usage: dict[str, int] = field(default_factory=dict)
    raw_output: JSONObject = field(default_factory=dict)
    metadata: JSONObject = field(default_factory=dict)
