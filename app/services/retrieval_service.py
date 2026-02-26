from typing import Any

from app.models.knowledge_item import KnowledgeItem
from app.services.embedding_service import EmbeddingService
from app.services.knowledge_item_service import KnowledgeItemService
from app.services.llm_service import LLMService
from app.services.memory.orchestrator import MemoryOrchestrator
from app.services.prompt_service import PromptService
from app.services.vector_store import VectorStore
from app.utils.logging import logger


class RetrievalService:
    def __init__(
        self,
        llm_service: LLMService,
        embedding_service: EmbeddingService,
        knowledge_service: KnowledgeItemService,
        vector_store: VectorStore,
        prompt_service: PromptService,
        memory_orchestrator: MemoryOrchestrator,
    ) -> None:
        self.llm_service = llm_service
        self.embedding_service = embedding_service
        self.knowledge_service = knowledge_service
        self.vector_store = vector_store
        self.prompt_service = prompt_service
        self.memory_orchestrator = memory_orchestrator

    async def search_similar(self, query: str, top_k: int = 5) -> list[dict[str, Any]]:
        query_embedding = await self.llm_service.get_embedding(query)
        results = self.vector_store.search(query_embedding, top_k)
        return results

    async def search_and_retrieve(self, query: str, top_k: int = 5) -> list[KnowledgeItem]:
        results = await self.search_similar(query, top_k)

        if not results:
            return []

        item_ids = [result["item_id"] for result in results]
        items = await self.knowledge_service.get_by_ids(item_ids)

        logger.info(f"Retrieved {len(items)} items for query")
        return items

    async def rag_query(
        self,
        query: str,
        top_k: int = 5,
        max_context_tokens: int = 2000,
        user_id: str = "default",
    ) -> str:
        items = await self.search_and_retrieve(query, top_k)

        if not items:
            # Even when knowledge base has no match, memory layer may still answer.
            logger.info("No knowledge hit, trying memory-only RAG context")

        bundle = await self.memory_orchestrator.build_context(
            user_id=user_id,
            query=query,
            knowledge_items=items,
            top_k=top_k,
        )

        if not bundle.memory_context and not items:
            return "No relevant knowledge found."

        response = await self.llm_service.chat_with_system(
            bundle.system_prompt, bundle.user_prompt, temperature=0.7
        )
        await self.memory_orchestrator.write_back(user_id=user_id, query=query, response=response)

        return response

    @staticmethod
    def _build_context(items: list[KnowledgeItem], max_tokens: int) -> str:
        context_parts = []
        current_length = 0

        for item in items:
            text = item.structured_text or item.raw_text
            entry = f"[ID: {item.id}] {text}\n"

            estimated_tokens = len(entry) // 4
            if current_length + estimated_tokens > max_tokens:
                break

            context_parts.append(entry)
            current_length += estimated_tokens

        return "\n".join(context_parts)

    async def index_item(self, item: KnowledgeItem) -> None:
        embedding = await self.embedding_service.generate_and_store(item)
        self.vector_store.add(item, embedding)
        self.vector_store.save()
        logger.info(f"Indexed item {item.id}")

    async def rebuild_index(self) -> int:
        items = await self.knowledge_service.filter_without_embedding(limit=1000)

        if not items:
            logger.info("No items need indexing")
            return 0

        embeddings = await self.embedding_service.batch_generate_and_store(items)

        self.vector_store.add_batch(items, embeddings)
        self.vector_store.save()

        logger.info(f"Rebuilt index with {len(items)} items")
        return len(items)
