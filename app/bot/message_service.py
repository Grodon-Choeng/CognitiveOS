from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from app.config import settings
from app.note import NoteService
from app.services.cognitive_agent_service import CognitiveAgentService
from app.services.llm_service import LLMService
from app.utils import logger


@dataclass
class IncomingMessage:
    provider: str
    user_id: str
    text: str
    reply: Callable[[str], Awaitable[None]]
    channel_id: int | None = None


class BotMessageService:
    def __init__(
        self,
        agent_service: CognitiveAgentService | None = None,
        llm_service: LLMService | None = None,
    ) -> None:
        self.llm_service = llm_service or LLMService()
        if agent_service is not None:
            self.agent_service = agent_service
        else:
            self.agent_service = CognitiveAgentService(note_service=NoteService())

    async def handle(self, message: IncomingMessage) -> None:
        text = message.text.strip()
        if not text:
            return

        logger.info(f"[{message.provider}] {message.user_id}: {text}")

        agent_outcome = await self.agent_service.run(
            user_id=message.user_id,
            provider=message.provider,
            text=text,
            channel_id=message.channel_id,
        )
        if agent_outcome.success and agent_outcome.response:
            await self._reply(message, agent_outcome.response, user_text=text)

    async def _reply(self, message: IncomingMessage, text: str, *, user_text: str = "") -> None:
        content = text.strip()
        if not content:
            return
        if message.provider == "feishu":
            content = await self._render_feishu_reply(user_text=user_text, draft_reply=content)
        await message.reply(content)

    async def _render_feishu_reply(self, user_text: str, draft_reply: str) -> str:
        system_prompt = (
            "你是一个中文助手。请基于给定事实草稿生成最终回复。"
            "要求：1) 只能使用草稿中的事实，不得新增事实；"
            "2) 语气自然简洁；3) 保留时间、数字、列表项；"
            "4) 不要输出额外说明；5) 仅输出纯文本，禁止 markdown（如 **、#、-、```）。"
        )
        user_prompt = (
            f"用户原话：{user_text or '（无）'}\n事实草稿：{draft_reply}\n请输出最终回复："
        )
        try:
            return (
                await self.llm_service.chat_with_system(
                    system_prompt=system_prompt,
                    user_message=user_prompt,
                    temperature=0.3,
                    model=settings.intent_model.strip() or settings.llm_model,
                    base_url=settings.intent_base_url or settings.llm_base_url or None,
                    api_key=settings.intent_api_key or settings.llm_api_key or None,
                )
            ).strip()
        except Exception as e:
            logger.warning(f"Feishu reply LLM fallback: {e}")
            return draft_reply
