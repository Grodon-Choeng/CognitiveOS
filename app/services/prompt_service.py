from cashews import cache

from app.config import settings
from app.core.service import BaseService
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


class PromptService(BaseService[Prompt, PromptRepository]):
    cache_prefix = "prompt"
    cache_ttl = settings.cache_prompt_ttl

    def __init__(self, repo: PromptRepository) -> None:
        super().__init__(repo)

    def _cache_key_by_name(self, name: str) -> str:
        return self._cache_key("name", name)

    async def get(self, name: str) -> str:
        prompt = await self.get_prompt(name)
        if prompt:
            return prompt.content

        default = DEFAULT_PROMPTS.get(name)
        if default:
            logger.warning(f"Prompt '{name}' not found in DB, using default")
            return default["content"]

        raise ValueError(f"Prompt '{name}' not found")

    async def get_prompt(self, name: str) -> Prompt | None:
        key = self._cache_key_by_name(name)
        cached = await self._get_cached(Prompt, key)
        if cached is not None:
            return cached

        prompt = await self._repo.get_by_name(name)
        if prompt:
            await self._set_cached(prompt, key)

        return prompt

    async def get_with_fallback(self, name: str) -> str:
        return await self.get(name)

    async def format(self, name: str, **kwargs) -> str:
        template = await self.get(name)
        return template.format(**kwargs)

    async def list(self, category: str | None = None) -> list[Prompt]:
        list_key = self._cache_key_list(category or "all")

        cached_names = await cache.get(list_key)
        if cached_names is not None:
            logger.debug(f"Cache hit for prompt list: {list_key}")
            prompts = []
            for prompt_name in cached_names:
                prompt = await self._get_cached(Prompt, self._cache_key_by_name(prompt_name))
                if prompt:
                    prompts.append(prompt)
            return prompts

        if category:
            prompts = await self._repo.get_by_category(category)
        else:
            prompts = await self._repo.list()

        prompt_names = [p.name for p in prompts]
        await cache.set(list_key, prompt_names, expire=self.cache_ttl)

        for prompt in prompts:
            await self._set_cached(prompt, self._cache_key_by_name(prompt.name))

        logger.debug(f"Cache miss for prompt list: {list_key}")
        return prompts

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

        await self._set_cached(prompt, self._cache_key_by_name(name))
        await self._invalidate_list_cache()

        logger.info(f"Created prompt: {name}")
        return prompt

    async def update(
        self, name: str, content: str, description: str | None = None
    ) -> Prompt | None:
        prompt = await self.get_prompt(name)
        if not prompt:
            return None

        await self._repo.update_by_id(
            prompt.id,
            content=content,
            description=description,
        )

        prompt.content = content
        prompt.description = description

        await self._set_cached(prompt, self._cache_key_by_name(name))
        await self._invalidate_list_cache()

        logger.info(f"Updated prompt: {name}")
        return prompt

    async def delete(self, name: str) -> bool:
        prompt = await self.get_prompt(name)
        if not prompt:
            return False

        await self._repo.delete_by_id(prompt.id)

        await self._delete_cached(self._cache_key_by_name(name))
        await self._invalidate_list_cache()

        logger.info(f"Deleted prompt: {name}")
        return True

    async def seed_defaults(self) -> int:
        count = 0
        for name, data in DEFAULT_PROMPTS.items():
            existing = await self._repo.get_by_name(name)
            if not existing:
                prompt = await self._repo.create(**data)
                await self._set_cached(prompt, self._cache_key_by_name(name))
                count += 1
                logger.info(f"Seeded prompt: {name}")

        if count > 0:
            await self._invalidate_list_cache()

        return count
