from app.core.repository import BaseRepository
from app.models.prompt_template import PromptTemplate


class PromptTemplateRepository(BaseRepository[PromptTemplate]):
    def __init__(self) -> None:
        super().__init__(PromptTemplate)

    async def get_active_by_name(self, name: str) -> PromptTemplate | None:
        return (
            await self.model.objects()
            .where(
                (self.get_col("name") == name) & (self.get_col("is_active") == True)  # noqa: E712
            )
            .order_by(self.get_col("version"), ascending=False)
            .first()
            .run()
        )

    async def list_by_name(self, name: str) -> list[PromptTemplate]:
        return (
            await self.model.objects()
            .where(self.get_col("name") == name)
            .order_by(self.get_col("version"), ascending=False)
            .run()
        )
