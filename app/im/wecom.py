from typing import Any

import httpx

from app.utils.logging import logger

from .base import IMAdapter, IMMessage, IMSendResult, MessageType


class WeComAdapter(IMAdapter):
    def __init__(self, webhook_url: str) -> None:
        self.webhook_url = webhook_url

    @property
    def name(self) -> str:
        return "wecom"

    async def send(self, message: IMMessage) -> IMSendResult:
        payload = self._build_payload(message)

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    self.webhook_url,
                    json=payload,
                    timeout=10.0,
                )

                result = response.json()

                if result.get("errcode") == 0:
                    logger.info("WeCom message sent successfully")
                    return IMSendResult(success=True)

                error_msg = result.get("errmsg", "Unknown error")
                logger.error(f"WeCom send failed: {error_msg}")
                return IMSendResult(success=False, error=error_msg)

        except Exception as e:
            logger.error(f"WeCom send error: {e}")
            return IMSendResult(success=False, error=str(e))

    async def send_text(self, content: str) -> IMSendResult:
        return await self.send(IMMessage(content=content, msg_type=MessageType.TEXT))

    async def send_markdown(self, title: str, content: str) -> IMSendResult:
        full_content = f"### {title}\n\n{content}"
        return await self.send(IMMessage(content=full_content, msg_type=MessageType.MARKDOWN))

    @staticmethod
    def _build_payload(message: IMMessage) -> dict[str, Any]:
        if message.msg_type == MessageType.MARKDOWN:
            return {
                "msgtype": "markdown",
                "markdown": {
                    "content": message.content,
                },
            }

        if message.msg_type == MessageType.CARD:
            return {
                "msgtype": "template_card",
                "template_card": message.extra or {},
            }

        return {
            "msgtype": "text",
            "text": {
                "content": message.content,
                "mentioned_list": message.extra.get("mentioned_list", []) if message.extra else [],
            },
        }
