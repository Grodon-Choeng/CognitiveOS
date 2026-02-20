import asyncio
import subprocess
from datetime import datetime
from pathlib import Path

from app.note.base import NoteAdapter, NoteEntry, NoteType
from app.utils.logging import logger


class LogseqAdapter(NoteAdapter):
    def __init__(self, base_path: str | Path = "storage/logseq", auto_git: bool = True) -> None:
        self.base_path = Path(base_path)
        self.journals_path = self.base_path / "journals"
        self.auto_git = auto_git
        self._ensure_directories()

    def _ensure_directories(self) -> None:
        self.journals_path.mkdir(parents=True, exist_ok=True)
        logger.info(f"Logseq journals path: {self.journals_path}")

    def _run_git_command(self, *args: str) -> subprocess.CompletedProcess:
        result = subprocess.run(
            ["git"] + list(args),
            cwd=str(self.base_path),
            capture_output=True,
            text=True,
        )
        return result

    async def git_pull(self) -> bool:
        if not self.auto_git:
            return True

        try:
            result = await asyncio.to_thread(self._run_git_command, "pull", "--rebase")
            if result.returncode == 0:
                logger.info("Git pull successful")
                return True
            else:
                logger.warning(f"Git pull failed: {result.stderr}")
                return False
        except Exception as e:
            logger.error(f"Git pull error: {e}")
            return False

    async def git_commit(self, message: str) -> bool:
        if not self.auto_git:
            return True

        try:
            await asyncio.to_thread(self._run_git_command, "add", "-A")
            result = await asyncio.to_thread(self._run_git_command, "commit", "-m", message)
            if result.returncode == 0:
                logger.info(f"Git commit: {message}")
                return True
            elif "nothing to commit" in result.stdout:
                logger.debug("Nothing to commit")
                return True
            else:
                logger.warning(f"Git commit failed: {result.stderr}")
                return False
        except Exception as e:
            logger.error(f"Git commit error: {e}")
            return False

    async def git_push(self) -> bool:
        if not self.auto_git:
            return True

        try:
            result = await asyncio.to_thread(self._run_git_command, "push")
            if result.returncode == 0:
                logger.info("Git push successful")
                return True
            else:
                logger.warning(f"Git push failed: {result.stderr}")
                return False
        except Exception as e:
            logger.error(f"Git push error: {e}")
            return False

    async def git_sync_and_commit(self, message: str) -> bool:
        await self.git_pull()
        success = await self.git_commit(message)
        if success:
            await self.git_push()
        return success

    @property
    def name(self) -> str:
        return "logseq"

    @property
    def file_extension(self) -> str:
        return ".md"

    async def get_daily_path(self, date: datetime | None = None) -> str:
        target_date = date or datetime.now()
        filename = target_date.strftime("%Y_%m_%d") + self.file_extension
        return str(self.journals_path / filename)

    def format_entry(self, entry: NoteEntry) -> str:
        timestamp = entry.created_at.strftime("%H:%M")

        if entry.note_type == NoteType.REMINDER:
            remind_str = entry.remind_at.strftime("%Y-%m-%d %H:%M") if entry.remind_at else ""
            tags_str = " ".join(f"#{tag}" for tag in entry.tags) if entry.tags else ""
            return f"- {timestamp} ⏰ **提醒** {entry.content} {tags_str}\n  - 提醒时间: {remind_str}\n"

        elif entry.note_type == NoteType.IDEA:
            tags_str = " ".join(f"#{tag}" for tag in entry.tags) if entry.tags else ""
            return f"- {timestamp} 💡 **灵感** {entry.content} {tags_str}\n"

        elif entry.note_type == NoteType.TASK:
            tags_str = " ".join(f"#{tag}" for tag in entry.tags) if entry.tags else ""
            priority = entry.task_priority.value
            return f"- {priority} {timestamp} {entry.content} {tags_str}\n"

        else:
            tags_str = " ".join(f"#{tag}" for tag in entry.tags) if entry.tags else ""
            return f"- {timestamp} {entry.content} {tags_str}\n"

    @staticmethod
    async def _write_file(path: Path, content: str, mode: str = "a") -> None:
        def _write():
            with open(path, mode, encoding="utf-8") as f:
                f.write(content)

        await asyncio.to_thread(_write)

    async def write_daily_entry(self, entry: NoteEntry) -> str:
        await self.git_pull()

        file_path = await self.get_daily_path(entry.created_at)
        path = Path(file_path)

        formatted = self.format_entry(entry)

        if path.exists():
            await self._write_file(path, "\n" + formatted)
        else:
            date_header = entry.created_at.strftime("%Y-%m-%d")
            content = f"# {date_header}\n\n{formatted}"
            await self._write_file(path, content, mode="w")

        logger.info(f"Wrote entry to {file_path}: {entry.content[:50]}...")

        commit_message = f"Add {entry.note_type.value}: {entry.content[:30]}"
        await self.git_sync_and_commit(commit_message)

        return file_path

    async def append_to_journal(self, date: datetime, content: str) -> str:
        await self.git_pull()

        file_path = await self.get_daily_path(date)
        path = Path(file_path)

        if path.exists():
            await self._write_file(path, "\n" + content)
        else:
            date_header = date.strftime("%Y-%m-%d")
            full_content = f"# {date_header}\n\n{content}"
            await self._write_file(path, full_content, mode="w")

        await self.git_sync_and_commit(f"Update journal: {date.strftime('%Y-%m-%d')}")

        return file_path
