from uuid import UUID

from dishka import FromDishka
from dishka.integrations.litestar import inject
from litestar import get, post

from app.constants import RAW_TEXT_TRUNCATE_LENGTH
from app.enums import SortField, SortOrder
from app.schemas.common import CursorPaginationResponse
from app.schemas.webhook import (
    KnowledgeItemListResponse,
    KnowledgeItemResponse,
    StructuredResponse,
)
from app.services.knowledge_item_service import KnowledgeItemService
from app.services.structuring_service import StructuringService
from app.utils.jsons import parse_json_field


@post(
    "/items/{item_uuid:uuid}/structure",
    summary="生成结构化笔记",
    description="调用 LLM 对原始笔记进行结构化处理，生成 Markdown 文件并提取标题、标签、双链等元数据。",
    tags=["知识管理"],
)
@inject
async def structure_item(
    item_uuid: UUID,
    knowledge_service: FromDishka[KnowledgeItemService],
    structuring_service: FromDishka[StructuringService],
) -> StructuredResponse:
    item = await knowledge_service.get_by_uuid(item_uuid)
    output = await structuring_service.generate_markdown(item)

    return StructuredResponse(
        uuid=item.uuid,
        title=output.title,
        file_path=str(output.file_path) if output.file_path else None,
    )


@get(
    "/items/{item_uuid:uuid}",
    summary="获取知识项详情",
    description="根据 UUID 获取单个知识项的完整信息，包括原始文本、结构化文本、标签、双链等。",
    tags=["知识管理"],
)
@inject
async def get_item(
    item_uuid: UUID,
    knowledge_service: FromDishka[KnowledgeItemService],
) -> KnowledgeItemResponse:
    item = await knowledge_service.get_by_uuid(item_uuid)

    return KnowledgeItemResponse(
        uuid=item.uuid,
        raw_text=item.raw_text,
        structured_text=item.structured_text,
        source=item.source,
        tags=parse_json_field(item.tags),
        links=parse_json_field(item.links),
        created_at=item.created_at.isoformat() if item.created_at else "",
        updated_at=item.updated_at.isoformat() if item.updated_at else "",
    )


@get(
    "/items",
    summary="获取知识项列表",
    description="游标分页获取知识项列表。默认按创建时间倒序排列，raw_text 会被截断。",
    tags=["知识管理"],
)
@inject
async def list_items(
    knowledge_service: FromDishka[KnowledgeItemService],
    limit: int = 20,
    cursor: str | None = None,
    sort_field: str = "created_at",
    sort_order: str = "desc",
) -> CursorPaginationResponse[KnowledgeItemListResponse]:
    field = SortField.CREATED_AT if sort_field == "created_at" else SortField.UPDATED_AT
    order = SortOrder.DESC if sort_order == "desc" else SortOrder.ASC

    page = await knowledge_service.cursor_paginate(
        limit=limit,
        cursor=cursor,
        sort_field=field,
        sort_order=order,
    )

    items = [
        KnowledgeItemListResponse(
            uuid=item.uuid,
            raw_text=item.raw_text[:RAW_TEXT_TRUNCATE_LENGTH] + "..."
            if len(item.raw_text) > RAW_TEXT_TRUNCATE_LENGTH
            else item.raw_text,
            source=item.source,
            tags=parse_json_field(item.tags),
            created_at=item.created_at.isoformat() if item.created_at else "",
        )
        for item in page.items
    ]

    return CursorPaginationResponse(
        items=items,
        next_cursor=page.next_cursor,
        has_more=page.has_more,
    )
