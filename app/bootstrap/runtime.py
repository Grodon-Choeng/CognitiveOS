from dishka import AsyncContainer

from app.infrastructure.db.session import dispose_engine


async def cleanup_runtime_resources(container: AsyncContainer | None = None) -> None:
    if container is not None:
        await container.close()
    await dispose_engine()
