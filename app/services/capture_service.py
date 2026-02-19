from datetime import datetime, timezone
from typing import TYPE_CHECKING
from uuid import UUID

from cashews import cache

from app.config import settings
from app.core.exceptions import StorageException
from app.utils.logging import logger

if TYPE_CHECKING:
    from app.services.knowledge_item_service import KnowledgeItemService


class CaptureService:
    def __init__(self, knowledge_service: "KnowledgeItemService") -> None:
        self.knowledge_service = knowledge_service

    async def capture(self, raw_text: str, source: str) -> UUID:
        try:
            item = await self.knowledge_service.create(raw_text=raw_text, source=source)

            await self._append_to_raw_markdown(raw_text, source)

            await self._invalidate_list_cache()

            return item.uuid
        except Exception as e:
            logger.error(f"Failed to capture item: {e}")
            raise StorageException("capture", str(e))

    async def _append_to_raw_markdown(self, raw_text: str, source: str) -> None:
        try:
            date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            folder = settings.raw_path
            folder.mkdir(parents=True, exist_ok=True)

            file_path = folder / f"{date}.md"
            timestamp = datetime.now(timezone.utc).strftime("%H:%M")

            entry = self._format_entry(raw_text, source, timestamp)

            with open(file_path, "a", encoding="utf-8") as f:
                f.write(entry)

            logger.debug(f"Appended to raw markdown: {file_path}")
        except Exception as e:
            logger.error(f"Failed to write markdown: {e}")
            raise StorageException("write_markdown", str(e))

    @staticmethod
    async def _invalidate_list_cache() -> None:
        await cache.delete_match("knowledge_item:recent:*")
        logger.debug("Invalidated list cache")

    @staticmethod
    def _format_entry(raw_text: str, source: str, timestamp: str) -> str:
        lines = [
            "",
            f"- [{timestamp}] [{source}] {raw_text}",
        ]
        return "\n".join(lines)
