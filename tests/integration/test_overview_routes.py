from dataclasses import dataclass
from datetime import UTC, datetime

from fastapi.testclient import TestClient

from app.api.http.deps.services import get_overview_service
from app.application.memory.dto import MemoryDTO
from app.application.overview.dto import OverviewDTO
from app.application.overview.queries import GetOverviewQuery
from app.application.reminders.dto import ReminderDTO
from app.application.tasks.dto import TaskDTO
from app.main import app


@dataclass
class FakeOverviewService:
    async def get_overview(self, query: GetOverviewQuery) -> OverviewDTO:
        _ = query
        return OverviewDTO(
            conversation_id="conversation-1",
            session_id="session-1",
            pending_reminders=[
                ReminderDTO(
                    reminder_id="r-1",
                    text="早上九点打卡",
                    remind_at=datetime(2026, 3, 23, 9, 0, tzinfo=UTC),
                    timezone="Asia/Shanghai",
                    status="pending",
                    conversation_id="conversation-1",
                    session_id="session-1",
                    workflow_id="reminder:r-1",
                )
            ],
            pending_tasks=[
                TaskDTO(
                    task_id="t-1",
                    title="整理会议纪要",
                    created_at=datetime(2026, 3, 22, 9, 0, tzinfo=UTC),
                    status="pending",
                    conversation_id="conversation-1",
                    session_id="session-1",
                    completed_at=None,
                )
            ],
            active_memories=[
                MemoryDTO(
                    memory_id="m-1",
                    content="用户喜欢早上九点提醒",
                    created_at=datetime(2026, 3, 22, 8, 0, tzinfo=UTC),
                    status="active",
                    conversation_id="conversation-1",
                    session_id="session-1",
                    archived_at=None,
                )
            ],
        )


def override_overview_service() -> FakeOverviewService:
    return FakeOverviewService()


def test_get_overview_route_returns_structured_response() -> None:
    app.dependency_overrides[get_overview_service] = override_overview_service

    try:
        with TestClient(app) as client:
            response = client.get("/api/v1/overview", params={"conversation_id": "conversation-1"})
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["conversation_id"] == "conversation-1"
    assert body["pending_reminders"][0]["reminder_id"] == "r-1"
    assert body["pending_tasks"][0]["task_id"] == "t-1"
    assert body["active_memories"][0]["memory_id"] == "m-1"
