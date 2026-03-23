import asyncio

from app.bootstrap.container import create_runtime_container
from app.bootstrap.runtime import cleanup_runtime_resources
from app.config.settings import get_settings
from app.infrastructure.integrations.messaging import FeishuLongConnectionListener
from app.observability.logging import configure_logging


async def run_feishu_long_connection_listener() -> None:
    settings = get_settings()
    configure_logging(settings)
    container = create_runtime_container(settings)
    listener = await container.get(FeishuLongConnectionListener)
    try:
        listener.start()
    finally:
        await cleanup_runtime_resources(container)


def main() -> None:
    asyncio.run(run_feishu_long_connection_listener())


if __name__ == "__main__":
    main()
