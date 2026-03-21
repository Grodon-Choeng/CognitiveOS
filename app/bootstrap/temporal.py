import asyncio

from app.bootstrap.container import get_container
from app.config.settings import get_settings
from app.infrastructure.temporal.client import create_temporal_client
from app.infrastructure.temporal.workers import create_worker
from app.observability.logging import configure_logging
from app.observability.tracing import configure_tracing


async def run_temporal_worker() -> None:
    settings = get_settings()
    configure_logging(settings)
    configure_tracing(settings)
    client = await create_temporal_client(settings)
    container = get_container()
    worker = create_worker(
        client=client,
        settings=settings,
        messaging_adapter=container.build_messaging_adapter(),
        session_factory=container.session_factory,
        workflow_event_recorder=container.build_workflow_event_recorder(),
    )
    await worker.run()


def main() -> None:
    asyncio.run(run_temporal_worker())


if __name__ == "__main__":
    main()
