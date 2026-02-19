from uuid import uuid4

from piccolo.table import Table
from piccolo.columns import UUID, Timestamp, Serial

from app.utils.times import utc_time


class BaseModel(Table):
    id = Serial(primary_key=True)
    uuid = UUID(default=uuid4, index=True)

    class Meta:
        abstract = True


class TimestampMixin(Table):
    created_at = Timestamp(default=utc_time)
    updated_at = Timestamp(default=utc_time)

    class Meta:
        abstract = True
