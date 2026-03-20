from dataclasses import dataclass, field

from app.infrastructure.types import JSONObject


@dataclass(slots=True, frozen=True)
class AgentTurnRequest:
    user_message: str
    conversation_id: str | None = None
    context: JSONObject = field(default_factory=dict)


@dataclass(slots=True, frozen=True)
class AgentTurnResult:
    output_text: str
    metadata: JSONObject = field(default_factory=dict)
