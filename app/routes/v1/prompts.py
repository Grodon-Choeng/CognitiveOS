from dishka import FromDishka
from dishka.integrations.litestar import inject
from litestar import Controller, delete, get, post, put

from app.core.exceptions import NotFoundError
from app.schemas import (
    PromptCreateRequest,
    PromptDeleteResponse,
    PromptResponse,
    PromptUpdateRequest,
)
from app.services import PromptService


class PromptsController(Controller):
    path = "/prompts"
    tags = ["提示词管理"]

    @get(summary="获取提示词列表", description="列出所有提示词，支持按分类筛选。")
    @inject
    async def list(
        self,
        prompt_service: FromDishka[PromptService],
        category: str | None = None,
    ) -> list[PromptResponse]:
        prompts = await prompt_service.list(category)
        return [self._to_response(p) for p in prompts]

    @get(
        path="/{prompt_name:str}",
        summary="获取提示词详情",
        description="根据名称获取单个提示词的完整内容。",
    )
    @inject
    async def get(
        self,
        prompt_name: str,
        prompt_service: FromDishka[PromptService],
    ) -> PromptResponse:
        prompt = await prompt_service.get_prompt(prompt_name)
        if not prompt:
            raise NotFoundError("Prompt", prompt_name)
        return self._to_response(prompt)

    @post(summary="创建提示词", description="创建新的提示词。名称必须唯一。")
    @inject
    async def create(
        self,
        data: PromptCreateRequest,
        prompt_service: FromDishka[PromptService],
    ) -> PromptResponse:
        prompt = await prompt_service.create(
            name=data.name,
            content=data.content,
            description=data.description,
            category=data.category,
        )
        return self._to_response(prompt)

    @put(
        path="/{prompt_name:str}",
        summary="更新提示词",
        description="更新提示词内容和描述。修改后立即生效，无需重启服务。",
    )
    @inject
    async def update(
        self,
        prompt_name: str,
        data: PromptUpdateRequest,
        prompt_service: FromDishka[PromptService],
    ) -> PromptResponse:
        prompt = await prompt_service.update(
            name=prompt_name,
            content=data.content,
            description=data.description,
        )
        if not prompt:
            raise NotFoundError("Prompt", prompt_name)
        return self._to_response(prompt)

    @delete(
        path="/{prompt_name:str}",
        status_code=200,
        summary="删除提示词",
        description="删除指定名称的提示词。",
    )
    @inject
    async def delete(
        self,
        prompt_name: str,
        prompt_service: FromDishka[PromptService],
    ) -> PromptDeleteResponse:
        deleted = await prompt_service.delete(prompt_name)
        if not deleted:
            raise NotFoundError("Prompt", prompt_name)
        return PromptDeleteResponse(status="deleted", name=prompt_name)

    @staticmethod
    def _to_response(prompt) -> PromptResponse:
        return PromptResponse(
            id=prompt.id,
            name=prompt.name,
            description=prompt.description,
            content=prompt.content,
            category=prompt.category,
            created_at=prompt.created_at.isoformat() if prompt.created_at else "",
            updated_at=prompt.updated_at.isoformat() if prompt.updated_at else "",
        )
