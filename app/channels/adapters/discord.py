from typing import Any

import httpx

from app.channels.adapter_base import IMAdapter
from app.channels.message import IMMessage, IMSendResult, MessageType
from app.utils.logging import logger


class DiscordAdapter(IMAdapter):
    def __init__(self, webhook_url: str) -> None:
        self.webhook_url = webhook_url

    @property
    def name(self) -> str:
        return "discord"

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

                if response.status_code == 204 or response.status_code == 200:
                    logger.info("Discord message sent successfully")
                    return IMSendResult(success=True)

                logger.error(f"Discord send failed: {response.status_code}")
                return IMSendResult(success=False, error=f"HTTP {response.status_code}")

        except Exception as e:
            logger.error(f"Discord send error: {e}")
            return IMSendResult(success=False, error=str(e))

    async def send_text(self, content: str) -> IMSendResult:
        return await self.send(IMMessage(content=content, msg_type=MessageType.TEXT))

    async def send_markdown(self, title: str, content: str) -> IMSendResult:
        full_content = f"**{title}**\n\n{content}"
        return await self.send(IMMessage(content=full_content, msg_type=MessageType.MARKDOWN))

    @staticmethod
    def _build_payload(message: IMMessage) -> dict[str, Any]:
        payload: dict[str, Any] = {"content": message.content}

        if message.msg_type == MessageType.MARKDOWN:
            payload["content"] = message.content

        if message.extra:
            if "username" in message.extra:
                payload["username"] = message.extra["username"]
            if "embeds" in message.extra:
                payload["embeds"] = message.extra["embeds"]

        return payload
