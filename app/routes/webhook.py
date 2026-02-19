from litestar import post
from dishka import FromDishka
from dishka.integrations.litestar import inject

from app.schemas.webhook import CaptureRequest, CaptureResponse
from app.services.capture_service import CaptureService


@post("/webhook")
@inject
async def webhook(
    data: CaptureRequest, capture_service: FromDishka[CaptureService]
) -> CaptureResponse:
    item_uuid = await capture_service.capture(data.content, data.source)
    return CaptureResponse(uuid=item_uuid)
