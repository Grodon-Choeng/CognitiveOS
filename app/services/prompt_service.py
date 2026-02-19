from app.models.prompt import Prompt
from app.repositories.prompt_repo import PromptRepository
from app.utils.logging import logger

DEFAULT_PROMPTS = {
    "rag_system": {
        "name": "rag_system",
        "description": "RAG system prompt for answering questions based on knowledge base",
        "content": """You are a helpful assistant with access to the user's knowledge base.
Use the provided context to answer the question. If the context doesn't contain relevant information, say so.
Always cite the source IDs when referencing specific information.""",
        "category": "rag",
    },
    "rag_user_template": {
        "name": "rag_user_template",
        "description": "RAG user message template, {context} and {query} are placeholders",
        "content": """Context from knowledge base:
{context}

Question: {query}

Please answer based on the context above.""",
        "category": "rag",
    },
}


class PromptService:
    def __init__(self, repo: PromptRepository) -> None:
        self._repo = repo
        self._cache: dict[str, Prompt] = {}

    async def get(self, name: str) -> str:
        prompt = await self._get_cached(name)
        if prompt:
            return prompt.content

        default = DEFAULT_PROMPTS.get(name)
        if default:
            logger.warning(f"Prompt '{name}' not found in DB, using default")
            return default["content"]

        raise ValueError(f"Prompt '{name}' not found")

    async def get_prompt(self, name: str) -> Prompt | None:
        return await self._get_cached(name)

    async def get_with_fallback(self, name: str) -> str:
        return await self.get(name)

    async def format(self, name: str, **kwargs) -> str:
        template = await self.get(name)
        return template.format(**kwargs)

    async def list(self, category: str | None = None) -> list[Prompt]:
        if category:
            return await self._repo.get_by_category(category)
        return await self._repo.list()

    async def create(
        self,
        name: str,
        content: str,
        description: str | None = None,
        category: str = "general",
    ) -> Prompt:
        prompt = await self._repo.create(
            name=name,
            content=content,
            description=description,
            category=category,
        )
        logger.info(f"Created prompt: {name}")
        return prompt

    async def update(
        self, name: str, content: str, description: str | None = None
    ) -> Prompt | None:
        prompt = await self._get_cached(name)
        if not prompt:
            return None

        await self._repo.update_by_id(
            prompt.id,
            content=content,
            description=description,
        )

        prompt.content = content
        prompt.description = description
        self._cache[name] = prompt

        logger.info(f"Updated prompt: {name}")
        return prompt

    async def delete(self, name: str) -> bool:
        prompt = await self._get_cached(name)
        if not prompt:
            return False

        await self._repo.delete_by_id(prompt.id)
        self._cache.pop(name, None)

        logger.info(f"Deleted prompt: {name}")
        return True

    async def _get_cached(self, name: str) -> Prompt | None:
        if name in self._cache:
            return self._cache[name]

        prompt = await self._repo.get_by_name(name)
        if prompt:
            self._cache[name] = prompt

        return prompt

    def clear_cache(self) -> None:
        self._cache.clear()
        logger.debug("Prompt cache cleared")

    async def seed_defaults(self) -> int:
        count = 0
        for name, data in DEFAULT_PROMPTS.items():
            existing = await self._repo.get_by_name(name)
            if not existing:
                await self._repo.create(**data)
                count += 1
                logger.info(f"Seeded prompt: {name}")

        return count
