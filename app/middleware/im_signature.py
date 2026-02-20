import hashlib
import hmac
import time

from litestar import Request
from litestar.middleware import AbstractMiddleware
from litestar.types import ASGIApp, Receive, Scope, Send

from app.config import settings
from app.core.exceptions import AuthenticationError
from app.enums import IMProvider

IM_WEBHOOK_PATHS = {
    "/webhook",
    "/api/v1/webhook",
}


class IMSignatureMiddleware(AbstractMiddleware):
    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request = Request(scope)
        path = request.url.path

        if not self._is_webhook_path(path):
            await self.app(scope, receive, send)
            return

        if not settings.im_enabled:
            await self.app(scope, receive, send)
            return

        provider = self._detect_provider(request)
        if provider:
            config = settings.get_im_config(provider)
            if config and config.secret:
                await self._verify_signature(request, provider, config.secret)

        await self.app(scope, receive, send)

    @staticmethod
    def _is_webhook_path(path: str) -> bool:
        return path in IM_WEBHOOK_PATHS

    @staticmethod
    def _detect_provider(request: Request) -> IMProvider | None:
        user_agent = request.headers.get("User-Agent", "").lower()

        if "dingtalk" in user_agent:
            return IMProvider.DINGTALK
        if "feishu" in user_agent or "lark" in user_agent:
            return IMProvider.FEISHU
        if "wecom" in user_agent or "wxwork" in user_agent:
            return IMProvider.WECOM
        if "discord" in user_agent:
            return IMProvider.DISCORD
        if "telegram" in user_agent:
            return IMProvider.TELEGRAM
        if "slack" in user_agent:
            return IMProvider.SLACK

        provider_header = request.headers.get("X-IM-Provider", "")
        if provider_header:
            try:
                return IMProvider(provider_header.lower())
            except ValueError:
                pass

        return None

    async def _verify_signature(self, request: Request, provider: IMProvider, secret: str) -> None:
        if provider == IMProvider.DINGTALK:
            await self._verify_dingtalk(request, secret)
        elif provider == IMProvider.FEISHU:
            await self._verify_feishu(request, secret)

    @staticmethod
    async def _verify_dingtalk(request: Request, secret: str) -> None:
        timestamp = request.headers.get("timestamp", "")
        sign = request.headers.get("sign", "")

        if not timestamp or not sign:
            raise AuthenticationError("Missing DingTalk signature headers")

        current_time = int(time.time() * 1000)
        timestamp_int = int(timestamp)
        if abs(current_time - timestamp_int) > 3600000:
            raise AuthenticationError("DingTalk timestamp expired")

        string_to_sign = f"{timestamp}\n{secret}"
        hmac_code = hmac.new(
            secret.encode("utf-8"),
            string_to_sign.encode("utf-8"),
            digestmod=hashlib.sha256,
        ).digest()
        expected_sign = hmac_code.hex()

        if sign != expected_sign:
            raise AuthenticationError("Invalid DingTalk signature")

    @staticmethod
    async def _verify_feishu(request: Request, secret: str) -> None:
        timestamp = request.headers.get("X-Lark-Request-Timestamp", "")
        nonce = request.headers.get("X-Lark-Request-Nonce", "")
        sign = request.headers.get("X-Lark-Signature", "")

        if not timestamp or not nonce or not sign:
            raise AuthenticationError("Missing Feishu signature headers")

        current_time = int(time.time())
        timestamp_int = int(timestamp)
        if abs(current_time - timestamp_int) > 3600:
            raise AuthenticationError("Feishu timestamp expired")

        string_to_sign = f"{timestamp}{nonce}{secret}"
        expected_sign = hashlib.sha1(string_to_sign.encode("utf-8")).hexdigest()

        if sign != expected_sign:
            raise AuthenticationError("Invalid Feishu signature")
