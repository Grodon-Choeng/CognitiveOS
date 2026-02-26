from app.config import settings
from app.services.llm_service import LLMService


class MemoryEmbedder:
    def __init__(self, llm_service: LLMService) -> None:
        self._llm_service = llm_service

    @property
    def dimension(self) -> int:
        return settings.embedding_dimension

    async def embed(self, text: str) -> list[float]:
        vector = await self._llm_service.get_embedding(text)
        if len(vector) != self.dimension:
            raise ValueError(
                f"Embedding dimension mismatch: got {len(vector)}, expect {self.dimension}"
            )
        return vector
