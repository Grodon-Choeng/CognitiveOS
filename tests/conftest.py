import asyncio
from collections.abc import AsyncGenerator, Generator
from pathlib import Path
from uuid import uuid4

import pytest
import pytest_asyncio

from app.config import Settings
from app.core.repository import BaseRepository
from app.models.knowledge_item import KnowledgeItem
from app.models.prompt import Prompt


@pytest.fixture(scope="session")
def event_loop() -> Generator[asyncio.AbstractEventLoop, None, None]:
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def test_settings(tmp_path: Path) -> Settings:
    return Settings(
        environment="development",
        debug=True,
        db_path=str(tmp_path / "test.db"),
        storage_path=tmp_path / "storage",
        cache_enabled=False,
        llm_api_key="test-key",
        llm_model="openai/gpt-4o-mini",
        embedding_model="openai/text-embedding-3-small",
    )


@pytest_asyncio.fixture
async def knowledge_item_repo() -> AsyncGenerator[BaseRepository[KnowledgeItem], None]:
    repo = BaseRepository[KnowledgeItem](KnowledgeItem)
    yield repo


@pytest_asyncio.fixture
async def prompt_repo() -> AsyncGenerator[BaseRepository[Prompt], None]:
    repo = BaseRepository[Prompt](Prompt)
    yield repo


@pytest.fixture
def sample_knowledge_item_data() -> dict:
    return {
        "raw_text": "Test knowledge item content",
        "source": "test",
        "tags": ["test", "sample"],
        "links": [],
    }


@pytest.fixture
def sample_prompt_data() -> dict:
    return {
        "name": "test_prompt",
        "content": "This is a test prompt.",
        "description": "Test prompt description",
        "category": "test",
    }


@pytest.fixture
def sample_uuid() -> str:
    return str(uuid4())
