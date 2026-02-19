from litestar import Request
from litestar.middleware import AbstractMiddleware
from litestar.types import ASGIApp, Receive, Scope, Send

from app.config import settings
from app.core.exceptions import AuthenticationError

EXCLUDE_PATHS = {
    "/health",
    "/api/v1/health",
    "/schema",
    "/schema/openapi.json",
    "/schema/swagger",
    "/schema/elements",
    "/favicon.ico",
}


class APIKeyMiddleware(AbstractMiddleware):
    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)
        self.api_key = settings.api_key
        self.header_name = settings.api_key_header

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request = Request(scope)
        path = request.url.path

        if self._is_excluded_path(path):
            await self.app(scope, receive, send)
            return

        if not self.api_key:
            await self.app(scope, receive, send)
            return

        provided_key = request.headers.get(self.header_name)

        if not provided_key:
            raise AuthenticationError(f"Missing {self.header_name} header")

        if provided_key != self.api_key:
            raise AuthenticationError("Invalid API key")

        await self.app(scope, receive, send)

    def _is_excluded_path(self, path: str) -> bool:
        for exclude_path in EXCLUDE_PATHS:
            if path == exclude_path or path.startswith(exclude_path + "/"):
                return True
        return False
