import re
from collections.abc import Callable
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from app.application.conversations.commands import HandleInboundConversationMessageCommand
from app.application.conversations.kernel.complexity import ComplexityAssessment
from app.application.conversations.kernel.plans import AssistantActionPlan
from app.application.conversations.kernel.state import AssistantTurnContext
from app.application.conversations.kernel.structured_plans import (
    ConstraintPlan,
    OverridePlan,
    RuleItemPlan,
    ScheduleSpec,
    StructuredRulePlan,
)
from app.application.conversations.kernel.temporal_parsing import default_now

_PART_SPLIT_RE = re.compile(r"[，,]+|然后|并且|同时|另外")
_TIME_RE = re.compile(
    r"(?:(?P<period>早上|上午|中午|下午|晚上))?"
    r"(?P<hour>\d{1,2})点(?:(?P<minute>\d{1,2})分?)?"
)


class StructuredRulePlanner:
    def __init__(
        self,
        *,
        now_provider: Callable[[], datetime] | None = None,
        default_timezone: str = "Asia/Shanghai",
    ) -> None:
        self.now_provider = now_provider or default_now
        self.default_timezone = default_timezone

    async def plan(
        self,
        command: HandleInboundConversationMessageCommand,
        *,
        turn_context: AssistantTurnContext,
        assessment: ComplexityAssessment,
    ) -> AssistantActionPlan | None:
        _ = turn_context
        if command.message_type != "text" or command.text is None:
            return None
        structured_plan = self.build_structured_plan(
            command.text,
            request_kind=assessment.request_kind,
        )
        if structured_plan is None:
            return None
        return AssistantActionPlan(
            intent="complex_rule_request",
            action="preview_structured_rule_plan",
            object_type=None,
            object_id=None,
            args={
                "structured_plan": structured_plan.to_dict(),
                "request_kind": assessment.request_kind,
                "signals": list(assessment.signals),
            },
            confidence=assessment.confidence,
            reasoning="rules",
        )

    def build_structured_plan(
        self,
        text: str,
        *,
        request_kind: str,
    ) -> StructuredRulePlan | None:
        parts = [part.strip() for part in _PART_SPLIT_RE.split(text) if part.strip()]
        if not parts:
            return None

        rule_items: list[RuleItemPlan] = []
        overrides: list[OverridePlan] = []
        constraints: list[ConstraintPlan] = []
        inherited_weekdays: list[str] = []
        pending_override_date: date | None = None

        for part in parts:
            if "另行通知" in part or "其他非工作日" in part:
                constraints.append(
                    ConstraintPlan(
                        summary="其他非工作日不自动创建提醒，等待你另行通知。",
                        note_text=part,
                    )
                )
                continue

            override_date = self._extract_override_date(part)
            if override_date is not None and "提醒" not in part:
                pending_override_date = override_date
                continue

            rule_item = self._build_rule_item(
                part,
                inherited_weekdays=inherited_weekdays,
                rule_index=len(rule_items) + 1,
            )
            if rule_item is not None:
                rule_items.append(rule_item)
                if rule_item.schedule.weekdays:
                    inherited_weekdays = list(rule_item.schedule.weekdays)
                continue

            target_date = override_date or pending_override_date
            if target_date is not None and rule_items and "提醒" in part:
                date_label = self._label_for_date(target_date)
                overrides.append(
                    OverridePlan(
                        override_id=f"override-{len(overrides) + 1}",
                        summary=f"{date_label} 额外沿用当前规则提醒。",
                        schedule=ScheduleSpec(
                            schedule_type="one_off_date",
                            timezone=self.default_timezone,
                            local_date=target_date.isoformat(),
                            label=date_label,
                        ),
                        applies_to_rule_ids=[item.rule_id for item in rule_items],
                    )
                )
                pending_override_date = None

        if not rule_items and not overrides and not constraints:
            return None
        if not rule_items and overrides:
            return None
        return StructuredRulePlan(
            request_kind=request_kind,
            original_text=text,
            rule_items=rule_items,
            overrides=overrides,
            constraints=constraints,
        )

    def _build_rule_item(
        self,
        part: str,
        *,
        inherited_weekdays: list[str],
        rule_index: int,
    ) -> RuleItemPlan | None:
        if "提醒" not in part:
            return None
        time_match = _TIME_RE.search(part)
        if time_match is None:
            return None
        reminder_text = _extract_reminder_text(part)
        if reminder_text is None:
            return None
        weekdays = _extract_weekdays(part) or inherited_weekdays
        schedule_type = "recurring" if weekdays else "one_off"
        hour = int(time_match.group("hour"))
        minute = int(time_match.group("minute") or 0)
        period = time_match.group("period")
        if period in {"下午", "晚上"} and hour < 12:
            hour += 12
        if period == "中午" and hour < 11:
            hour += 12
        label = _schedule_label(weekdays=weekdays, hour=hour, minute=minute)
        return RuleItemPlan(
            rule_id=f"rule-{rule_index}",
            reminder_text=reminder_text,
            schedule=ScheduleSpec(
                schedule_type=schedule_type,
                timezone=self.default_timezone,
                weekdays=list(weekdays),
                hour=hour,
                minute=minute,
                label=label,
            ),
            summary=f"{label}提醒“{reminder_text}”",
        )

    def _extract_override_date(self, part: str) -> date | None:
        current = self.now_provider().astimezone(ZoneInfo(self.default_timezone)).date()
        if "本周六" in part:
            return _next_weekday_in_current_week(current, weekday=5)
        if "本周日" in part:
            return _next_weekday_in_current_week(current, weekday=6)
        return None

    def _label_for_date(self, target_date: date) -> str:
        current = self.now_provider().astimezone(ZoneInfo(self.default_timezone)).date()
        if target_date == _next_weekday_in_current_week(current, weekday=5):
            return "本周六"
        if target_date == _next_weekday_in_current_week(current, weekday=6):
            return "本周日"
        return target_date.isoformat()


def _extract_weekdays(text: str) -> list[str]:
    if "工作日" in text:
        return ["mon", "tue", "wed", "thu", "fri"]
    return []


def _schedule_label(*, weekdays: list[str], hour: int, minute: int) -> str:
    day_label = "工作日" if weekdays == ["mon", "tue", "wed", "thu", "fri"] else "单次"
    return f"{day_label} {hour:02d}:{minute:02d}"


def _extract_reminder_text(text: str) -> str | None:
    _, marker, suffix = text.partition("提醒我")
    if not marker:
        return None
    cleaned = suffix.strip("，,。；; ")
    return cleaned or None


def _next_weekday_in_current_week(current: date, *, weekday: int) -> date:
    delta = weekday - current.weekday()
    if delta < 0:
        delta += 7
    return current + timedelta(days=delta)
