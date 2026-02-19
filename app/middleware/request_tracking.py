import time
from uuid import uuid4

from litestar import Request
from litestar.middleware import AbstractMiddleware
from litestar.types import ASGIApp, Message, Receive, Scope, Send

from app.utils.logging import get_logger, set_request_id


class RequestTrackingMiddleware(AbstractMiddleware):
    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)
        self.logger = get_logger("request")

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request = Request(scope)
        request_id = request.headers.get("X-Request-ID", str(uuid4()))
        set_request_id(request_id)

        start_time = time.perf_counter()
        path = request.url.path
        method = request.method

        self.logger.info(f"--> {method} {path}")

        response_started = False
        status_code = 500

        async def send_wrapper(message: Message) -> None:
            nonlocal response_started, status_code
            if message["type"] == "http.response.start":
                response_started = True
                status_code = message["status"]
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
            duration_ms = (time.perf_counter() - start_time) * 1000
            self.logger.info(f"<-- {method} {path} {status_code} {duration_ms:.2f}ms")
        except Exception as e:
            duration_ms = (time.perf_counter() - start_time) * 1000
            self.logger.error(f"<-- {method} {path} 500 {duration_ms:.2f}ms - {e}")
            raise
