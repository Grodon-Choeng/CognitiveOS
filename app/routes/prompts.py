from dataclasses import dataclass

from litestar import get, post, put, delete
from dishka import FromDishka
from dishka.integrations.litestar import inject

from app.models.prompt import Prompt
from app.services.prompt_service import PromptService


@dataclass
class PromptResponse:
    id: int
    name: str
    description: str | None
    content: str
    category: str
    created_at: str
    updated_at: str


@dataclass
class PromptCreateRequest:
    name: str
    content: str
    description: str | None = None
    category: str = "general"


@dataclass
class PromptUpdateRequest:
    content: str
    description: str | None = None


def _to_response(prompt: Prompt) -> PromptResponse:
    return PromptResponse(
        id=prompt.id,
        name=prompt.name,
        description=prompt.description,
        content=prompt.content,
        category=prompt.category,
        created_at=prompt.created_at.isoformat() if prompt.created_at else "",
        updated_at=prompt.updated_at.isoformat() if prompt.updated_at else "",
    )


@get("/prompts")
@inject
async def list_prompts(
    prompt_service: FromDishka[PromptService],
    category: str | None = None,
) -> list[PromptResponse]:
    prompts = (
        await prompt_service.repo.get_by_category(category)
        if category
        else await prompt_service.repo.list()
    )
    return [_to_response(p) for p in prompts]


@get("/prompts/{prompt_name:str}")
@inject
async def get_prompt(
    prompt_name: str,
    prompt_service: FromDishka[PromptService],
) -> PromptResponse:
    prompt = await prompt_service.get_prompt(prompt_name)
    if not prompt:
        from app.core.exceptions import NotFoundException

        raise NotFoundException("Prompt", prompt_name)
    return _to_response(prompt)


@post("/prompts")
@inject
async def create_prompt(
    data: PromptCreateRequest,
    prompt_service: FromDishka[PromptService],
) -> PromptResponse:
    prompt = await prompt_service.repo.create(
        name=data.name,
        content=data.content,
        description=data.description,
        category=data.category,
    )
    return _to_response(prompt)


@put("/prompts/{prompt_name:str}")
@inject
async def update_prompt(
    prompt_name: str,
    data: PromptUpdateRequest,
    prompt_service: FromDishka[PromptService],
) -> PromptResponse:
    prompt = await prompt_service.get_prompt(prompt_name)
    if not prompt:
        from app.core.exceptions import NotFoundException

        raise NotFoundException("Prompt", prompt_name)

    await prompt_service.repo.update_by_id(
        prompt.id,
        content=data.content,
        description=data.description,
    )

    prompt.content = data.content
    prompt.description = data.description
    prompt_service.clear_cache()

    return _to_response(prompt)


@delete("/prompts/{prompt_name:str}", status_code=200)
@inject
async def delete_prompt(
    prompt_name: str,
    prompt_service: FromDishka[PromptService],
) -> dict:
    prompt = await prompt_service.get_prompt(prompt_name)
    if not prompt:
        from app.core.exceptions import NotFoundException

        raise NotFoundException("Prompt", prompt_name)

    await prompt_service.repo.delete_by_id(prompt.id)
    prompt_service.clear_cache()

    return {"status": "deleted", "name": prompt_name}
