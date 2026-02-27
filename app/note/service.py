from app.config import settings

from .base import NoteAdapter, NoteEntry, NoteType, TaskPriority
from .logseq import LogseqAdapter


def get_note_adapter() -> NoteAdapter:
    if settings.note_system == "logseq":
        return LogseqAdapter(
            base_path=settings.note_path,
            auto_git=settings.note_git_enabled,
        )
    else:
        return LogseqAdapter(
            base_path=settings.note_path,
            auto_git=settings.note_git_enabled,
        )


class NoteService:
    def __init__(self, adapter: NoteAdapter | None = None) -> None:
        self.adapter = adapter or get_note_adapter()

    async def write_reminder(self, content: str, remind_at, tags: list[str] | None = None) -> str:
        entry = NoteEntry(
            content=content,
            note_type=NoteType.REMINDER,
            tags=tags,
            remind_at=remind_at,
        )
        return await self.adapter.write_daily_entry(entry)

    async def write_idea(self, content: str, tags: list[str] | None = None) -> str:
        entry = NoteEntry(
            content=content,
            note_type=NoteType.IDEA,
            tags=tags,
        )
        return await self.adapter.write_daily_entry(entry)

    async def write_note(self, content: str, tags: list[str] | None = None) -> str:
        entry = NoteEntry(
            content=content,
            note_type=NoteType.NOTE,
            tags=tags,
        )
        return await self.adapter.write_daily_entry(entry)

    async def write_task(
        self,
        content: str,
        priority: TaskPriority = TaskPriority.LATER,
        tags: list[str] | None = None,
    ) -> str:
        entry = NoteEntry(
            content=content,
            note_type=NoteType.TASK,
            tags=tags,
            task_priority=priority,
        )
        return await self.adapter.write_daily_entry(entry)
