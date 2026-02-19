from piccolo.columns import Varchar, Text, JSON

from app.core.model import BaseModel, TimestampMixin


class KnowledgeItem(BaseModel, TimestampMixin):
    raw_text = Text()
    structured_text = Text(null=True, default=None)
    source = Varchar(length=100)
    tags = JSON(default=list)
    links = JSON(default=list)

    class Meta:
        tablename = "knowledge_item"
