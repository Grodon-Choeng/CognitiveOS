import asyncio

from app.config.settings import get_settings
from app.infrastructure.integrations.messaging.logging_adapter import LoggingMessagingAdapter
from app.infrastructure.temporal.client import create_temporal_client
from app.infrastructure.temporal.workers import create_worker
from app.observability.logging import configure_logging
from app.observability.tracing import configure_tracing


async def run_temporal_worker() -> None:
    settings = get_settings()
    configure_logging(settings)
    configure_tracing(settings)
    client = await create_temporal_client(settings)
    worker = create_worker(
        client=client,
        settings=settings,
        messaging_adapter=LoggingMessagingAdapter(),
    )
    await worker.run()


def main() -> None:
    asyncio.run(run_temporal_worker())


if __name__ == "__main__":
    main()
