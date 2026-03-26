from dataclasses import dataclass, field


@dataclass(slots=True, frozen=True)
class ScheduleSpec:
    schedule_type: str
    timezone: str
    local_date: str | None = None
    weekdays: list[str] = field(default_factory=list)
    hour: int | None = None
    minute: int | None = None
    label: str | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "schedule_type": self.schedule_type,
            "timezone": self.timezone,
            "local_date": self.local_date,
            "weekdays": list(self.weekdays),
            "hour": self.hour,
            "minute": self.minute,
            "label": self.label,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, object]) -> "ScheduleSpec":
        weekdays = payload.get("weekdays")
        return cls(
            schedule_type=str(payload["schedule_type"]),
            timezone=str(payload["timezone"]),
            local_date=_optional_str(payload.get("local_date")),
            weekdays=[item for item in weekdays if isinstance(item, str)]
            if isinstance(weekdays, list)
            else [],
            hour=_optional_int(payload.get("hour")),
            minute=_optional_int(payload.get("minute")),
            label=_optional_str(payload.get("label")),
        )


@dataclass(slots=True, frozen=True)
class RuleItemPlan:
    rule_id: str
    reminder_text: str
    schedule: ScheduleSpec
    summary: str

    def to_dict(self) -> dict[str, object]:
        return {
            "rule_id": self.rule_id,
            "reminder_text": self.reminder_text,
            "schedule": self.schedule.to_dict(),
            "summary": self.summary,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, object]) -> "RuleItemPlan":
        schedule = payload.get("schedule")
        if not isinstance(schedule, dict):
            raise ValueError("结构化规则缺少 schedule。")
        return cls(
            rule_id=str(payload["rule_id"]),
            reminder_text=str(payload["reminder_text"]),
            schedule=ScheduleSpec.from_dict(schedule),
            summary=str(payload["summary"]),
        )


@dataclass(slots=True, frozen=True)
class OverridePlan:
    override_id: str
    summary: str
    schedule: ScheduleSpec
    applies_to_rule_ids: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return {
            "override_id": self.override_id,
            "summary": self.summary,
            "schedule": self.schedule.to_dict(),
            "applies_to_rule_ids": list(self.applies_to_rule_ids),
        }

    @classmethod
    def from_dict(cls, payload: dict[str, object]) -> "OverridePlan":
        schedule = payload.get("schedule")
        rule_ids = payload.get("applies_to_rule_ids")
        if not isinstance(schedule, dict):
            raise ValueError("结构化 override 缺少 schedule。")
        return cls(
            override_id=str(payload["override_id"]),
            summary=str(payload["summary"]),
            schedule=ScheduleSpec.from_dict(schedule),
            applies_to_rule_ids=[item for item in rule_ids if isinstance(item, str)]
            if isinstance(rule_ids, list)
            else [],
        )


@dataclass(slots=True, frozen=True)
class ConstraintPlan:
    summary: str
    note_text: str

    def to_dict(self) -> dict[str, object]:
        return {
            "summary": self.summary,
            "note_text": self.note_text,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, object]) -> "ConstraintPlan":
        return cls(
            summary=str(payload["summary"]),
            note_text=str(payload["note_text"]),
        )


@dataclass(slots=True, frozen=True)
class StructuredRulePlan:
    request_kind: str
    original_text: str
    rule_items: list[RuleItemPlan] = field(default_factory=list)
    overrides: list[OverridePlan] = field(default_factory=list)
    constraints: list[ConstraintPlan] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return {
            "request_kind": self.request_kind,
            "original_text": self.original_text,
            "rule_items": [item.to_dict() for item in self.rule_items],
            "overrides": [item.to_dict() for item in self.overrides],
            "constraints": [item.to_dict() for item in self.constraints],
        }

    @classmethod
    def from_dict(cls, payload: dict[str, object]) -> "StructuredRulePlan":
        rule_items = payload.get("rule_items")
        overrides = payload.get("overrides")
        constraints = payload.get("constraints")
        return cls(
            request_kind=str(payload["request_kind"]),
            original_text=str(payload["original_text"]),
            rule_items=[
                RuleItemPlan.from_dict(item) for item in rule_items if isinstance(item, dict)
            ]
            if isinstance(rule_items, list)
            else [],
            overrides=[OverridePlan.from_dict(item) for item in overrides if isinstance(item, dict)]
            if isinstance(overrides, list)
            else [],
            constraints=[
                ConstraintPlan.from_dict(item) for item in constraints if isinstance(item, dict)
            ]
            if isinstance(constraints, list)
            else [],
        )


def _optional_int(value: object) -> int | None:
    return int(value) if isinstance(value, int) else None


def _optional_str(value: object) -> str | None:
    return value if isinstance(value, str) else None
