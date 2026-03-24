from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal, Protocol

from app.application.audit.dto import AuditEventPageDTO
from app.application.overview.dto import OverviewDTO
from app.application.overview.queries import GetOverviewQuery

DialogueMode = Literal[
    "normal",
    "confirmation",
    "disambiguation",
    "followup_edit",
    "browse_results",
]


@dataclass(slots=True, frozen=True)
class FocusedObjectRef:
    object_type: str
    object_id: str
    title: str | None = None


@dataclass(slots=True, frozen=True)
class CandidateObjectRef:
    object_type: str
    object_id: str
    title: str
    score: float
    reason: str | None = None


@dataclass(slots=True, frozen=True)
class LastAssistantAction:
    action_type: str
    success: bool
    object_type: str | None = None
    object_id: str | None = None
    summary: str | None = None


@dataclass(slots=True, frozen=True)
class AssistantTurnContext:
    conversation_id: str
    session_id: str
    latest_user_text: str | None
    recent_messages: list[str] = field(default_factory=list)
    focused_object: FocusedObjectRef | None = None
    visible_candidates: list[CandidateObjectRef] = field(default_factory=list)
    pending_reminder_ids: list[str] = field(default_factory=list)
    pending_task_ids: list[str] = field(default_factory=list)
    active_memory_ids: list[str] = field(default_factory=list)
    dialogue_mode: DialogueMode = "normal"
    last_assistant_action: LastAssistantAction | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


class TurnContextOverviewReader(Protocol):
    async def get_overview(self, query: GetOverviewQuery) -> OverviewDTO: ...


class TurnContextHistoryReader(Protocol):
    async def list_events(
        self,
        *,
        kind: str,
        conversation_id: str | None = None,
        session_id: str | None = None,
        success: bool | None = None,
        channel: str | None = None,
        provider: str | None = None,
        tool_name: str | None = None,
        workflow_type: str | None = None,
        recorded_after: datetime | None = None,
        recorded_before: datetime | None = None,
        cursor: str | None = None,
        limit: int = 50,
    ) -> AuditEventPageDTO: ...


class AssistantTurnContextBuilder:
    def __init__(
        self,
        *,
        overview_service: TurnContextOverviewReader,
        history_reader: TurnContextHistoryReader,
        working_set_limit: int = 5,
        history_limit: int = 12,
    ) -> None:
        self.overview_service = overview_service
        self.history_reader = history_reader
        self.working_set_limit = working_set_limit
        self.history_limit = history_limit

    async def build(
        self,
        *,
        conversation_id: str,
        session_id: str,
        latest_user_text: str | None,
    ) -> AssistantTurnContext:
        overview = await self.overview_service.get_overview(
            GetOverviewQuery(
                conversation_id=conversation_id,
                session_id=session_id,
                reminder_limit=self.working_set_limit,
                task_limit=self.working_set_limit,
                memory_limit=self.working_set_limit,
                recent_activity_limit=3,
            )
        )
        history_page = await self.history_reader.list_events(
            kind="message",
            conversation_id=conversation_id,
            session_id=session_id,
            limit=self.history_limit,
        )

        recent_messages = _build_recent_messages(history_page)
        metadata = _build_working_set_metadata(overview)
        state_metadata = _extract_latest_state_metadata(history_page)

        focused_object = _build_focused_object(state_metadata)
        visible_candidates = _build_visible_candidates(state_metadata)
        last_assistant_action = _build_last_assistant_action(state_metadata)
        dialogue_mode = _build_dialogue_mode(state_metadata)

        metadata.update(
            {
                "last_state_metadata": state_metadata,
                "recent_activity": [
                    {
                        "kind": event.kind,
                        "summary": event.summary,
                    }
                    for event in overview.recent_activity
                ],
            }
        )

        return AssistantTurnContext(
            conversation_id=conversation_id,
            session_id=session_id,
            latest_user_text=latest_user_text,
            recent_messages=recent_messages,
            focused_object=focused_object,
            visible_candidates=visible_candidates,
            pending_reminder_ids=[item["object_id"] for item in metadata["pending_reminders"]],
            pending_task_ids=[item["object_id"] for item in metadata["pending_tasks"]],
            active_memory_ids=[item["object_id"] for item in metadata["active_memories"]],
            dialogue_mode=dialogue_mode,
            last_assistant_action=last_assistant_action,
            metadata=metadata,
        )


