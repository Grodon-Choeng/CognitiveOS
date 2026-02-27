import asyncio
import random
from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, datetime

import discord
from discord.ext import commands
from pydantic import SecretStr

from app.config import settings
from app.utils import logger


@dataclass
class DiscordBotStatus:
    enabled: bool
    running: bool
    connected: bool
    reconnect_attempts: int
    last_connected_at: str | None
    last_event_at: str | None
    last_error_at: str | None
    last_error: str | None
    guild_count: int


class DiscordBot:
    def __init__(
        self,
        token: str,
        command_prefix: str = "!",
        proxy: str | None = None,
        heartbeat_timeout: float = 120.0,
        on_message_callback: Callable | None = None,
        on_alert_callback: Callable[[str], None] | None = None,
    ) -> None:
        self.token = SecretStr(token)
        self.command_prefix = command_prefix
        self.proxy = proxy
        self.heartbeat_timeout = heartbeat_timeout
        self.on_message_callback = on_message_callback
        self.on_alert_callback = on_alert_callback

        self._loop: asyncio.AbstractEventLoop | None = None
        self._supervisor_task: asyncio.Task | None = None
        self._disconnect_monitor_task: asyncio.Task | None = None

        self._running = False
        self._connected = False
        self._reconnect_attempts = 0
        self._last_connected_at: datetime | None = None
        self._last_event_at: datetime | None = None
        self._last_error_at: datetime | None = None
        self._last_error: str | None = None
        self._last_alert_at: dict[str, datetime] = {}
        self._seen_messages: dict[str, datetime] = {}

        logger.info(f"Initializing Discord Bot with prefix: {command_prefix}")
        logger.info(f"Token length: {len(self.token)} chars, starts with: {self.token}...")
        logger.info(f"Discord heartbeat timeout: {heartbeat_timeout}s")
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
            heartbeat_timeout=heartbeat_timeout,
        )

        if proxy:
            self.bot.http.proxy = proxy

        self._setup_events()

    @property
    def connected(self):
        return self._connected

    def status(self) -> DiscordBotStatus:
        guild_count = len(self.bot.guilds) if self.bot.user else 0
        return DiscordBotStatus(
            enabled=True,
            running=self._running,
            connected=self._connected,
            reconnect_attempts=self._reconnect_attempts,
            last_connected_at=self._fmt_dt(self._last_connected_at),
            last_event_at=self._fmt_dt(self._last_event_at),
            last_error_at=self._fmt_dt(self._last_error_at),
            last_error=self._last_error,
            guild_count=guild_count,
        )

    @staticmethod
    def _fmt_dt(value: datetime | None) -> str | None:
        return value.isoformat() if value else None

    def _record_error(self, error: str) -> None:
        self._last_error = error
        self._last_error_at = datetime.now(UTC)

    @staticmethod
    def _next_backoff(attempt: int) -> float:
        exp = min(attempt, 6)
        return min(60.0, (2**exp) + random.uniform(0, 1.5))

    async def _alert(self, key: str, message: str, cooldown_seconds: int = 300) -> None:
        now = datetime.now(UTC)
        last = self._last_alert_at.get(key)
        if last and (now - last).total_seconds() < cooldown_seconds:
            return
        self._last_alert_at[key] = now

        logger.error(message)
        if self.on_alert_callback and self._loop:
            if asyncio.iscoroutinefunction(self.on_alert_callback):
                asyncio.run_coroutine_threadsafe(self.on_alert_callback(message), self._loop)
            else:
                self._loop.call_soon_threadsafe(self.on_alert_callback, message)

    def _is_duplicate(self, message_id: int, ttl_seconds: int = 600) -> bool:
        key = str(message_id)
        now = datetime.now(UTC)
        seen_at = self._seen_messages.get(key)
        if seen_at and (now - seen_at).total_seconds() < ttl_seconds:
            return True
        self._seen_messages[key] = now
        return False

    def _cleanup_seen_messages(self, ttl_seconds: int = 600, max_size: int = 2000) -> None:
        if len(self._seen_messages) <= max_size:
            return
        now = datetime.now(UTC)
        stale_ids = [
            msg_id
            for msg_id, ts in self._seen_messages.items()
            if (now - ts).total_seconds() > ttl_seconds
        ]
        for msg_id in stale_ids:
            self._seen_messages.pop(msg_id, None)

    def _setup_events(self) -> None:
        async def _confirm_disconnect(attempt: int, grace_seconds: int = 8) -> None:
            await asyncio.sleep(grace_seconds)
            if not self._running or self._connected:
                return
            self._record_error(f"Disconnected for more than {grace_seconds}s")
            await self._alert(
                "disconnect",
                f"Discord Bot 断开连接（attempt={attempt}, 持续>{grace_seconds}s）",
            )

        @self.bot.event
        async def on_ready():
            self._connected = True
            self._last_connected_at = datetime.now(UTC)
            self._reconnect_attempts = 0
            logger.info(f"Discord Bot logged in as {self.bot.user}")
            logger.info(f"Bot ID: {self.bot.user.id}")
            logger.info(f"Connected to {len(self.bot.guilds)} guild(s)")
            for guild in self.bot.guilds:
                logger.info(f"  - Guild: {guild.name} (ID: {guild.id})")

        @self.bot.event
        async def on_connect():
            self._connected = True
            logger.info("Discord Bot connected to Discord gateway")

        @self.bot.event
        async def on_disconnect():
            self._connected = False
            self._reconnect_attempts += 1
            attempt = self._reconnect_attempts
            logger.warning(f"Discord Bot disconnected from Discord (attempt={attempt})")
            if self._disconnect_monitor_task and not self._disconnect_monitor_task.done():
                self._disconnect_monitor_task.cancel()
            self._disconnect_monitor_task = asyncio.create_task(_confirm_disconnect(attempt))

        @self.bot.event
        async def on_resumed():
            self._connected = True
            self._reconnect_attempts = 0
            if self._disconnect_monitor_task and not self._disconnect_monitor_task.done():
                self._disconnect_monitor_task.cancel()
            logger.info("Discord Bot resumed session")

        @self.bot.event
        async def on_error(event: str, *args, **kwargs):
            self._record_error(f"Error in event: {event}")
            logger.error(f"Discord Bot error in event: {event}")
            await self._alert("error", f"Discord Bot 错误: {event}")

        @self.bot.event
        async def on_message(message: discord.Message):
            if message.author == self.bot.user:
                return

            if message.author.bot:
                return

            if self._is_duplicate(message.id):
                return

            self._last_event_at = datetime.now(UTC)
            self._cleanup_seen_messages()

            logger.info(
                f"[Discord] Message from {message.author} in #{message.channel}: {message.content[:100]}"
            )

            if self.on_message_callback:
                try:
                    await self.on_message_callback(message)
                except Exception as e:
                    self._record_error(str(e))
                    logger.error(f"Error in message callback: {e}")

    async def send_to_channel(self, channel_id: int, content: str) -> bool:
        channel = self.bot.get_channel(channel_id)
        if channel:
            await channel.send(content)
            return True
        else:
            logger.warning(f"Channel {channel_id} not found")
            return False

    async def send_to_user(self, user_id: int, content: str) -> bool:
        user = self.bot.get_user(user_id)
        if not user:
            user = await self.bot.fetch_user(user_id)
        if user:
            await user.send(content)
            return True
        else:
            logger.warning(f"User {user_id} not found")
            return False

    async def start(self) -> None:
        self._loop = asyncio.get_running_loop()
        self._running = True

        while self._running:
            self._reconnect_attempts += 1
            attempt = self._reconnect_attempts

            try:
                logger.info("Starting Discord Bot connection...")
                await self.bot.start(self.token.get_secret_value())
            except discord.LoginFailure as e:
                self._record_error(f"Login failed: {e}")
                logger.error(f"Discord login failed: {e}")
                await self._alert("login_error", f"Discord 登录失败: {e}")
                raise
            except discord.ConnectionClosed as e:
                self._record_error(f"Connection closed: {e}")
                logger.error(f"Discord connection closed: {e}")
                await self._alert(
                    "connection_closed",
                    f"Discord 连接关闭（attempt={attempt}）: {e}",
                )
            except Exception as e:
                self._record_error(str(e))
                logger.error(f"Discord Bot error: {e}")
                await self._alert("error", f"Discord Bot 异常（attempt={attempt}）: {e}")

            if not self._running:
                break

            delay = self._next_backoff(attempt)
            logger.warning(f"Discord Bot disconnected, retry in {delay:.1f}s (attempt={attempt})")
            await asyncio.sleep(delay)

    async def stop(self) -> None:
        self._running = False
        self._connected = False

        if self._disconnect_monitor_task and not self._disconnect_monitor_task.done():
            self._disconnect_monitor_task.cancel()
            with suppress(asyncio.CancelledError):
                await self._disconnect_monitor_task

        if self._supervisor_task and not self._supervisor_task.done():
            self._supervisor_task.cancel()
            with suppress(asyncio.CancelledError):
                await self._supervisor_task

        logger.info("Stopping Discord Bot...")
        await self.bot.close()


