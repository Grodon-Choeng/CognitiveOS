from dataclasses import dataclass, replace
from typing import Literal

from app.application.conversations.kernel.plans import AssistantActionPlan, CandidateRef
from app.application.conversations.kernel.policies import (
    ASK_CONFIRMATION_MIN_CONFIDENCE,
    AUTO_EXECUTE_MIN_CONFIDENCE,
    MAX_DISAMBIGUATION_CANDIDATES,
)
from app.application.conversations.kernel.state import AssistantTurnContext

ResolutionStatus = Literal["matched", "ambiguous", "not_found", "needs_confirmation"]

_PRONOUN_HINTS = {"这个", "那个", "刚才那个", "刚刚那个", "这条", "那条"}
_ORDINAL_HINTS = {
    "第一个": 0,
    "第一项": 0,
    "第1个": 0,
    "第二个": 1,
    "第二项": 1,
    "第2个": 1,
}


@dataclass(slots=True, frozen=True)
class ReferenceResolution:
    status: ResolutionStatus
    candidate: CandidateRef | None = None
    candidates: list[CandidateRef] | None = None
    prompt: str | None = None


class ReferenceResolver:
    def resolve(
        self,
        plan: AssistantActionPlan,
        *,
        turn_context: AssistantTurnContext,
    ) -> AssistantActionPlan:
        if plan.object_type is None or plan.action is None or plan.object_id is not None:
            return plan
        if plan.status != "ready":
            return plan

        resolution = self.resolve_reference(plan, turn_context=turn_context)
        if resolution.status == "matched" and resolution.candidate is not None:
            return replace(
                plan,
                object_id=resolution.candidate.object_id,
                candidates=[],
                status="ready",
            )
        if resolution.status == "needs_confirmation" and resolution.candidate is not None:
            return replace(
                plan,
                object_id=resolution.candidate.object_id,
                candidates=[resolution.candidate],
                status="needs_confirmation",
            )
        if resolution.status == "ambiguous":
            return replace(
                plan,
                candidates=resolution.candidates or [],
                status="needs_disambiguation",
            )
        return replace(plan, status="unsupported")

    def resolve_reference(
        self,
        plan: AssistantActionPlan,
        *,
        turn_context: AssistantTurnContext,
    ) -> ReferenceResolution:
        if plan.object_type is None:
            return ReferenceResolution(status="not_found")
        object_type = plan.object_type
        reference_text = _normalize_reference_text(plan.args.get("reference_text"))
        working_candidates = _get_working_candidates(turn_context, object_type)
        visible_candidates = _get_visible_candidates(turn_context, object_type)

        if reference_text is None:
            if (
                turn_context.focused_object is not None
                and turn_context.focused_object.object_type == object_type
            ):
                focused_candidate = CandidateRef(
                    object_type=turn_context.focused_object.object_type,
                    object_id=turn_context.focused_object.object_id,
                    title=turn_context.focused_object.title or "当前对象",
                    score=0.98,
                )
                return self._apply_confirmation_policy(plan, focused_candidate)
            if working_candidates:
                return self._apply_confirmation_policy(plan, working_candidates[0])
            return ReferenceResolution(status="not_found")

        if reference_text in _PRONOUN_HINTS:
            if (
                turn_context.focused_object is not None
                and turn_context.focused_object.object_type == object_type
            ):
                focused_candidate = CandidateRef(
                    object_type=turn_context.focused_object.object_type,
                    object_id=turn_context.focused_object.object_id,
                    title=turn_context.focused_object.title or "当前对象",
                    score=0.99,
                )
                return self._apply_confirmation_policy(plan, focused_candidate)
            if len(visible_candidates) == 1:
                return self._apply_confirmation_policy(plan, visible_candidates[0])
            if visible_candidates:
                return ReferenceResolution(
                    status="ambiguous",
                    candidates=visible_candidates[:MAX_DISAMBIGUATION_CANDIDATES],
                )
            if len(working_candidates) == 1:
                return self._apply_confirmation_policy(plan, working_candidates[0])
            if working_candidates:
                return ReferenceResolution(
                    status="ambiguous",
                    candidates=working_candidates[:MAX_DISAMBIGUATION_CANDIDATES],
                )
            return ReferenceResolution(status="not_found")

        if reference_text in _ORDINAL_HINTS:
            index = _ORDINAL_HINTS[reference_text]
            ordered_candidates = visible_candidates or working_candidates
            if index < len(ordered_candidates):
                return self._apply_confirmation_policy(plan, ordered_candidates[index])
            return ReferenceResolution(status="not_found")

        if reference_text in {"最后一个", "最后一项"}:
            ordered_candidates = visible_candidates or working_candidates
            if ordered_candidates:
                return self._apply_confirmation_policy(plan, ordered_candidates[-1])
            return ReferenceResolution(status="not_found")

        filtered_candidates = _match_candidates_by_keyword(
            candidates=visible_candidates or working_candidates,
            reference_text=reference_text,
        )
        if len(filtered_candidates) == 1:
            return self._apply_confirmation_policy(plan, filtered_candidates[0])
        if len(filtered_candidates) > 1:
            return ReferenceResolution(
                status="ambiguous",
                candidates=filtered_candidates[:MAX_DISAMBIGUATION_CANDIDATES],
            )
        return ReferenceResolution(status="not_found")

    @staticmethod
    def _apply_confirmation_policy(
        plan: AssistantActionPlan,
        candidate: CandidateRef,
    ) -> ReferenceResolution:
        if plan.confidence >= AUTO_EXECUTE_MIN_CONFIDENCE:
            return ReferenceResolution(status="matched", candidate=candidate)
        if plan.confidence >= ASK_CONFIRMATION_MIN_CONFIDENCE:
            return ReferenceResolution(status="needs_confirmation", candidate=candidate)
        return ReferenceResolution(status="ambiguous", candidates=[candidate])


