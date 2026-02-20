import random
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from app.note import NoteService, TaskPriority
from app.services.reminder_service import ReminderService
from app.utils.logging import logger


@dataclass
class IncomingMessage:
    provider: str
    user_id: str
    text: str
    reply: Callable[[str], Awaitable[None]]
    channel_id: int | None = None


RESPONSE_TEMPLATES = {
    "reminder_created": [
        "好的，{time}提醒你「{content}」",
        "收到！{time}会提醒你{content}",
        "已设置提醒：{content}（{time}）",
        "没问题，{time}准时提醒你{content}",
    ],
    "idea": [
        "记下了这个灵感：{content}",
        "好想法！已记录：{content}",
        "灵感已保存：{content}",
        "这个想法不错，记下来了：{content}",
    ],
    "task_later": [
        "待办已添加：{content}",
        "好的，稍后处理：{content}",
        "记在待办里了：{content}",
    ],
    "task_now": [
        "紧急任务：{content}",
        "马上处理：{content}",
        "优先级已设为紧急：{content}",
    ],
    "task_done": [
        "已完成：{content}",
        "记录为已完成：{content}",
        "好的，标记为完成：{content}",
    ],
    "note": [
        "记下了：{content}",
        "已记录：{content}",
        "好的，保存了：{content}",
    ],
    "no_reminders": [
        "暂时没有待处理的提醒",
        "提醒列表是空的",
        "没有需要提醒的事项",
    ],
}


class BotMessageService:
    def __init__(self, note_service: NoteService | None = None) -> None:
        self.note_service = note_service or NoteService()

    async def handle(self, message: IncomingMessage) -> None:
        text = message.text.strip()
        if not text:
            return

        logger.info(f"[{message.provider}] {message.user_id}: {text}")

        if text.startswith(("!remind ", "!提醒 ", "/remind ")):
            command_text = text.split(" ", 1)[1] if " " in text else ""
            await self._handle_remind(message, command_text)
            return

        if text in ("!remind", "!提醒", "/remind", "提醒列表"):
            await self._handle_list_reminders(message)
            return

        if text in ("!help", "/help", "帮助"):
            await message.reply(self._help_text())
            return

        if text in ("!ping", "/ping", "ping"):
            await message.reply("Pong!")
            return

        if text.startswith(("!", "/")):
            return

        await self._handle_note(message, text)

    @staticmethod
    def _help_text() -> str:
        return (
            "命令列表\n"
            "!help 或 /help          帮助\n"
            "!ping 或 /ping          测试\n"
            "!remind                 查看提醒\n"
            "!remind <内容>          创建提醒\n"
            "\n"
            "笔记记录\n"
            "灵感 <内容>              记录灵感\n"
            "任务 <内容>              待办任务\n"
            "紧急 任务 <内容>         紧急任务\n"
            "完成 任务 <内容>         已完成任务\n"
            "记录 <内容>              普通笔记\n"
            "\n"
            "时间表达式\n"
            "5分钟后、1小时后、明天 10:00、下班前"
        )

    @staticmethod
    def _get_response(key: str, **kwargs: str) -> str:
        templates = RESPONSE_TEMPLATES.get(key, ["{content}"])
        return random.choice(templates).format(**kwargs)

    @staticmethod
    def _parse_note_type(content: str) -> tuple[str, str, TaskPriority]:
        content = content.strip()
        priority = TaskPriority.LATER

        priority_patterns = [
            (r"^紧急\s*", TaskPriority.NOW),
            (r"^now\s*", TaskPriority.NOW),
            (r"^重要\s*", TaskPriority.NOW),
            (r"^完成\s*", TaskPriority.DONE),
            (r"^done\s*", TaskPriority.DONE),
        ]

        for pattern, prio in priority_patterns:
            match = re.match(pattern, content, re.IGNORECASE)
            if match:
                content = content[match.end() :].strip()
                priority = prio
                break

        patterns = [
            (r"^灵感\s*", "idea"),
            (r"^idea\s*", "idea"),
            (r"^任务\s*", "task"),
            (r"^task\s*", "task"),
            (r"^todo\s*", "task"),
            (r"^记录\s*", "note"),
            (r"^note\s*", "note"),
        ]

        for pattern, note_type in patterns:
            match = re.match(pattern, content, re.IGNORECASE)
            if match:
                return note_type, content[match.end() :].strip(), priority

        return "note", content, priority

    async def _handle_remind(self, message: IncomingMessage, text: str) -> None:
        remind_at, content = ReminderService.parse_time_expression(text)
        if not remind_at:
            await message.reply(
                "不太明白这个时间，试试这样：\n"
                "• !remind 5分钟后 提交代码\n"
                "• !remind 明天 10:00 开会\n"
                "• !remind 下班前 发日报"
            )
            return

        if not content:
            content = "提醒!"

        await ReminderService.create_reminder(
            content=content,
            remind_at=remind_at,
            user_id=message.user_id,
            channel_id=message.channel_id,
            provider=message.provider,
        )

        await self.note_service.write_reminder(content, remind_at, tags=[message.provider])

        time_remaining = ReminderService.format_time_remaining(remind_at)
        time_str = f"{remind_at.strftime('%m月%d日 %H:%M')}（{time_remaining}后）"
        await message.reply(self._get_response("reminder_created", content=content, time=time_str))

    async def _handle_list_reminders(self, message: IncomingMessage) -> None:
        reminders = await ReminderService.get_user_reminders(message.user_id)
        if not reminders:
            await message.reply(self._get_response("no_reminders"))
            return

        lines = ["待处理提醒"]
        for i, r in enumerate(reminders, 1):
            time_remaining = ReminderService.format_time_remaining(r.remind_at)
            lines.append(f"{i}. {r.content}")
            lines.append(f"   {r.remind_at.strftime('%m月%d日 %H:%M')}（{time_remaining}）")
        await message.reply("\n".join(lines))

    async def _handle_note(self, message: IncomingMessage, text: str) -> None:
        note_type, note_content, priority = self._parse_note_type(text)

        if not note_content:
            await message.reply("要记录什么内容呢？")
            return

        if note_type == "idea":
            await self.note_service.write_idea(note_content, tags=[message.provider])
            await message.reply(self._get_response("idea", content=note_content))
            return

        if note_type == "task":
            await self.note_service.write_task(
                note_content,
                priority=priority,
                tags=[message.provider],
            )
            if priority == TaskPriority.NOW:
                await message.reply(self._get_response("task_now", content=note_content))
            elif priority == TaskPriority.DONE:
                await message.reply(self._get_response("task_done", content=note_content))
            else:
                await message.reply(self._get_response("task_later", content=note_content))
            return

        await self.note_service.write_note(note_content, tags=[message.provider])
        await message.reply(self._get_response("note", content=note_content))
