import asyncio
import logging
from importlib import import_module
from typing import Any, cast

from dishka import AsyncContainer

from app.bootstrap.container import create_runtime_container
from app.bootstrap.runtime import cleanup_runtime_resources
from app.config.settings import get_settings
from app.infrastructure.integrations.messaging import FeishuLongConnectionListener
from app.observability.logging import configure_logging

logger = logging.getLogger(__name__)


async def _resolve_listener(container: AsyncContainer) -> FeishuLongConnectionListener:
    return await container.get(FeishuLongConnectionListener)


def _bind_feishu_ws_client_loop(loop: asyncio.AbstractEventLoop) -> None:
    try:
        ws_client = import_module("lark_oapi.ws.client")
    except ModuleNotFoundError as exc:
        if exc.name not in {"lark_oapi", "lark_oapi.ws", "lark_oapi.ws.client"}:
            raise
        logger.info("未检测到飞书长连接 SDK，跳过事件循环绑定。")
        return
    cast(Any, ws_client).loop = loop


def _drain_pending_tasks(loop: asyncio.AbstractEventLoop) -> None:
    pending_tasks = [task for task in asyncio.all_tasks(loop) if not task.done()]
    if not pending_tasks:
        return
    for task in pending_tasks:
        task.cancel()
    loop.run_until_complete(asyncio.gather(*pending_tasks, return_exceptions=True))


def main() -> None:
    settings = get_settings()
    configure_logging(settings)
    container: AsyncContainer | None = None
    listener: FeishuLongConnectionListener | None = None
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    _bind_feishu_ws_client_loop(loop)
    try:
        container = create_runtime_container(settings)
        listener = loop.run_until_complete(_resolve_listener(container))
        _bind_feishu_ws_client_loop(loop)
        listener.start()
    except KeyboardInterrupt:
        logger.info("收到中断信号，准备停止飞书长连接监听。")
    finally:
        try:
            if listener is not None:
                loop.run_until_complete(listener.stop())
            if container is not None:
                loop.run_until_complete(cleanup_runtime_resources(container))
        finally:
            _drain_pending_tasks(loop)
            loop.run_until_complete(loop.shutdown_asyncgens())
            asyncio.set_event_loop(None)
            loop.close()


if __name__ == "__main__":
    main()
