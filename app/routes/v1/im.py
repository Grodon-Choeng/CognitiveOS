from uuid import UUID

from dishka import FromDishka
from dishka.integrations.litestar import inject
from litestar import Controller, get, post

from app.channels import IMMessage, MessageType
from app.enums import IMProvider
from app.schemas import (
    IMNotifyResponse,
    IMProviderInfo,
    IMProvidersResponse,
    IMTestResponse,
    SetUserChannelRequest,
    SetUserChannelResponse,
)
from app.services import NotificationService

PROVIDER_NAMES = {
    IMProvider.WECOM: "企业微信",
    IMProvider.DINGTALK: "钉钉",
    IMProvider.FEISHU: "飞书",
    IMProvider.DISCORD: "Discord",
    IMProvider.TELEGRAM: "Telegram",
    IMProvider.SLACK: "Slack",
}


class IMController(Controller):
    path = "/im"
    tags = ["IM 通知"]

    @get(
        path="/providers",
        summary="获取可用 IM 平台",
        description="列出所有已配置且启用的 IM 平台。",
    )
    @inject
    async def providers(
        self,
        notification_service: FromDishka[NotificationService],
    ) -> IMProvidersResponse:
        available = notification_service.get_available_providers()
        providers = [
            IMProviderInfo(
                provider=p.value,
                name=PROVIDER_NAMES.get(p, p.value),
                enabled=True,
            )
            for p in available
        ]
        return IMProvidersResponse(providers=providers)

    @post(
        path="/test",
        summary="测试 IM 通知",
        description="发送测试消息到默认 IM 平台，验证通知功能是否正常。",
    )
    @inject
    async def test(
        self,
        notification_service: FromDishka[NotificationService],
        provider: str | None = None,
    ) -> IMTestResponse:
        if not notification_service.manager:
            return IMTestResponse(
                success=False,
                error="IM service not configured",
                provider=provider or "none",
            )

        target_provider = IMProvider(provider) if provider else None

        if target_provider:
            message = IMMessage(content="Test message from CognitiveOS", msg_type=MessageType.TEXT)
            result = await notification_service.manager.send_to_provider(target_provider, message)
        else:
            result = await notification_service.send_text("Test message from CognitiveOS")

        return IMTestResponse(
            success=result.success,
            error=result.error,
            provider=provider or "default",
        )

    @post(
        path="/test-all",
        summary="测试所有 IM 平台",
        description="向所有已配置的 IM 平台发送测试消息。",
    )
    @inject
    async def test_all(
        self,
        notification_service: FromDishka[NotificationService],
    ) -> list[IMTestResponse]:
        message = IMMessage(content="Test message from CognitiveOS", msg_type=MessageType.TEXT)
        results = await notification_service.send_to_all(message)

        providers = notification_service.get_available_providers()
        return [
            IMTestResponse(
                success=r.success,
                error=r.error,
                provider=providers[i].value if i < len(providers) else "unknown",
            )
            for i, r in enumerate(results)
        ]

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
        user_id: str | None = None,
    ) -> IMNotifyResponse:
        result = await notification_service.notify_capture_success(
            uuid=str(item_uuid),
            content="Test notification",
            user_id=user_id,
        )

        provider = await notification_service.get_user_channel(user_id) if user_id else None

        return IMNotifyResponse(
            success=result.success,
            error=result.error,
            provider=provider.value if provider else "default",
        )

    @post(
        path="/channel",
        summary="设置用户 IM 渠道",
        description="设置用户最后一次使用的 IM 渠道，后续通知将发送到该渠道。",
    )
    @inject
    async def set_channel(
        self,
        data: SetUserChannelRequest,
        notification_service: FromDishka[NotificationService],
        user_id: str = "default",
    ) -> SetUserChannelResponse:
        await notification_service.set_user_channel(user_id, data.provider)
        return SetUserChannelResponse(
            success=True,
            provider=data.provider.value,
        )

    @get(
        path="/channel",
        summary="获取用户 IM 渠道",
        description="获取用户当前设置的 IM 渠道。",
    )
    @inject
    async def get_channel(
        self,
        notification_service: FromDishka[NotificationService],
        user_id: str = "default",
    ) -> SetUserChannelResponse:
        provider = await notification_service.get_user_channel(user_id)
        return SetUserChannelResponse(
            success=provider is not None,
            provider=provider.value if provider else "none",
        )
