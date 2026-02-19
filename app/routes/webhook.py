from litestar import post
from dishka import FromDishka
from dishka.integrations.litestar import inject

from app.schemas.webhook import CaptureRequest, CaptureResponse
from app.services.capture_service import CaptureService


@post(
    "/webhook",
    summary="捕获笔记",
    description="接收并保存原始笔记内容，自动记录到数据库和 Markdown 文件。不调用 LLM，确保数据完整保存。",
    tags=["知识管理"],
)
@inject
async def webhook(
    data: CaptureRequest, capture_service: FromDishka[CaptureService]
) -> CaptureResponse:
    item_uuid = await capture_service.capture(data.content, data.source)
    return CaptureResponse(uuid=item_uuid)
