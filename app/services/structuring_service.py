import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from app.config import settings
from app.core.exceptions import StorageError
from app.models.knowledge_item import KnowledgeItem
from app.utils.jsons import parse_json_field
from app.utils.logging import logger


@dataclass
class StructuredOutput:
    title: str
    content: str
    file_path: Path | None


class StructuringService:
    def __init__(self, debug_mode: bool = False) -> None:
        self.debug_mode = debug_mode
        self.output_dir = settings.structured_path
        self.output_dir.mkdir(parents=True, exist_ok=True)

    async def generate_markdown(self, item: KnowledgeItem) -> StructuredOutput:
        title = self._generate_title(item)
        content = self._build_content(item, title)

        file_path = None
        if not self.debug_mode:
            file_path = self.output_dir / f"{item.id}-{self._slugify(title)}.md"

            try:
                with open(file_path, "w", encoding="utf-8") as f:
                    f.write(content)
                logger.info(f"Generated structured markdown: {file_path}")
            except Exception as e:
                logger.error(f"Failed to generate markdown: {e}")
                raise StorageError("generate_markdown", str(e)) from e
        else:
            logger.debug(f"Debug mode: skipping file write for item {item.uuid}")

        return StructuredOutput(title=title, content=content, file_path=file_path)

    async def update_markdown(self, item: KnowledgeItem) -> StructuredOutput:
        return await self.generate_markdown(item)

    async def delete_markdown(self, item_id: int) -> bool:
        if self.debug_mode:
            logger.debug(f"Debug mode: skipping file deletion for item {item_id}")
            return True

        pattern = f"{item_id}-*.md"
        for file_path in self.output_dir.glob(pattern):
            file_path.unlink()
            logger.info(f"Deleted structured markdown: {file_path}")
            return True
        return False

    @staticmethod
    def _generate_title(item: KnowledgeItem) -> str:
        if item.structured_text:
            first_line = item.structured_text.split("\n")[0]
            return first_line[:50] if len(first_line) > 50 else first_line

        raw_first_line = item.raw_text.split("\n")[0]
        return raw_first_line[:50] if len(raw_first_line) > 50 else raw_first_line

    @staticmethod
    def _slugify(text: str) -> str:
        slug = re.sub(r"[^\w\s-]", "", text.lower())
        slug = re.sub(r"[\s_-]+", "-", slug)
        return slug.strip("-")[:30]

    def _build_content(self, item: KnowledgeItem, title: str) -> str:
        lines = [
            f"# {title}",
            "",
            f"> UUID: {item.uuid}",
            f"> Created: {self._format_datetime(item.created_at)}",
            f"> Source: {item.source}",
            "",
        ]

        tags = parse_json_field(item.tags)
        if tags:
            tags_str = " ".join(f"#{tag}" for tag in tags)
            lines.extend(["## Tags", "", tags_str, ""])

        links = parse_json_field(item.links)
        if links:
            links_str = " ".join(f"[[{link}]]" for link in links)
            lines.extend(["## Links", "", links_str, ""])

        lines.extend(["## Content", ""])

        if item.structured_text:
            lines.append(item.structured_text)
        else:
            lines.append(item.raw_text)

        lines.append("")

        return "\n".join(lines)

    @staticmethod
    def _format_datetime(dt: datetime) -> str:
        if dt:
            return dt.strftime("%Y-%m-%d %H:%M")
        return "Unknown"
