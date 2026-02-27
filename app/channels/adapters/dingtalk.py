import base64
import hashlib
import hmac
import time
import urllib.parse
from typing import Any

import httpx

from app.utils import logger

from ..message import IMMessage, IMSendResult, MessageType
from .adapter_base import IMAdapter


class DingTalkAdapter(IMAdapter):
    def __init__(self, webhook_url: str, secret: str = "") -> None:
        self.webhook_url = webhook_url
        self.secret = secret

    @property
    def name(self) -> str:
        return "dingtalk"

    async def send(self, message: IMMessage) -> IMSendResult:
        payload = self._build_payload(message)
        url = self._build_signed_url()

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    url,
                    json=payload,
                    timeout=10.0,
                )
                response.raise_for_status()

                result = response.json()

                if result.get("errcode") == 0:
                    logger.info("DingTalk message sent successfully")
                    return IMSendResult(success=True)

                error_msg = result.get("errmsg", "Unknown error")
                logger.error(f"DingTalk send failed: {error_msg}")
                return IMSendResult(success=False, error=error_msg)

        except Exception as e:
            logger.error(f"DingTalk send error: {e}")
            return IMSendResult(success=False, error=str(e))

    async def send_text(self, content: str) -> IMSendResult:
        return await self.send(IMMessage(content=content, msg_type=MessageType.TEXT))

    async def send_markdown(self, title: str, content: str) -> IMSendResult:
        return await self.send(
            IMMessage(
                content=content,
                msg_type=MessageType.MARKDOWN,
                title=title,
            )
        )

    def _build_signed_url(self) -> str:
        if not self.secret:
            return self.webhook_url

        timestamp = str(round(time.time() * 1000))
        string_to_sign = f"{timestamp}\n{self.secret}"
        string_to_sign_enc = string_to_sign.encode("utf-8")
        secret_enc = self.secret.encode("utf-8")
        hmac_code = hmac.new(secret_enc, string_to_sign_enc, digestmod=hashlib.sha256).digest()
        sign = urllib.parse.quote_plus(base64.b64encode(hmac_code))

        return f"{self.webhook_url}&timestamp={timestamp}&sign={sign}"

    @staticmethod
    def _build_payload(message: IMMessage) -> dict[str, Any]:
        if message.msg_type == MessageType.MARKDOWN:
            return {
                "msgtype": "markdown",
                "markdown": {
                    "title": message.title or "Notification",
                    "text": message.content,
                },
            }

        return {
            "msgtype": "text",
            "text": {
                "content": message.content,
            },
        }
