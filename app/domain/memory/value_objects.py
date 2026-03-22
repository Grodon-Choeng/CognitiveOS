from dataclasses import dataclass
from uuid import UUID, uuid4


@dataclass(slots=True, frozen=True)
class MemoryId:
    value: UUID

    @classmethod
    def new(cls) -> "MemoryId":
        return cls(value=uuid4())

    @classmethod
    def from_string(cls, value: str) -> "MemoryId":
        return cls(value=UUID(value))
