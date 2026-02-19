from app.core.repository import BaseRepository
from app.models.prompt import Prompt


class PromptRepository(BaseRepository[Prompt]):
    def __init__(self) -> None:
        super().__init__(Prompt)

    async def get_by_name(self, name: str) -> Prompt | None:
        return (
            await self.model.objects().where(self.get_col("name") == name).first().run()
        )

    async def get_by_category(self, category: str) -> list[Prompt]:
        return (
            await self.model.objects().where(self.get_col("category") == category).run()
        )
