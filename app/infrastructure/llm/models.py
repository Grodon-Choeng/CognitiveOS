from dataclasses import dataclass, field

from app.infrastructure.types import JSONObject


@dataclass(slots=True, frozen=True)
class GenerateRequest:
    prompt: str
    system_prompt: str | None = None
    metadata: JSONObject = field(default_factory=dict)


@dataclass(slots=True, frozen=True)
class GenerateResult:
    content: str
    model: str
    provider: str
    usage: dict[str, int] = field(default_factory=dict)
