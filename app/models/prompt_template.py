from piccolo.columns import Boolean, Integer, Text, Varchar

from app.core import BaseModel


class PromptTemplate(BaseModel):
    name = Varchar(length=128, index=True)
    version = Integer(default=1)
    system_prompt = Text()
    user_prompt_template = Text()
    is_active = Boolean(default=True, index=True)
    category = Varchar(length=64, default="memory")

    class Meta:
        tablename = "prompt_template"
