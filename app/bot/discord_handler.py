import random
import re

import discord

from app.note import NoteService, TaskPriority
from app.services import ReminderService, start_discord_bot, stop_discord_bot
from app.services.reminder_checker import start_reminder_checker, stop_reminder_checker
from app.utils.logging import logger

note_service = NoteService()

RESPONSE_TEMPLATES = {
    "reminder_created": [
        "好的，{time}提醒你「{content}」",
        "收到！{time}会提醒你{content}",
        "已设置提醒：{content}（{time}）",
        "没问题，{time}准时提醒你{content}",
    ],
    "idea": [
        "记下了这个灵感：{content}",
        "💡 好想法！已记录：{content}",
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
        "🔴 马上处理：{content}",
        "优先级已设为紧急：{content}",
    ],
    "task_done": [
        "已完成：{content}",
        "✅ 记录为已完成：{content}",
        "好的，标记为完成：{content}",
    ],
    "note": [
        "记下了：{content}",
        "📝 已记录：{content}",
        "好的，保存了：{content}",
    ],
    "no_reminders": [
        "暂时没有待处理的提醒",
        "提醒列表是空的",
        "没有需要提醒的事项",
    ],
    "help": [
        "有什么可以帮你的？",
        "需要帮助吗？",
    ],
}


def get_response(key: str, **kwargs) -> str:
    templates = RESPONSE_TEMPLATES.get(key, ["{content}"])
    template = random.choice(templates)
    return template.format(**kwargs)


async def send_message(message: discord.Message, content: str) -> None:
    if isinstance(message.channel, discord.DMChannel):
        await message.channel.send(content)
    else:
        await message.channel.send(content)


def parse_note_type(content: str) -> tuple[str, str, TaskPriority]:
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
        (r"^💡\s*", "idea"),
        (r"^任务\s*", "task"),
        (r"^task\s*", "task"),
        (r"^TODO\s*", "task"),
        (r"^记录\s*", "note"),
        (r"^note\s*", "note"),
        (r"^📝\s*", "note"),
    ]

    for pattern, note_type in patterns:
        match = re.match(pattern, content, re.IGNORECASE)
        if match:
            remaining = content[match.end() :].strip()
            return note_type, remaining, priority

    return "note", content, priority


async def handle_discord_message(message: discord.Message) -> None:
    logger.info(f"[Discord] {message.author}: {message.content}")

    content = message.content.strip()

    if content.startswith("!remind ") or content.startswith("!提醒 "):
        await handle_remind(message, content[8:])
        return

    if content in ("!remind", "!提醒"):
        await handle_list_reminders(message)
        return

    if content == "!help":
        await send_message(
            message,
            "**命令列表**\n"
            "```\n"
            "!help           帮助\n"
            "!ping           测试\n"
            "!remind         查看提醒\n"
            "!remind <内容>  创建提醒\n"
            "```\n"
            "**笔记记录**\n"
            "```\n"
            "灵感 <内容>       记录灵感\n"
            "任务 <内容>       待办任务\n"
            "紧急 任务 <内容>  紧急任务\n"
            "完成 任务 <内容>  已完成任务\n"
            "记录 <内容>       普通笔记\n"
            "```\n"
            "**时间表达式**\n"
            "```\n"
            "5分钟后、1小时后、明天 10:00\n"
            "下班前、明天早上\n"
            "```\n",
        )
        return

    if content == "!ping":
        latency = round(message.guild.me.latency * 1000) if message.guild else 0
        await send_message(message, f"Pong! {latency}ms")
        return

    if content.startswith("!"):
        return

    await handle_note(message, content)


async def handle_remind(message: discord.Message, text: str) -> None:
    remind_at, content = ReminderService.parse_time_expression(text)

    if not remind_at:
        await send_message(
            message,
            "不太明白这个时间，试试这样：\n"
            "• `!remind 5分钟后 提交代码`\n"
            "• `!remind 明天 10:00 开会`\n"
            "• `!remind 下班前 发日报`",
        )
        return

    if not content:
        content = "提醒!"

    user_id = str(message.author.id)
    channel_id = message.channel.id if message.channel else None
    guild_id = message.guild.id if message.guild else None

    await ReminderService.create_reminder(
        content=content,
        remind_at=remind_at,
        user_id=user_id,
        channel_id=channel_id,
        guild_id=guild_id,
    )

    await note_service.write_reminder(content, remind_at, tags=["discord"])

    time_remaining = ReminderService.format_time_remaining(remind_at)
    time_str = f"{remind_at.strftime('%m月%d日 %H:%M')}（{time_remaining}后）"

    response = get_response("reminder_created", content=content, time=time_str)
    await send_message(message, response)


async def handle_list_reminders(message: discord.Message) -> None:
    user_id = str(message.author.id)
    reminders = await ReminderService.get_user_reminders(user_id)

    if not reminders:
        await send_message(message, get_response("no_reminders"))
        return

    lines = ["**待处理提醒**\n"]
    for i, r in enumerate(reminders, 1):
        time_remaining = ReminderService.format_time_remaining(r.remind_at)
        lines.append(f"{i}. {r.content}")
        lines.append(f"   {r.remind_at.strftime('%m月%d日 %H:%M')}（{time_remaining}）")

    await send_message(message, "\n".join(lines))


async def handle_note(message: discord.Message, content: str) -> None:
    note_type, note_content, priority = parse_note_type(content)

    if not note_content:
        await send_message(message, "要记录什么内容呢？")
        return

    if note_type == "idea":
        await note_service.write_idea(note_content, tags=["discord"])
        response = get_response("idea", content=note_content)
        await send_message(message, response)

    elif note_type == "task":
        await note_service.write_task(note_content, priority=priority, tags=["discord"])
        if priority == TaskPriority.NOW:
            response = get_response("task_now", content=note_content)
        elif priority == TaskPriority.DONE:
            response = get_response("task_done", content=note_content)
        else:
            response = get_response("task_later", content=note_content)
        await send_message(message, response)

    else:
        await note_service.write_note(note_content, tags=["discord"])
        response = get_response("note", content=note_content)
        await send_message(message, response)

    logger.info(f"Wrote {note_type} to journal")


async def start_bot() -> None:
    await start_discord_bot(on_message_callback=handle_discord_message)
    start_reminder_checker()


async def stop_bot() -> None:
    stop_reminder_checker()
    await stop_discord_bot()
