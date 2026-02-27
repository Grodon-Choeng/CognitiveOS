from app.core import BaseRepository
from app.models import EmbeddingRecord


class EmbeddingRecordRepository(BaseRepository[EmbeddingRecord]):
    def __init__(self) -> None:
        super().__init__(EmbeddingRecord)

    async def get_by_memory_id_and_model(
        self, memory_id: int, model_name: str
    ) -> EmbeddingRecord | None:
        return (
            await self.model.objects()
            .where(
                (self.get_col("memory_id") == memory_id)
                & (self.get_col("model_name") == model_name)
            )
            .first()
            .run()
        )

    async def upsert(
        self, memory_id: int, model_name: str, dimension: int, vector_id: int
    ) -> EmbeddingRecord:
        existing = await self.get_by_memory_id_and_model(memory_id, model_name)
        if existing:
            existing.dimension = dimension
            existing.vector_id = vector_id
            await existing.save()
            return existing

        return await self.create(
            memory_id=memory_id,
            model_name=model_name,
            dimension=dimension,
            vector_id=vector_id,
        )
