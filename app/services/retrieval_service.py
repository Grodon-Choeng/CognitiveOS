from typing import TYPE_CHECKING, Any

from app.services.embedding_service import EmbeddingService
from app.services.knowledge_item_service import KnowledgeItemService
from app.services.llm_service import LLMService
from app.services.prompt_service import PromptService
from app.services.vector_store import VectorStore
from app.utils.logging import logger

if TYPE_CHECKING:
    from app.models.knowledge_item import KnowledgeItem


class RetrievalService:
    def __init__(
        self,
        llm_service: LLMService,
        embedding_service: EmbeddingService,
        knowledge_service: KnowledgeItemService,
        vector_store: VectorStore,
        prompt_service: PromptService,
    ) -> None:
        self.llm_service = llm_service
        self.embedding_service = embedding_service
        self.knowledge_service = knowledge_service
        self.vector_store = vector_store
        self.prompt_service = prompt_service

    async def search_similar(self, query: str, top_k: int = 5) -> list[dict[str, Any]]:
        query_embedding = await self.llm_service.get_embedding(query)
        results = self.vector_store.search(query_embedding, top_k)
        return results

    async def search_and_retrieve(
        self, query: str, top_k: int = 5
    ) -> list["KnowledgeItem"]:
        results = await self.search_similar(query, top_k)

        items = []
        for result in results:
            item = await self.knowledge_service.get_by_id(result["item_id"])
            items.append(item)

        logger.info(f"Retrieved {len(items)} items for query")
        return items

    async def rag_query(
        self, query: str, top_k: int = 5, max_context_tokens: int = 2000
    ) -> str:
        items = await self.search_and_retrieve(query, top_k)

        if not items:
            return "No relevant knowledge found."

        context = self._build_context(items, max_context_tokens)

        system_prompt = await self.prompt_service.get("rag_system")
        user_message = await self.prompt_service.format(
            "rag_user_template", context=context, query=query
        )

        response = await self.llm_service.chat_with_system(
            system_prompt, user_message, temperature=0.7
        )

        return response

    @staticmethod
    def _build_context(items: list["KnowledgeItem"], max_tokens: int) -> str:
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

    async def index_item(self, item: "KnowledgeItem") -> None:
        embedding = await self.embedding_service.generate_and_store(item)
        self.vector_store.add(item, embedding)
        self.vector_store.save()
        logger.info(f"Indexed item {item.id}")

    async def rebuild_index(self) -> int:
        items = await self.knowledge_service.get_recent(limit=1000)

        items_to_index = [item for item in items if not item.embedding]

        if not items_to_index:
            logger.info("No items need indexing")
            return 0

        embeddings = await self.embedding_service.batch_generate_and_store(
            items_to_index
        )

        self.vector_store.add_batch(items_to_index, embeddings)
        self.vector_store.save()

        logger.info(f"Rebuilt index with {len(items_to_index)} items")
        return len(items_to_index)
