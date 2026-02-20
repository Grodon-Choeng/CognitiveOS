from uuid import UUID

from dishka import FromDishka
from dishka.integrations.litestar import inject
from litestar import Controller, post

from app.schemas.im import IMNotifyResponse, IMTestResponse
from app.services.notification_service import NotificationService


class IMController(Controller):
    path = "/im"
    tags = ["IM 通知"]

    @post(
        path="/test",
        summary="测试 IM 通知",
        description="发送测试消息到配置的 IM 平台，验证通知功能是否正常。",
    )
    @inject
    async def test(self, notification_service: FromDishka[NotificationService]) -> IMTestResponse:
        result = await notification_service.send_text("Test message from CognitiveOS")
        return IMTestResponse(
            success=result.success,
            error=result.error,
        )

    @post(
        path="/notify/{item_uuid:uuid}",
        summary="发送知识项通知",
        description="发送知识项捕获成功的通知到 IM 平台。",
    )
    @inject
    async def notify(
        self,
        item_uuid: UUID,
        notification_service: FromDishka[NotificationService],
    ) -> IMNotifyResponse:
        result = await notification_service.notify_capture_success(
            uuid=str(item_uuid),
            content="Test notification",
        )
        return IMNotifyResponse(
            success=result.success,
            error=result.error,
        )
