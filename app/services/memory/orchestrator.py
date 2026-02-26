from dataclasses import dataclass

from app.models.knowledge_item import KnowledgeItem
from app.services.memory.embedder import MemoryEmbedder
from app.services.memory.retriever import MemoryRetriever
from app.services.memory.writer import MemoryWriter
from app.services.prompt_template_service import PromptTemplateService


@dataclass
class ContextBundle:
    system_prompt: str
    user_prompt: str
    memory_context: str


class MemoryOrchestrator:
    def __init__(
        self,
        embedder: MemoryEmbedder,
        retriever: MemoryRetriever,
        writer: MemoryWriter,
        prompt_template_service: PromptTemplateService,
    ) -> None:
        self._embedder = embedder
        self._retriever = retriever
        self._writer = writer
        self._prompt_template_service = prompt_template_service

    @staticmethod
    def _build_knowledge_context(items: list[KnowledgeItem], max_tokens: int = 1200) -> str:
        parts: list[str] = []
        token_count = 0

        for item in items:
            text = item.structured_text or item.raw_text
            line = f"[knowledge_id={item.id}] {text}"
            estimate = len(line) // 4
            if token_count + estimate > max_tokens:
                break
            parts.append(line)
            token_count += estimate

        return "\n".join(parts)

    async def build_context(
        self,
        user_id: str,
        query: str,
        knowledge_items: list[KnowledgeItem],
        *,
        top_k: int = 8,
    ) -> ContextBundle:
        query_embedding = await self._embedder.embed(query)
        hits = await self._retriever.search(
            user_id=user_id, query_embedding=query_embedding, top_k=top_k
        )
        memory_context = self._retriever.build_context(hits)
        knowledge_context = self._build_knowledge_context(knowledge_items)

        system_prompt, user_prompt = await self._prompt_template_service.render(
            "memory_rag",
            memory_context=memory_context or "(empty)",
            knowledge_context=knowledge_context or "(empty)",
            query=query,
        )

        return ContextBundle(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            memory_context=memory_context,
        )

    async def write_back(self, user_id: str, query: str, response: str) -> None:
        await self._writer.write(
            user_id=user_id,
            content=f"Q: {query}\nA: {response}",
            memory_type="conversation",
            importance=2,
        )
