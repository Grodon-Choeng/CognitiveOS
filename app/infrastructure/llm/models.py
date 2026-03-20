from dataclasses import dataclass, field

from app.infrastructure.types import JSONObject


@dataclass(slots=True, frozen=True)
class GenerateRequest:
    prompt: str
    system_prompt: str | None = None
    model_kind: str = "llm"
    provider: str | None = None
    model: str | None = None
    session_id: str | None = None
    conversation_id: str | None = None
    trace_id: str | None = None
    chain_id: str | None = None
    request_id: str | None = None
    api_key_suffix: str | None = None
    raw_input: JSONObject = field(default_factory=dict)
    metadata: JSONObject = field(default_factory=dict)


@dataclass(slots=True, frozen=True)
class GenerateResult:
    content: str
    model: str
    provider: str
    usage: dict[str, int] = field(default_factory=dict)
    raw_output: JSONObject = field(default_factory=dict)
    metadata: JSONObject = field(default_factory=dict)