def _build_recent_messages(history_page: AuditEventPageDTO) -> list[str]:
    lines: list[str] = []
    for event in reversed(history_page.items):
        payload = event.payload
        direction = payload.get("direction")
        text = payload.get("text")
        if not isinstance(direction, str) or not isinstance(text, str):
            continue
        normalized_text = text.strip()
        if not normalized_text:
            continue
        speaker = "assistant" if direction == "outbound" else "user"
        lines.append(f"{speaker}: {normalized_text}")
    return lines


def _build_working_set_metadata(overview: OverviewDTO) -> dict[str, Any]:
    return {
        "pending_reminders": [
            {
                "object_type": "reminder",
                "object_id": reminder.reminder_id,
                "title": reminder.text,
                "status": reminder.status,
                "when": reminder.remind_at.isoformat(),
            }
            for reminder in overview.pending_reminders
        ],
        "pending_tasks": [
            {
                "object_type": "task",
                "object_id": task.task_id,
                "title": task.title,
                "status": task.status,
            }
            for task in overview.pending_tasks
        ],
        "active_memories": [
            {
                "object_type": "memory",
                "object_id": memory.memory_id,
                "title": memory.content,
                "status": memory.status,
            }
            for memory in overview.active_memories
        ],
    }


def _extract_latest_state_metadata(history_page: AuditEventPageDTO) -> dict[str, Any]:
    for event in history_page.items:
        payload = event.payload
        if payload.get("direction") != "inbound":
            continue
        metadata = payload.get("metadata")
        if isinstance(metadata, dict) and metadata.get("assistant_turn_state"):
            state = metadata.get("assistant_turn_state")
            if isinstance(state, dict):
                return state
    return {}


def _build_focused_object(state_metadata: dict[str, Any]) -> FocusedObjectRef | None:
    focused_object = state_metadata.get("focused_object")
    if not isinstance(focused_object, dict):
        return None
    object_type = focused_object.get("object_type")
    object_id = focused_object.get("object_id")
    title = focused_object.get("title")
    if not isinstance(object_type, str) or not isinstance(object_id, str):
        return None
    return FocusedObjectRef(
        object_type=object_type,
        object_id=object_id,
        title=title if isinstance(title, str) else None,
    )


def _build_visible_candidates(state_metadata: dict[str, Any]) -> list[CandidateObjectRef]:
    visible_candidates = state_metadata.get("visible_candidates")
    if not isinstance(visible_candidates, list):
        return []
    candidates: list[CandidateObjectRef] = []
    for candidate in visible_candidates:
        if not isinstance(candidate, dict):
            continue
        object_type = candidate.get("object_type")
        object_id = candidate.get("object_id")
        title = candidate.get("title")
        score = candidate.get("score")
        reason = candidate.get("reason")
        if (
            isinstance(object_type, str)
            and isinstance(object_id, str)
            and isinstance(title, str)
            and isinstance(score, (int, float))
        ):
            candidates.append(
                CandidateObjectRef(
                    object_type=object_type,
                    object_id=object_id,
                    title=title,
                    score=float(score),
                    reason=reason if isinstance(reason, str) else None,
                )
            )
    return candidates


def _build_last_assistant_action(state_metadata: dict[str, Any]) -> LastAssistantAction | None:
    last_action = state_metadata.get("last_assistant_action")
    if not isinstance(last_action, dict):
        return None
    action_type = last_action.get("action_type")
    success = last_action.get("success")
    object_type = last_action.get("object_type")
    object_id = last_action.get("object_id")
    summary = last_action.get("summary")
    if not isinstance(action_type, str) or not isinstance(success, bool):
        return None
    return LastAssistantAction(
        action_type=action_type,
        success=success,
        object_type=object_type if isinstance(object_type, str) else None,
        object_id=object_id if isinstance(object_id, str) else None,
        summary=summary if isinstance(summary, str) else None,
    )


def _build_dialogue_mode(state_metadata: dict[str, Any]) -> DialogueMode:
    dialogue_mode = state_metadata.get("dialogue_mode")
    if dialogue_mode in {
        "normal",
        "confirmation",
        "disambiguation",
        "followup_edit",
        "browse_results",
    }:
        return dialogue_mode
    return "normal"
