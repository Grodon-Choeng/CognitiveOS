from dataclasses import dataclass, field
from typing import Any, Literal

PlanStatus = Literal["ready", "needs_confirmation", "needs_disambiguation", "unsupported"]


@dataclass(slots=True, frozen=True)
class CandidateRef:
    object_type: str
    object_id: str
    title: str
    score: float


@dataclass(slots=True, frozen=True)
class SubActionPlan:
    action: str
    object_type: str | None
    object_id: str | None
    args: dict[str, Any]


@dataclass(slots=True, frozen=True)
class AssistantActionPlan:
    intent: str
    action: str | None
    object_type: str | None
    object_id: str | None
    args: dict[str, Any] = field(default_factory=dict)
    confidence: float = 0.0
    status: PlanStatus = "ready"
    candidates: list[CandidateRef] = field(default_factory=list)
    sub_actions: list[SubActionPlan] = field(default_factory=list)
    reasoning: str | None = None
