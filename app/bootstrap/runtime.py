from app.bootstrap.container import reset_container
from app.infrastructure.db.session import dispose_engine


async def cleanup_runtime_resources() -> None:
    reset_container()
    await dispose_engine()
