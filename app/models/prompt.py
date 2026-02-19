from piccolo.columns import Varchar, Text

from app.core.model import BaseModel, TimestampMixin


class Prompt(BaseModel, TimestampMixin):
    name = Varchar(length=100, unique=True)
    description = Varchar(length=255, null=True, default=None)
    content = Text()
    category = Varchar(length=50, default="general")

    class Meta:
        tablename = "prompt"
