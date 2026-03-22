from dataclasses import dataclass
from datetime import UTC, datetime

from fastapi.testclient import TestClient

from app.api.http.deps.services import get_memory_service
from app.application.memory.commands import CreateMemoryCommand
from app.application.memory.dto import MemoryDTO, MemoryListDTO
from app.application.memory.errors import MemoryNotFoundError
from app.main import app


@dataclass
class FakeMemoryService:
    async def create_memory(self, command: CreateMemoryCommand) -> MemoryDTO:
        _ = command
        return MemoryDTO(
            memory_id="00000000-0000-0000-0000-000000000001",
            content="用户偏好：早上九点提醒",
            created_at=datetime(2026, 3, 22, 9, 0, tzinfo=UTC),
            conversation_id="conversation-1",
            session_id="session-1",
        )

    async def get_memory(self, memory_id: str) -> MemoryDTO:
        if memory_id == "missing":
            raise MemoryNotFoundError("记忆不存在：missing")
        return MemoryDTO(
            memory_id="00000000-0000-0000-0000-000000000001",
            content="用户偏好：早上九点提醒",
            created_at=datetime(2026, 3, 22, 9, 0, tzinfo=UTC),
            conversation_id="conversation-1",
            session_id="session-1",
        )

    async def list_memories(self, query: object) -> MemoryListDTO:
        _ = query
        return MemoryListDTO(
            items=[
                MemoryDTO(
                    memory_id="00000000-0000-0000-0000-000000000001",
                    content="用户偏好：早上九点提醒",
                    created_at=datetime(2026, 3, 22, 9, 0, tzinfo=UTC),
                    conversation_id="conversation-1",
                    session_id="session-1",
                )
            ]
        )


def override_memory_service() -> FakeMemoryService:
    return FakeMemoryService()


def test_create_memory_route_returns_structured_response() -> None:
    app.dependency_overrides[get_memory_service] = override_memory_service

    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/v1/memories",
                json={"content": "用户偏好：早上九点提醒"},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["memory_id"] == "00000000-0000-0000-0000-000000000001"


def test_list_memories_route_returns_structured_response() -> None:
    app.dependency_overrides[get_memory_service] = override_memory_service

    try:
        with TestClient(app) as client:
            response = client.get("/api/v1/memories", params={"conversation_id": "conversation-1"})
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert len(response.json()["items"]) == 1


def test_get_memory_route_returns_structured_response() -> None:
    app.dependency_overrides[get_memory_service] = override_memory_service

    try:
        with TestClient(app) as client:
            response = client.get("/api/v1/memories/00000000-0000-0000-0000-000000000001")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["content"] == "用户偏好：早上九点提醒"


def test_get_memory_route_returns_404_when_missing() -> None:
    app.dependency_overrides[get_memory_service] = override_memory_service

    try:
        with TestClient(app) as client:
            response = client.get("/api/v1/memories/missing")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 404
