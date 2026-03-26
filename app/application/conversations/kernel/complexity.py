from dataclasses import dataclass, field
from typing import Literal

RequestKind = Literal["simple_action", "multi_action", "rule_with_overrides", "ambiguous"]

_RULE_KEYWORDS = (
    "工作日",
    "每天",
    "每周",
    "周一",
    "周二",
    "周三",
    "周四",
    "周五",
    "周六",
    "周日",
    "周末",
)
_OVERRIDE_KEYWORDS = ("本周", "今天", "明天", "后天", "加班", "补班")
_CONSTRAINT_KEYWORDS = ("另行通知", "其他非", "除外", "不用", "不需要", "先不要")
_AMBIGUOUS_KEYWORDS = ("到时候", "看情况", "合适的时候", "那个时候")
_CONNECTOR_KEYWORDS = ("然后", "另外", "同时", "并且")


@dataclass(slots=True, frozen=True)
class ComplexityAssessment:
    is_complex: bool
    request_kind: RequestKind
    signals: list[str] = field(default_factory=list)
    confidence: float = 0.0


class ComplexRequestDetector:
    def assess(self, text: str | None) -> ComplexityAssessment:
        if text is None:
            return ComplexityAssessment(
                is_complex=False,
                request_kind="simple_action",
                signals=[],
                confidence=0.0,
            )

        normalized = text.strip()
        if not normalized:
            return ComplexityAssessment(
                is_complex=False,
                request_kind="simple_action",
                signals=[],
                confidence=0.0,
            )

        signals: list[str] = []
        reminder_mentions = normalized.count("提醒")
        if reminder_mentions >= 2:
            signals.append("multiple_reminder_mentions")
        if any(token in normalized for token in _RULE_KEYWORDS):
            signals.append("rule_keyword")
        if any(token in normalized for token in _OVERRIDE_KEYWORDS):
            signals.append("override_keyword")
        if any(token in normalized for token in _CONSTRAINT_KEYWORDS):
            signals.append("constraint_keyword")
        if any(token in normalized for token in _AMBIGUOUS_KEYWORDS):
            signals.append("ambiguous_keyword")
        if any(token in normalized for token in _CONNECTOR_KEYWORDS):
            signals.append("connector_keyword")

        has_rule = "rule_keyword" in signals
        has_override = "override_keyword" in signals
        has_constraint = "constraint_keyword" in signals
        has_ambiguous = "ambiguous_keyword" in signals
        has_multi = "multiple_reminder_mentions" in signals or (
            "connector_keyword" in signals and reminder_mentions >= 1
        )

        if has_ambiguous and (has_rule or has_multi):
            return ComplexityAssessment(
                is_complex=True,
                request_kind="ambiguous",
                signals=signals,
                confidence=0.66,
            )
        if has_rule and (has_override or has_constraint):
            return ComplexityAssessment(
                is_complex=True,
                request_kind="rule_with_overrides",
                signals=signals,
                confidence=0.93,
            )
        if has_rule and has_multi:
            return ComplexityAssessment(
                is_complex=True,
                request_kind="rule_with_overrides",
                signals=signals,
                confidence=0.88,
            )
        if has_multi:
            return ComplexityAssessment(
                is_complex=True,
                request_kind="multi_action",
                signals=signals,
                confidence=0.82,
            )
        return ComplexityAssessment(
            is_complex=False,
            request_kind="simple_action",
            signals=signals,
            confidence=0.2 if signals else 0.0,
        )
