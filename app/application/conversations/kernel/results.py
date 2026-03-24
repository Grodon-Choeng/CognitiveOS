from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True, frozen=True)
class AssistantExecutionResult:
    success: bool
    action: str
    object_type: str | None = None
    object_id: str | None = None
    object_title: str | None = None
    payload: dict[str, Any] = field(default_factory=dict)
    followup_options: list[str] = field(default_factory=list)
    recovery_options: list[str] = field(default_factory=list)
    message_hint: str | None = None


@dataclass(slots=True, frozen=True)
class AssistantDisambiguationResult:
    prompt: str
    candidates: list[dict[str, str]]


@dataclass(slots=True, frozen=True)
class AssistantConfirmationResult:
    prompt: str
    confirm_action: str
    preview_text: str | None = None
