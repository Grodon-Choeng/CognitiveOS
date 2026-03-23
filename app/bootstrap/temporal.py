import asyncio

from app.bootstrap.container import AsyncSessionFactory, create_runtime_container
from app.bootstrap.runtime import cleanup_runtime_resources
from app.config.settings import get_settings
from app.infrastructure.integrations.messaging.base import MessagingAdapter
from app.infrastructure.temporal.client import create_temporal_client
from app.infrastructure.temporal.workers import create_worker
from app.observability.logging import configure_logging
from app.observability.tracing import configure_tracing
from app.observability.workflow_events import MultiWorkflowEventRecorder


async def run_temporal_worker() -> None:
    settings = get_settings()
    configure_logging(settings)
    configure_tracing(settings)
    client = await create_temporal_client(settings)
    container = create_runtime_container(settings)
    messaging_adapter = await container.get(MessagingAdapter)
    session_factory = await container.get(AsyncSessionFactory)
    workflow_event_recorder = await container.get(MultiWorkflowEventRecorder)
    worker = create_worker(
        client=client,
        settings=settings,
        messaging_adapter=messaging_adapter,
        session_factory=session_factory,
        workflow_event_recorder=workflow_event_recorder,
    )
    try:
        await worker.run()
    finally:
        await cleanup_runtime_resources(container)


def main() -> None:
    asyncio.run(run_temporal_worker())


if __name__ == "__main__":
    main()
