from temporalio.client import Client

from app.config.settings import Settings


async def create_temporal_client(settings: Settings) -> Client:
    return await Client.connect(
        target_host=settings.temporal_host,
        namespace=settings.temporal_namespace,
    )
