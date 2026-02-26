from piccolo.columns import Integer, Text, Timestamp, Varchar

from app.core import BaseModel
from app.utils.times import utc_time


class Memory(BaseModel):
    user_id = Varchar(length=64, index=True)
    content = Text()
    summary = Text(null=True, default=None)
    memory_type = Varchar(length=32, default="conversation", index=True)
    importance = Integer(default=1)
    last_accessed_at = Timestamp(default=utc_time, index=True)

    class Meta:
        tablename = "memory"
