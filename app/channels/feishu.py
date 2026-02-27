import asyncio
import json
import os
import random
from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from app.config import settings
from app.utils import logger

try:
    import lark_oapi as lark
    from lark_oapi.api.im.v1 import (
        CreateMessageRequest,
        CreateMessageRequestBody,
    )
except Exception:  # pragma: no cover - optional dependency in runtime environment
    lark = None
    CreateMessageRequest = None
    CreateMessageRequestBody = None


@dataclass
class FeishuIncomingMessage:
    message_id: str
    user_open_id: str
    chat_id: str
    chat_type: str
    text: str


@dataclass
class FeishuBotStatus:
    enabled: bool
    running: bool
    connected: bool
    reconnect_attempts: int
    last_connected_at: str | None
    last_event_at: str | None
    last_error_at: str | None
    last_error: str | None


class FeishuBot:
    def __init__(
        self,
        app_id: str,
        app_secret: str,
        verification_token: str = "",
        encrypt_key: str = "",
        bypass_proxy: bool = False,
        on_message_callback: Callable[[FeishuIncomingMessage], Any] | None = None,
        on_alert_callback: Callable[[str], Any] | None = None,
    ) -> None:
        if not lark:
            raise RuntimeError("lark-oapi is not installed")

        self.app_id = app_id
        self.app_secret = app_secret
        self.verification_token = verification_token
        self.encrypt_key = encrypt_key
        self.bypass_proxy = bypass_proxy
        self.on_message_callback = on_message_callback
        self.on_alert_callback = on_alert_callback

        self._loop: asyncio.AbstractEventLoop | None = None
        self._supervisor_task: asyncio.Task | None = None
        self._ws_client: Any = None
        self._ws_loop: asyncio.AbstractEventLoop | None = None
        self._client = lark.Client.builder().app_id(app_id).app_secret(app_secret).build()
        self._user_chat_map: dict[str, str] = {}
        self._seen_messages: dict[str, datetime] = {}
        self._last_alert_at: dict[str, datetime] = {}

        self._running = False
        self._connected = False
        self._reconnect_attempts = 0
        self._last_connected_at: datetime | None = None
        self._last_event_at: datetime | None = None
        self._last_error_at: datetime | None = None
        self._last_error: str | None = None

    @property
    def connected(self):
        return self._connected

    def _ensure_no_proxy_for_feishu(self) -> None:
        if not self.bypass_proxy:
            return

        hosts = {
            "open.feishu.cn",
            ".feishu.cn",
            "open.larksuite.com",
            ".larksuite.com",
            ".larkoffice.com",
        }
        existing = os.environ.get("NO_PROXY", "")
        merged = {h.strip() for h in existing.split(",") if h.strip()}
        merged.update(hosts)
        value = ",".join(sorted(merged))

        os.environ["NO_PROXY"] = value
        os.environ["no_proxy"] = value

    def status(self) -> FeishuBotStatus:
        return FeishuBotStatus(
            enabled=True,
            running=self._running,
            connected=self._connected,
            reconnect_attempts=self._reconnect_attempts,
            last_connected_at=self._fmt_dt(self._last_connected_at),
            last_event_at=self._fmt_dt(self._last_event_at),
            last_error_at=self._fmt_dt(self._last_error_at),
            last_error=self._last_error,
        )

    async def start(self) -> None:
        if self._supervisor_task and not self._supervisor_task.done():
            return

        self._loop = asyncio.get_running_loop()
        self._running = True
        self._supervisor_task = asyncio.create_task(self._supervise_ws())
        logger.info("Feishu long connection started")

    async def stop(self) -> None:
        self._running = False

        if self._ws_loop and not self._ws_loop.is_closed():
            self._ws_loop.call_soon_threadsafe(self._ws_loop.stop)

        if self._supervisor_task and not self._supervisor_task.done():
            self._supervisor_task.cancel()
            with suppress(asyncio.CancelledError):
                await self._supervisor_task

        self._connected = False
        logger.info("Feishu long connection stopped")

    async def _supervise_ws(self) -> None:
        while self._running:
            self._reconnect_attempts += 1
            attempt = self._reconnect_attempts

            try:
                await asyncio.to_thread(self._run_ws_client_blocking)
            except Exception as e:
                self._record_error(f"Feishu ws error: {e}")
                await self._alert(
                    "ws_error",
                    f"Feishu 长连接异常（attempt={attempt}）: {e}",
                )

            if not self._running:
                break

            delay = self._next_backoff(attempt)
            logger.warning(f"Feishu ws disconnected, retry in {delay:.1f}s (attempt={attempt})")
            await asyncio.sleep(delay)

    @staticmethod
    def _next_backoff(attempt: int) -> float:
        # Exponential backoff with jitter: cap around 60s.
        exp = min(attempt, 6)
        return min(60.0, (2**exp) + random.uniform(0, 1.5))

    def _run_ws_client_blocking(self) -> None:
        self._connected = False
        self._ensure_no_proxy_for_feishu()

        assert lark is not None
        import lark_oapi.ws.client as lark_ws_client

        # lark-oapi keeps a module-level event loop and uses run_until_complete().
        # In Uvicorn, the default loop is already running, so we must isolate WS
        # client execution in a dedicated loop bound to this worker thread.
        thread_loop = asyncio.new_event_loop()
        old_loop = lark_ws_client.loop
        lark_ws_client.loop = thread_loop
        self._ws_loop = thread_loop
        asyncio.set_event_loop(thread_loop)
        dispatcher = (
            lark.EventDispatcherHandler.builder(
                self.verification_token,
                self.encrypt_key,
            )
            .register_p2_im_message_receive_v1(self._handle_message_event)
            .build()
        )

        try:
            self._ws_client = lark.ws.Client(
                self.app_id,
                self.app_secret,
                event_handler=dispatcher,
                log_level=lark.LogLevel.INFO,
                auto_reconnect=False,
            )

            self._connected = True
            self._last_connected_at = datetime.now(UTC)
            logger.info("Feishu ws client connected")
            self._ws_client.start()
            self._connected = False
        finally:
            self._ws_loop = None
            lark_ws_client.loop = old_loop
            asyncio.set_event_loop(None)
            thread_loop.close()

    def _record_error(self, error: str) -> None:
        self._last_error = error
        self._last_error_at = datetime.now(UTC)

    @staticmethod
    def _fmt_dt(value: datetime | None) -> str | None:
        return value.isoformat() if value else None

    async def _alert(self, key: str, message: str, cooldown_seconds: int = 300) -> None:
        now = datetime.now(UTC)
        last = self._last_alert_at.get(key)
        if last and (now - last).total_seconds() < cooldown_seconds:
            return
        self._last_alert_at[key] = now

        logger.error(message)
        if self.on_alert_callback and self._loop:
            future = asyncio.run_coroutine_threadsafe(self.on_alert_callback(message), self._loop)
            future.add_done_callback(self._log_future_exception)

    def _handle_message_event(self, data: Any) -> None:
        logger.info("[Feishu] Incoming event received")
        incoming = self._parse_incoming_message(data)
        if not incoming:
            logger.info("[Feishu] Incoming event ignored (unsupported type or missing fields)")
            return

        if self._is_duplicate(incoming.message_id):
            logger.info(f"[Feishu] Duplicate message ignored: message_id={incoming.message_id}")
            return

        self._user_chat_map[incoming.user_open_id] = incoming.chat_id
        self._last_event_at = datetime.now(UTC)
        self._cleanup_seen_messages()
        logger.info(
            "[Feishu] Message parsed: "
            f"message_id={incoming.message_id}, "
            f"chat_id={incoming.chat_id}, "
            f"user_open_id={incoming.user_open_id}, "
            f"chat_type={incoming.chat_type}, "
            f"text={incoming.text[:100]}"
        )

        if not self.on_message_callback or not self._loop:
            return

        future = asyncio.run_coroutine_threadsafe(
            self.on_message_callback(incoming),
            self._loop,
        )
        future.add_done_callback(self._log_future_exception)

    @staticmethod
    def _log_future_exception(future: Any) -> None:
        try:
            exc = future.exception()
        except asyncio.CancelledError:
            return
        if exc:
            logger.error(f"Feishu message callback failed: {exc}")

    def _is_duplicate(self, message_id: str, ttl_seconds: int = 600) -> bool:
        now = datetime.now(UTC)
        seen_at = self._seen_messages.get(message_id)
        if seen_at and (now - seen_at).total_seconds() < ttl_seconds:
            return True
        self._seen_messages[message_id] = now
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

    def _parse_incoming_message(self, data: Any) -> FeishuIncomingMessage | None:
        event = self._read_value(data, "event")
        if not event:
            return None

        message = self._read_value(event, "message")
        if not message:
            return None

        message_type = self._read_value(message, "message_type")
        if message_type != "text":
            return None

        content_raw = self._read_value(message, "content")
        text = self._extract_text(content_raw)
        if not text:
            return None

        sender = self._read_value(event, "sender")
        sender_id = self._read_value(sender, "sender_id")
        user_open_id = self._read_value(sender_id, "open_id", "")

        message_id = self._read_value(message, "message_id", "")
        chat_id = self._read_value(message, "chat_id", "")
        chat_type = self._read_value(message, "chat_type", "")

        if not user_open_id or not message_id:
            return None

        return FeishuIncomingMessage(
            message_id=message_id,
            user_open_id=user_open_id,
            chat_id=chat_id,
            chat_type=chat_type,
            text=text,
        )

    @staticmethod
    def _extract_text(content_raw: Any) -> str:
        if isinstance(content_raw, dict):
            return str(content_raw.get("text", "")).strip()

        if isinstance(content_raw, str):
            try:
                payload = json.loads(content_raw)
                if isinstance(payload, dict):
                    return str(payload.get("text", "")).strip()
            except json.JSONDecodeError:
                return content_raw.strip()

        return ""

    @staticmethod
    def _read_value(obj: Any, key: str, default: Any = None) -> Any:
        if obj is None:
            return default
        if isinstance(obj, dict):
            return obj.get(key, default)
        return getattr(obj, key, default)

    async def send_text_to_user(self, open_id: str, text: str) -> bool:
        return await asyncio.to_thread(self._send_text_sync, "open_id", open_id, text)

    async def send_text_to_chat(self, chat_id: str, text: str) -> bool:
        return await asyncio.to_thread(self._send_text_sync, "chat_id", chat_id, text)

    async def send_text_to_user_or_chat(self, user_open_id: str, text: str) -> bool:
        chat_id = self._user_chat_map.get(user_open_id)
        if chat_id:
            success = await self.send_text_to_chat(chat_id, text)
            if success:
                return True
        return await self.send_text_to_user(user_open_id, text)

    def _send_text_sync(self, receive_id_type: str, receive_id: str, text: str) -> bool:
        if not receive_id:
            return False
        if not CreateMessageRequest or not CreateMessageRequestBody:
            return False
        self._ensure_no_proxy_for_feishu()

        content = json.dumps({"text": text}, ensure_ascii=False)
        request = (
            CreateMessageRequest.builder()
            .receive_id_type(receive_id_type)
            .request_body(
                CreateMessageRequestBody.builder()
                .receive_id(receive_id)
                .msg_type("text")
                .content(content)
                .build()
            )
            .build()
        )
        response = self._client.im.v1.message.create(request)
        if response.success():
            return True

        logger.error(
            f"Failed to send Feishu message: code={response.code}, msg={response.msg}, "
            f"log_id={response.get_log_id()}"
        )
        return False


