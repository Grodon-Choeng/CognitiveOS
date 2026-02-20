import asyncio
from collections.abc import Callable

import discord
from discord.ext import commands

from app.config import settings
from app.utils.logging import logger


class DiscordBot:
    def __init__(
        self,
        token: str,
        command_prefix: str = "!",
        proxy: str | None = None,
        on_message_callback: Callable | None = None,
    ) -> None:
        self.token = token
        self.command_prefix = command_prefix
        self.proxy = proxy
        self.on_message_callback = on_message_callback

        logger.info(f"Initializing Discord Bot with prefix: {command_prefix}")
        logger.info(f"Token length: {len(token)} chars, starts with: {token[:10]}...")
        if proxy:
            logger.info(f"Using proxy: {proxy}")

        intents = discord.Intents.default()
        intents.message_content = True
        intents.messages = True

        logger.info("Discord intents configured: message_content=True, messages=True")

        connector = None
        if proxy:
            import aiohttp

            connector = aiohttp.TCPConnector()

        self.bot = commands.Bot(
            command_prefix=command_prefix,
            intents=intents,
            connector=connector,
        )

        if proxy:
            self.bot.http.proxy = proxy

        self._setup_events()

    def _setup_events(self) -> None:
        @self.bot.event
        async def on_ready():
            logger.info(f"Discord Bot logged in as {self.bot.user}")
            logger.info(f"Bot ID: {self.bot.user.id}")
            logger.info(f"Connected to {len(self.bot.guilds)} guild(s)")
            for guild in self.bot.guilds:
                logger.info(f"  - Guild: {guild.name} (ID: {guild.id})")

        @self.bot.event
        async def on_connect():
            logger.info("Discord Bot connected to Discord gateway")

        @self.bot.event
        async def on_disconnect():
            logger.warning("Discord Bot disconnected from Discord")

        @self.bot.event
        async def on_resumed():
            logger.info("Discord Bot resumed session")

        @self.bot.event
        async def on_error(event: str, *args, **kwargs):
            logger.error(f"Discord Bot error in event: {event}")

        @self.bot.event
        async def on_message(message: discord.Message):
            if message.author == self.bot.user:
                return

            if message.author.bot:
                return

            logger.info(
                f"[Discord] Message from {message.author} in #{message.channel}: {message.content[:100]}"
            )

            if self.on_message_callback:
                try:
                    await self.on_message_callback(message)
                except Exception as e:
                    logger.error(f"Error in message callback: {e}")
                    await message.reply(f"Error processing message: {e}")

    async def send_to_channel(self, channel_id: int, content: str) -> None:
        channel = self.bot.get_channel(channel_id)
        if channel:
            await channel.send(content)
        else:
            logger.warning(f"Channel {channel_id} not found")

    async def start(self) -> None:
        logger.info("Starting Discord Bot connection...")
        try:
            await self.bot.start(self.token)
        except discord.LoginFailure as e:
            logger.error(f"Discord login failed: {e}")
            raise
        except discord.ConnectionClosed as e:
            logger.error(f"Discord connection closed: {e}")
            raise
        except Exception as e:
            logger.error(f"Discord Bot error: {e}")
            raise

    async def stop(self) -> None:
        logger.info("Stopping Discord Bot...")
        await self.bot.close()


_bot_instance: DiscordBot | None = None


def get_discord_bot() -> DiscordBot | None:
    return _bot_instance


async def start_discord_bot(on_message_callback: Callable | None = None) -> DiscordBot | None:
    global _bot_instance

    logger.info("Looking for Discord configuration...")

    discord_config = None
    for cfg in settings.get_im_configs():
        if cfg.provider.value == "discord":
            discord_config = cfg
            break

    if not discord_config:
        logger.warning("Discord not configured in IM_CONFIGS")
        return None

    bot_token = discord_config.extra.get("bot_token")
    if not bot_token:
        logger.warning("Discord bot_token not found in configuration")
        logger.info(f"Available extra keys: {list(discord_config.extra.keys())}")
        return None

    command_prefix = discord_config.extra.get("command_prefix", "!")
    proxy = discord_config.extra.get("proxy") or settings.proxy_url or None

    logger.info("Creating Discord Bot instance...")
    _bot_instance = DiscordBot(
        token=bot_token,
        command_prefix=command_prefix,
        proxy=proxy,
        on_message_callback=on_message_callback,
    )

    logger.info("Scheduling Discord Bot start task...")
    asyncio.create_task(_bot_instance.start())
    return _bot_instance


async def stop_discord_bot() -> None:
    global _bot_instance
    if _bot_instance:
        await _bot_instance.stop()
        _bot_instance = None
