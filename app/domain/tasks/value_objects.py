from dataclasses import dataclass
from uuid import UUID, uuid4


@dataclass(slots=True, frozen=True)
class TaskId:
    value: UUID

    @classmethod
    def new(cls) -> "TaskId":
        return cls(value=uuid4())

    @classmethod
    def from_string(cls, value: str) -> "TaskId":
        return cls(value=UUID(value))
