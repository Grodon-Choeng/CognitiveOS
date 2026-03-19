from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True, frozen=True)
class AgentTurnRequest:
    user_message: str
    conversation_id: str | None = None
    context: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True, frozen=True)
class AgentTurnResult:
    output_text: str
    metadata: dict[str, Any] = field(default_factory=dict)
