import json

from app.config import settings
from app.repositories import EmbeddingRecordRepository, MemoryRepository
from app.services.llm_service import LLMService
from app.utils import logger

from .embedder import MemoryEmbedder
from .faiss_store import MemoryFAISSStore


class MemoryWriter:
    def __init__(
        self,
        memory_repo: MemoryRepository,
        embedding_repo: EmbeddingRecordRepository,
        embedder: MemoryEmbedder,
        store: MemoryFAISSStore,
        llm_service: LLMService,
    ) -> None:
        self._memory_repo = memory_repo
        self._embedding_repo = embedding_repo
        self._embedder = embedder
        self._store = store
        self._llm_service = llm_service

    @staticmethod
    def _fallback_type(text: str) -> str:
        text_lower = text.lower()
        if any(token in text_lower for token in ("喜欢", "偏好", "preference")):
            return "preference"
        if any(token in text_lower for token in ("任务", "todo", "deadline", "must")):
            return "fact"
        if any(token in text_lower for token in ("技能", "workflow", "步骤")):
            return "skill"
        return "conversation"

    @staticmethod
    def _fallback_importance(text: str) -> int:
        if len(text) >= 500:
            return 4
        if len(text) >= 180:
            return 3
        if len(text) <= 10:
            return 1
        return 2

    async def _memory_judge(self, text: str) -> dict[str, object]:
        system_prompt = (
            "You are a memory classifier. Decide if text should be stored in long-term memory. "
            "Return strict JSON with keys: should_store(bool), memory_type(str), importance(int 1-5), "
            "summary(str)."
        )
        user_prompt = f"Text:\n{text}\n\nReturn JSON only."

        try:
            raw = await self._llm_service.chat_with_system(
                system_prompt=system_prompt,
                user_message=user_prompt,
                temperature=0.0,
                max_tokens=settings.memory_judge_max_tokens,
            )
            data = json.loads(raw)
            return {
                "should_store": bool(data.get("should_store", True)),
                "memory_type": str(data.get("memory_type") or self._fallback_type(text)),
                "importance": int(data.get("importance") or self._fallback_importance(text)),
                "summary": str(data.get("summary") or text[:200]),
            }
        except Exception as e:
            logger.warning(f"Memory judge fallback: {e}")
            return {
                "should_store": len(text.strip()) > 12,
                "memory_type": self._fallback_type(text),
                "importance": self._fallback_importance(text),
                "summary": text[:200],
            }

    async def write(
        self,
        user_id: str,
        content: str,
        *,
        memory_type: str | None = None,
        importance: int | None = None,
        force: bool = False,
    ) -> int | None:
        if not content.strip():
            return None

        decision = await self._memory_judge(content)
        if not force and not bool(decision["should_store"]):
            return None

        memory_type_final = memory_type or str(decision["memory_type"])
        importance_final = int(importance or decision["importance"])
        importance_final = max(1, min(5, importance_final))
        summary = str(decision["summary"])

        memory = await self._memory_repo.create(
            user_id=user_id,
            content=content,
            summary=summary,
            memory_type=memory_type_final,
            importance=importance_final,
        )

        embedding = await self._embedder.embed(summary or content)
        vector_id = self._store.add(memory.id, embedding)
        await self._embedding_repo.upsert(
            memory_id=memory.id,
            model_name=self._llm_service.model,
            dimension=len(embedding),
            vector_id=vector_id,
        )
        self._store.save()

        logger.info(
            f"Memory stored: id={memory.id}, user={user_id}, type={memory_type_final}, importance={importance_final}"
        )
        return memory.id
