from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import JSONResponse

from app.api.http.deps.services import get_feishu_webhook_handler
from app.infrastructure.integrations.messaging.feishu_webhook import FeishuWebhookHandler

router = APIRouter(prefix="/integrations", tags=["integrations"])


@router.post("/feishu/events", summary="接收飞书事件订阅回调")
async def handle_feishu_events(
    request: Request,
    handler: Annotated[FeishuWebhookHandler, Depends(get_feishu_webhook_handler)],
) -> Response:
    headers = {key: value for key, value in request.headers.items()}
    body = await request.body()
    status_code, payload = await handler.handle(
        _FastAPIRawRequest(
            headers=headers,
            body=body,
            uri=str(request.url.path),
        )
    )
    return JSONResponse(status_code=status_code, content=payload)


class _FastAPIRawRequest:
    def __init__(
        self,
        *,
        headers: dict[str, str],
        body: bytes,
        uri: str,
    ) -> None:
        self.headers = headers
        self.body = body
        self.uri = uri