_bot_instance: DiscordBot | None = None


def get_discord_bot() -> DiscordBot | None:
    return _bot_instance


def get_discord_bot_status() -> DiscordBotStatus:
    if not _bot_instance:
        return DiscordBotStatus(
            enabled=False,
            running=False,
            connected=False,
            reconnect_attempts=0,
            last_connected_at=None,
            last_event_at=None,
            last_error_at=None,
            last_error=None,
            guild_count=0,
        )
    return _bot_instance.status()


async def start_discord_bot(
    on_message_callback: Callable | None = None,
    on_alert_callback: Callable[[str], None] | None = None,
) -> DiscordBot | None:
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
    bypass_proxy = bool(discord_config.extra.get("bypass_proxy", False))
    proxy = (
        None if bypass_proxy else (discord_config.extra.get("proxy") or settings.proxy_url or None)
    )
    heartbeat_timeout = float(discord_config.extra.get("heartbeat_timeout", 120.0))

    logger.info("Creating Discord Bot instance...")
    _bot_instance = DiscordBot(
        token=bot_token,
        command_prefix=command_prefix,
        proxy=proxy,
        heartbeat_timeout=heartbeat_timeout,
        on_message_callback=on_message_callback,
        on_alert_callback=on_alert_callback,
    )

    logger.info("Scheduling Discord Bot start task...")
    _bot_instance._supervisor_task = asyncio.create_task(_bot_instance.start())
    return _bot_instance


async def stop_discord_bot() -> None:
    global _bot_instance
    if _bot_instance:
        await _bot_instance.stop()
        _bot_instance = None
