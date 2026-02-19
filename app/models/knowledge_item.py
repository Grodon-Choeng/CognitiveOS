from piccolo.columns import JSON, Text, Varchar

from app.core import BaseModel, TimestampMixin


class KnowledgeItem(BaseModel, TimestampMixin):
    raw_text = Text()
    structured_text = Text(null=True, default=None)
    source = Varchar(length=100)
    tags = JSON(default=list)
    links = JSON(default=list)
    embedding = JSON(null=True, default=None)

    class Meta:
        tablename = "knowledge_item"
