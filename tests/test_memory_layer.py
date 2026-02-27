from dataclasses import dataclass
from datetime import datetime, timedelta

from app.services.memory.faiss_store import MemoryFAISSStore
from app.services.memory.retriever import MemoryHit, MemoryRetriever
from app.utils.times import utc_time


@dataclass
class _MemoryLike:
    id: int
    user_id: str
    memory_type: str
    importance: int
    summary: str
    content: str
    updated_at: datetime


class _FakeRepo:
    def __init__(self, items: list[_MemoryLike]):
        self._items = items

    async def get_by_ids(self, ids: list[int]) -> list[_MemoryLike]:
        by_id = {item.id: item for item in self._items}
        return [by_id[i] for i in ids if i in by_id]


def test_memory_faiss_store_add_and_search(tmp_path, monkeypatch):
    index_path = tmp_path / "memory.index"
    monkeypatch.setattr(
        "app.services.memory.faiss_store.settings.memory_vector_index_path", str(index_path)
    )
    monkeypatch.setattr("app.services.memory.faiss_store.settings.embedding_dimension", 4)

    store = MemoryFAISSStore()
    store.add(memory_id=101, embedding=[1.0, 0.0, 0.0, 0.0])
    store.save()

    hits = store.search([1.0, 0.0, 0.0, 0.0], top_k=3)
    assert len(hits) >= 1
    assert hits[0]["memory_id"] == 101


def test_memory_retriever_build_context():
    memory = _MemoryLike(
        id=1,
        user_id="u1",
        memory_type="fact",
        importance=4,
        summary="记忆摘要",
        content="记忆正文",
        updated_at=utc_time(),
    )
    hit = MemoryHit(memory=memory, similarity=0.9, final_score=0.8, vector_id=1)

    context = MemoryRetriever.build_context([hit], max_tokens=200)
    assert "memory_id=1" in context
    assert "记忆摘要" in context


async def test_memory_retriever_search_scores():
    now = utc_time()
    recent = _MemoryLike(
        id=1,
        user_id="u1",
        memory_type="fact",
        importance=5,
        summary="recent",
        content="recent",
        updated_at=now,
    )
    old = _MemoryLike(
        id=2,
        user_id="u1",
        memory_type="fact",
        importance=5,
        summary="old",
        content="old",
        updated_at=now - timedelta(days=40),
    )

    class _FakeStore:
        # noinspection PyMethodMayBeStatic
        def search(self, _query_embedding, top_k=8):
            _ = top_k
            return [
                {"memory_id": 1, "vector_id": 1, "similarity": 0.8},
                {"memory_id": 2, "vector_id": 2, "similarity": 0.8},
            ]

    retriever = MemoryRetriever(_FakeStore(), _FakeRepo([recent, old]))
    hits = await retriever.search(user_id="u1", query_embedding=[0.0], top_k=2)

    assert len(hits) == 2
    assert hits[0].memory.id == 1
