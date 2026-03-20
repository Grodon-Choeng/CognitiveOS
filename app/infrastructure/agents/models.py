from dataclasses import dataclass, field

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
