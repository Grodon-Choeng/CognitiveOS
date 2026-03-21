import pytest

from app.config.settings import Settings
from app.infrastructure.db.session import dispose_engine, get_engine


@pytest.mark.asyncio
async def test_dispose_engine_resets_cached_engine() -> None:
    settings = Settings(
        database_url="postgresql+asyncpg://cognitiveos:cognitiveos@localhost:5432/cognitiveos"
    )
    first = get_engine(settings)

    await dispose_engine()

    second = get_engine(settings)
    await dispose_engine()

    assert first is not second
