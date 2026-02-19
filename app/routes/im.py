from uuid import UUID

from litestar import post
from dishka import FromDishka
from dishka.integrations.litestar import inject

from app.services.notification_service import NotificationService


@post("/im/test")
@inject
async def test_im(
    notification_service: FromDishka[NotificationService],
) -> dict:
    result = await notification_service.send_text("Test message from CognitiveOS")
    return {
        "success": result.success,
        "error": result.error,
    }


@post("/im/notify/{item_uuid:uuid}")
@inject
async def notify_item(
    item_uuid: UUID,
    notification_service: FromDishka[NotificationService],
) -> dict:
    result = await notification_service.notify_capture_success(
        uuid=str(item_uuid),
        content="Test notification",
    )
    return {
        "success": result.success,
        "error": result.error,
    }