def _get_visible_candidates(
    turn_context: AssistantTurnContext,
    object_type: str,
) -> list[CandidateRef]:
    return [
        CandidateRef(
            object_type=candidate.object_type,
            object_id=candidate.object_id,
            title=candidate.title,
            score=candidate.score,
        )
        for candidate in turn_context.visible_candidates
        if candidate.object_type == object_type
    ]


def _get_working_candidates(
    turn_context: AssistantTurnContext,
    object_type: str,
) -> list[CandidateRef]:
    key = {
        "task": "pending_tasks",
        "reminder": "pending_reminders",
        "memory": "active_memories",
    }.get(object_type)
    if key is None:
        return []
    candidates: list[CandidateRef] = []
    raw_items = turn_context.metadata.get(key)
    if not isinstance(raw_items, list):
        return candidates
    for index, item in enumerate(raw_items):
        if not isinstance(item, dict):
            continue
        object_id = item.get("object_id")
        title = item.get("title")
        if isinstance(object_id, str) and isinstance(title, str):
            candidates.append(
                CandidateRef(
                    object_type=object_type,
                    object_id=object_id,
                    title=title,
                    score=max(0.6, 0.95 - index * 0.05),
                )
            )
    return candidates


def _normalize_reference_text(reference_text: object) -> str | None:
    if not isinstance(reference_text, str):
        return None
    normalized = reference_text.strip()
    return normalized or None


def _match_candidates_by_keyword(
    *,
    candidates: list[CandidateRef],
    reference_text: str,
) -> list[CandidateRef]:
    normalized_hint = _strip_reference_noise(reference_text.casefold())
    if not normalized_hint:
        return []
    matched: list[CandidateRef] = []
    for candidate in candidates:
        if normalized_hint in _strip_reference_noise(candidate.title.casefold()):
            matched.append(candidate)
    return matched


def _strip_reference_noise(reference_text: str) -> str:
    normalized = reference_text
    for token in ("提醒", "待办", "任务", "记忆", "这个", "那个", "这条", "那条"):
        normalized = normalized.replace(token, "")
    return normalized.strip()
