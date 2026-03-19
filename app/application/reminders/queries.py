from dataclasses import dataclass


@dataclass(slots=True, frozen=True)
class GetReminderQuery:
    reminder_id: str

