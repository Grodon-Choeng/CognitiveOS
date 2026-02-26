import base64
import hashlib
import hmac
import time
from typing import Any

import httpx

from app.channels.adapter_base import IMAdapter
from app.channels.message import IMMessage, IMSendResult, MessageType
from app.utils.logging import logger


class FeishuAdapter(IMAdapter):
    def __init__(self, webhook_url: str, secret: str = "") -> None:
        self.webhook_url = webhook_url
        self.secret = secret

    @property
    def name(self) -> str:
        return "feishu"

    async def send(self, message: IMMessage) -> IMSendResult:
        payload = self._build_payload(message)

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    self.webhook_url,
                    json=payload,
                    timeout=10.0,
                )
                response.raise_for_status()

                result = response.json()

                if result.get("code") == 0 or result.get("StatusCode") == 0:
                    logger.info("Feishu message sent successfully")
                    return IMSendResult(success=True)

                error_msg = result.get("msg", "Unknown error")
                logger.error(f"Feishu send failed: {error_msg}")
                return IMSendResult(success=False, error=error_msg)

        except Exception as e:
            logger.error(f"Feishu send error: {e}")
            return IMSendResult(success=False, error=str(e))

    async def send_text(self, content: str) -> IMSendResult:
        return await self.send(IMMessage(content=content, msg_type=MessageType.TEXT))

    async def send_markdown(self, title: str, content: str) -> IMSendResult:
        full_content = f"**{title}**\n\n{content}"
        return await self.send(
            IMMessage(content=full_content, msg_type=MessageType.MARKDOWN, title=title)
        )

    def _build_payload(self, message: IMMessage) -> dict[str, Any]:
        if message.msg_type == MessageType.MARKDOWN:
            payload = {
                "msg_type": "post",
                "content": {
                    "post": {
                        "zh_cn": {
                            "title": message.title or "Notification",
                            "content": [
                                [
                                    {
                                        "tag": "text",
                                        "text": message.content,
                                    }
                                ]
                            ],
                        }
                    }
                },
            }
        else:
            payload = {
                "msg_type": "text",
                "content": {
                    "text": message.content,
                },
            }

        if self.secret:
            timestamp, sign = self._generate_sign()
            payload["timestamp"] = timestamp
            payload["sign"] = sign

        return payload

    def _generate_sign(self) -> tuple[str, str]:
        timestamp = str(int(time.time()))
        string_to_sign = f"{timestamp}\n{self.secret}"
        hmac_code = hmac.new(
            self.secret.encode("utf-8"),
            string_to_sign.encode("utf-8"),
            digestmod=hashlib.sha256,
        ).digest()
        sign = base64.b64encode(hmac_code).decode("utf-8")
        return timestamp, sign
