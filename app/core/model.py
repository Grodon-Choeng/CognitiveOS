from datetime import datetime
from typing import Any
from uuid import UUID as UUID_
from uuid import uuid4

from piccolo.columns import UUID, Serial, Timestamp
from piccolo.table import Table

from app.utils.times import utc_time


class BaseModel(Table):
    id = Serial(primary_key=True)
    uuid = UUID(default=uuid4, index=True)
    created_at = Timestamp(default=utc_time, index=True)
    updated_at = Timestamp(default=utc_time, index=True)

    class Meta:
        abstract = True

    def to_dict(self) -> dict[str, Any]:
        result = {}
        for column in self._meta.columns:
            value = getattr(self, column._meta.name, None)
            result[column._meta.name] = self._serialize_value(value)
        return result

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "BaseModel":
        instance = cls.__new__(cls)
        for key, value in data.items():
            if hasattr(cls, key):
                setattr(instance, key, cls._deserialize_value(value, key))
        return instance

    @staticmethod
    def _serialize_value(value: Any) -> Any:
        if value is None:
            return None

        if isinstance(value, UUID_):
            return str(value)
        if isinstance(value, datetime):
            return value.isoformat()
        return value

    @classmethod
    def _deserialize_value(cls, value: Any, field_name: str) -> Any:
        if value is None:
            return None

        column = getattr(cls, field_name, None)
        if column is None:
            return value

        column_type = type(column).__name__

        if column_type == "UUID":
            return UUID_(value) if isinstance(value, str) else value
        if column_type in ("Timestamp", "TimestampDefault") and isinstance(value, str):
            return datetime.fromisoformat(value)
        return value