_bot_instance: FeishuBot | None = None


def get_feishu_bot() -> FeishuBot | None:
    return _bot_instance


def get_feishu_bot_status() -> FeishuBotStatus:
    if not _bot_instance:
        return FeishuBotStatus(
            enabled=False,
            running=False,
            connected=False,
            reconnect_attempts=0,
            last_connected_at=None,
            last_event_at=None,
            last_error_at=None,
            last_error=None,
        )
    return _bot_instance.status()


async def start_feishu_bot(
    on_message_callback: Callable[[FeishuIncomingMessage], Any] | None = None,
    on_alert_callback: Callable[[str], Any] | None = None,
) -> FeishuBot | None:
    global _bot_instance

    if not lark:
        logger.warning("Feishu bot disabled: missing dependency lark-oapi")
        return None

    feishu_config = None
    for cfg in settings.get_im_configs():
        if cfg.provider.value == "feishu":
            feishu_config = cfg
            break

    if not feishu_config:
        return None

    app_id = str(feishu_config.extra.get("app_id", "")).strip()
    app_secret = str(feishu_config.extra.get("app_secret", "")).strip()
    if not app_id or not app_secret:
        logger.info("Feishu long connection skipped: app_id/app_secret not configured")
        return None

    verification_token = str(feishu_config.extra.get("verification_token", ""))
    encrypt_key = str(feishu_config.extra.get("encrypt_key", ""))
    bypass_proxy = bool(feishu_config.extra.get("bypass_proxy", False))

    _bot_instance = FeishuBot(
        app_id=app_id,
        app_secret=app_secret,
        verification_token=verification_token,
        encrypt_key=encrypt_key,
        bypass_proxy=bypass_proxy,
        on_message_callback=on_message_callback,
        on_alert_callback=on_alert_callback,
    )
    await _bot_instance.start()
    return _bot_instance


async def stop_feishu_bot() -> None:
    global _bot_instance
    if _bot_instance:
        await _bot_instance.stop()
        _bot_instance = None
