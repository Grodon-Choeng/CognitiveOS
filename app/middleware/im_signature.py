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
        self.provider = settings.im_provider
        self.secret = settings.im_secret

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request = Request(scope)
        path = request.url.path

        if not self._is_webhook_path(path):
            await self.app(scope, receive, send)
            return

        if not settings.im_enabled or not self.secret:
            await self.app(scope, receive, send)
            return

        await self._verify_signature(request)

        await self.app(scope, receive, send)

    @staticmethod
    def _is_webhook_path(path: str) -> bool:
        return path in IM_WEBHOOK_PATHS

    async def _verify_signature(self, request: Request) -> None:
        if self.provider == IMProvider.DINGTALK:
            await self._verify_dingtalk(request)
        elif self.provider == IMProvider.FEISHU:
            await self._verify_feishu(request)
        elif self.provider in (IMProvider.WECOM, IMProvider.DISCORD):
            pass

    async def _verify_dingtalk(self, request: Request) -> None:
        timestamp = request.headers.get("timestamp", "")
        sign = request.headers.get("sign", "")

        if not timestamp or not sign:
            raise AuthenticationError("Missing DingTalk signature headers")

        current_time = int(time.time() * 1000)
        timestamp_int = int(timestamp)
        if abs(current_time - timestamp_int) > 3600000:
            raise AuthenticationError("DingTalk timestamp expired")

        string_to_sign = f"{timestamp}\n{self.secret}"
        hmac_code = hmac.new(
            self.secret.encode("utf-8"),
            string_to_sign.encode("utf-8"),
            digestmod=hashlib.sha256,
        ).digest()
        expected_sign = hmac_code.hex()

        if sign != expected_sign:
            raise AuthenticationError("Invalid DingTalk signature")

    async def _verify_feishu(self, request: Request) -> None:
        timestamp = request.headers.get("X-Lark-Request-Timestamp", "")
        nonce = request.headers.get("X-Lark-Request-Nonce", "")
        sign = request.headers.get("X-Lark-Signature", "")

        if not timestamp or not nonce or not sign:
            raise AuthenticationError("Missing Feishu signature headers")

        current_time = int(time.time())
        timestamp_int = int(timestamp)
        if abs(current_time - timestamp_int) > 3600:
            raise AuthenticationError("Feishu timestamp expired")

        string_to_sign = f"{timestamp}{nonce}{self.secret}"
        expected_sign = hashlib.sha1(string_to_sign.encode("utf-8")).hexdigest()

        if sign != expected_sign:
            raise AuthenticationError("Invalid Feishu signature")
