from piccolo.columns import Text, Varchar

from app.core.model import BaseModel


class Prompt(BaseModel):
    name = Varchar(length=100, unique=True)
    description = Varchar(length=255, null=True, default=None)
    content = Text()
    category = Varchar(length=50, default="general")

    class Meta:
        tablename = "prompt"
