from dataclasses import dataclass
from datetime import UTC, datetime

from fastapi.testclient import TestClient

from app.api.http.deps.services import get_task_service
from app.application.tasks.commands import CancelTaskCommand, CompleteTaskCommand, CreateTaskCommand
from app.application.tasks.dto import TaskDTO, TaskListDTO
from app.application.tasks.errors import TaskNotFoundError
from app.main import app


@dataclass
class FakeTaskService:
    async def create_task(self, command: CreateTaskCommand) -> TaskDTO:
        _ = command
        return TaskDTO(
            task_id="00000000-0000-0000-0000-000000000001",
            title="整理今天的会议纪要",
            created_at=datetime(2026, 3, 22, 9, 0, tzinfo=UTC),
            status="pending",
            conversation_id="conversation-1",
            session_id="session-1",
            completed_at=None,
        )

    async def get_task(self, task_id: str) -> TaskDTO:
        if task_id == "missing":
            raise TaskNotFoundError("任务不存在：missing")
        return TaskDTO(
            task_id="00000000-0000-0000-0000-000000000001",
            title="整理今天的会议纪要",
            created_at=datetime(2026, 3, 22, 9, 0, tzinfo=UTC),
            status="pending",
            conversation_id="conversation-1",
            session_id="session-1",
            completed_at=None,
        )

    async def list_tasks(self, query: object) -> TaskListDTO:
        _ = query
        return TaskListDTO(
            items=[
                TaskDTO(
                    task_id="00000000-0000-0000-0000-000000000001",
                    title="整理今天的会议纪要",
                    created_at=datetime(2026, 3, 22, 9, 0, tzinfo=UTC),
                    status="pending",
                    conversation_id="conversation-1",
                    session_id="session-1",
                    completed_at=None,
                )
            ]
        )

    async def complete_task(self, command: CompleteTaskCommand) -> TaskDTO:
        _ = command
        return TaskDTO(
            task_id="00000000-0000-0000-0000-000000000001",
            title="整理今天的会议纪要",
            created_at=datetime(2026, 3, 22, 9, 0, tzinfo=UTC),
            status="completed",
            conversation_id="conversation-1",
            session_id="session-1",
            completed_at=datetime(2026, 3, 22, 10, 0, tzinfo=UTC),
        )

    async def cancel_task(self, command: CancelTaskCommand) -> TaskDTO:
        _ = command
        return TaskDTO(
            task_id="00000000-0000-0000-0000-000000000001",
            title="整理今天的会议纪要",
            created_at=datetime(2026, 3, 22, 9, 0, tzinfo=UTC),
            status="canceled",
            conversation_id="conversation-1",
            session_id="session-1",
            completed_at=None,
        )


def override_task_service() -> FakeTaskService:
    return FakeTaskService()


def test_create_task_route_returns_structured_response() -> None:
    app.dependency_overrides[get_task_service] = override_task_service

    try:
        with TestClient(app) as client:
            response = client.post("/api/v1/tasks", json={"title": "整理今天的会议纪要"})
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["status"] == "pending"


def test_list_tasks_route_returns_structured_response() -> None:
    app.dependency_overrides[get_task_service] = override_task_service

    try:
        with TestClient(app) as client:
            response = client.get("/api/v1/tasks", params={"conversation_id": "conversation-1"})
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert len(response.json()["items"]) == 1


def test_get_task_route_returns_structured_response() -> None:
    app.dependency_overrides[get_task_service] = override_task_service

    try:
        with TestClient(app) as client:
            response = client.get("/api/v1/tasks/00000000-0000-0000-0000-000000000001")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["title"] == "整理今天的会议纪要"


def test_get_task_route_returns_404_when_missing() -> None:
    app.dependency_overrides[get_task_service] = override_task_service

    try:
        with TestClient(app) as client:
            response = client.get("/api/v1/tasks/missing")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 404


def test_complete_task_route_returns_structured_response() -> None:
    app.dependency_overrides[get_task_service] = override_task_service

    try:
        with TestClient(app) as client:
            response = client.post("/api/v1/tasks/00000000-0000-0000-0000-000000000001/complete")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["status"] == "completed"


def test_cancel_task_route_returns_structured_response() -> None:
    app.dependency_overrides[get_task_service] = override_task_service

    try:
        with TestClient(app) as client:
            response = client.post("/api/v1/tasks/00000000-0000-0000-0000-000000000001/cancel")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["status"] == "canceled"
