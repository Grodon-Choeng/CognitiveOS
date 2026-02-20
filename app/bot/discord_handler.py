import discord

from app.services import ReminderService, start_discord_bot, stop_discord_bot
from app.services.reminder_checker import start_reminder_checker, stop_reminder_checker
from app.utils.logging import logger


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
        await message.reply(
            "**CognitiveOS Bot 命令**\n"
            "```\n"
            "!help           - 显示帮助\n"
            "!ping           - 测试延迟\n"
            "!remind         - 查看我的提醒列表\n"
            "!remind <内容>  - 创建提醒\n"
            "```\n"
            "**时间表达式示例**:\n"
            "```\n"
            "!remind 5分钟后 提交代码\n"
            "!remind 1小时后 开会\n"
            "!remind 今天 18:00 下班\n"
            "!remind 明天 10:00 发日报\n"
            "!remind 明天早上 晨会\n"
            "!remind 下班前 提交PR\n"
            "```\n"
        )
        return

    if content == "!ping":
        latency = round(message.guild.me.latency * 1000) if message.guild else 0
        await message.reply(f"Pong! 延迟: {latency}ms")
        return

    if content.startswith("!capture "):
        capture_content = content[9:].strip()
        if capture_content:
            await message.reply(f"已捕获: {capture_content[:100]}...")
        else:
            await message.reply("请提供要捕获的内容。用法: `!capture <内容>`")
        return

    await message.reply(f"收到: {content[:100]}")


async def handle_remind(message: discord.Message, text: str) -> None:
    remind_at, content = ReminderService.parse_time_expression(text)

    if not remind_at:
        await message.reply(
            "无法解析时间表达式。\n"
            "示例:\n"
            "• `!remind 5分钟后 提交代码`\n"
            "• `!remind 今天 18:00 下班`\n"
            "• `!remind 明天 10:00 发日报`"
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

    time_remaining = ReminderService.format_time_remaining(remind_at)
    await message.reply(
        f"✅ 已设置提醒\n\n**内容**: {content}\n**时间**: {remind_at.strftime('%Y-%m-%d %H:%M')}\n**剩余**: {time_remaining}"
    )


async def handle_list_reminders(message: discord.Message) -> None:
    user_id = str(message.author.id)
    reminders = await ReminderService.get_user_reminders(user_id)

    if not reminders:
        await message.reply("暂无待处理的提醒。")
        return

    lines = ["**我的提醒列表**:\n"]
    for i, r in enumerate(reminders, 1):
        time_remaining = ReminderService.format_time_remaining(r.remind_at)
        lines.append(f"{i}. {r.content}")
        lines.append(f"   时间: {r.remind_at.strftime('%Y-%m-%d %H:%M')} ({time_remaining})")

    await message.reply("\n".join(lines))


async def start_bot() -> None:
    await start_discord_bot(on_message_callback=handle_discord_message)
    start_reminder_checker()


async def stop_bot() -> None:
    stop_reminder_checker()
    await stop_discord_bot()
