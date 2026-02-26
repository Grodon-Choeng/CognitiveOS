from app.models.prompt_template import PromptTemplate
from app.repositories.prompt_template_repo import PromptTemplateRepository
from app.utils.logging import logger

DEFAULT_PROMPT_TEMPLATES = {
    "memory_rag": {
        "name": "memory_rag",
        "version": 1,
        "system_prompt": (
            "You are CognitiveOS assistant. Use memory context as the primary source. "
            "If context is insufficient, state uncertainty clearly and avoid fabrication."
        ),
        "user_prompt_template": (
            "Long-term memory context:\n{memory_context}\n\n"
            "Knowledge base context:\n{knowledge_context}\n\n"
            "User question:\n{query}\n\n"
            "Respond in Chinese by default and cite memory IDs / knowledge IDs when applicable."
        ),
        "is_active": True,
        "category": "memory",
    }
}


class PromptTemplateService:
    def __init__(self, repo: PromptTemplateRepository) -> None:
        self._repo = repo

    async def get_active(self, name: str) -> PromptTemplate | None:
        return await self._repo.get_active_by_name(name)

    async def render(self, name: str, **kwargs: str) -> tuple[str, str]:
        template = await self.get_active(name)
        if template:
            return template.system_prompt, template.user_prompt_template.format(**kwargs)

        default = DEFAULT_PROMPT_TEMPLATES.get(name)
        if not default:
            raise ValueError(f"Prompt template '{name}' not found")

        logger.warning(f"Prompt template '{name}' missing in DB, using default")
        return default["system_prompt"], default["user_prompt_template"].format(**kwargs)

    async def seed_defaults(self) -> int:
        created = 0
        for name, payload in DEFAULT_PROMPT_TEMPLATES.items():
            existing = await self._repo.get_active_by_name(name)
            if existing:
                continue
            await self._repo.create(**payload)
            created += 1
        if created:
            logger.info(f"Seeded {created} prompt templates")
        return created
