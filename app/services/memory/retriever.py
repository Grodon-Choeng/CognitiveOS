import math
from dataclasses import dataclass

from app.models import Memory
from app.repositories import MemoryRepository
from app.utils import utc_time

from .faiss_store import MemoryFAISSStore


@dataclass
class MemoryHit:
    memory: Memory
    similarity: float
    final_score: float
    vector_id: int


class MemoryRetriever:
    def __init__(self, store: MemoryFAISSStore, memory_repo: MemoryRepository) -> None:
        self._store = store
        self._memory_repo = memory_repo

    @staticmethod
    def _decay_factor(days: float, lambda_: float = 0.015) -> float:
        return math.exp(-lambda_ * max(days, 0.0))

    async def search(
        self,
        user_id: str,
        query_embedding: list[float],
        top_k: int = 8,
        min_importance: int = 1,
    ) -> list[MemoryHit]:
        raw_hits = self._store.search(query_embedding, top_k=max(top_k * 3, top_k))
        if not raw_hits:
            return []

        ordered_ids = [int(item["memory_id"]) for item in raw_hits]
        memories = await self._memory_repo.get_by_ids(ordered_ids)
        by_id = {m.id: m for m in memories}

        now = utc_time()
        hits: list[MemoryHit] = []
        for item in raw_hits:
            memory_id = int(item["memory_id"])
            memory = by_id.get(memory_id)
            if not memory:
                continue
            if memory.user_id != user_id:
                continue
            if int(memory.importance) < min_importance:
                continue

            similarity = float(item["similarity"])
            importance_weight = min(max(int(memory.importance), 1), 5) / 5.0
            age_days = (now - memory.updated_at).total_seconds() / 86400.0
            decay = self._decay_factor(age_days)
            final_score = (similarity * 0.7 + importance_weight * 0.3) * decay

            hits.append(
                MemoryHit(
                    memory=memory,
                    similarity=similarity,
                    final_score=final_score,
                    vector_id=int(item["vector_id"]),
                )
            )

        hits.sort(key=lambda x: x.final_score, reverse=True)
        return hits[:top_k]

    @staticmethod
    def build_context(hits: list[MemoryHit], max_tokens: int = 1600) -> str:
        parts: list[str] = []
        token_budget = 0

        for hit in hits:
            text = hit.memory.summary or hit.memory.content
            line = (
                f"[memory_id={hit.memory.id};type={hit.memory.memory_type};"
                f"importance={hit.memory.importance};score={hit.final_score:.4f}] {text}"
            )
            estimate = len(line) // 4
            if token_budget + estimate > max_tokens:
                break
            parts.append(line)
            token_budget += estimate

        return "\n".join(parts)
