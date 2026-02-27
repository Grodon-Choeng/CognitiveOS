from app.core import BaseRepository
from app.models import Memory


class MemoryRepository(BaseRepository[Memory]):
    def __init__(self) -> None:
        super().__init__(Memory)

    async def get_recent_by_user(self, user_id: str, limit: int = 20) -> list[Memory]:
        return (
            await self.model.objects()
            .where(self.get_col("user_id") == user_id)
            .order_by(self.get_col("created_at"), ascending=False)
            .limit(limit)
            .run()
        )

    async def get_by_ids(self, memory_ids: list[int]) -> list[Memory]:
        if not memory_ids:
            return []

        rows = await self.model.objects().where(self.get_col("id").is_in(memory_ids)).run()
        by_id = {row.id: row for row in rows}
        return [by_id[mid] for mid in memory_ids if mid in by_id]
