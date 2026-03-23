import pytest
from fastapi import FastAPI

from app.bootstrap.http import create_application


@pytest.fixture
def app() -> FastAPI:
    return create_application()
