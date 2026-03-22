from dataclasses import dataclass
from datetime import UTC, datetime
from typing import cast

import pytest
from temporalio.client import Client

from app.application.reminders.ports import ReminderDispatchTarget
from app.config.settings import Settings
from app.domain.reminders.entities import Reminder
from app.domain.reminders.value_objects import ReminderId, ReminderSchedule
from app.infrastructure.temporal.gateway import TemporalReminderWorkflowGateway
from app.observability.workflow_events import WorkflowEventRecord


class FakeWorkflowHandle:
    async def signal(self, signal_name: str, reply_text: str) -> None:
        _ = (signal_name, reply_text)


@dataclass
class StartedWorkflowCall:
    workflow_name: str
    workflow_input: object
    workflow_id: str
    task_queue: str


class FakeTemporalClient:
    def __init__(self) -> None:
        self.started_calls: list[StartedWorkflowCall] = []
        self.start_error: Exception | None = None

    async def start_workflow(
        self,
        workflow_name: str,
        workflow_input: object,
        *,
        id: str,
        task_queue: str,
        start_delay: object,
    ) -> None:
        _ = start_delay
        if self.start_error is not None:
            raise self.start_error
        self.started_calls.append(
            StartedWorkflowCall(
                workflow_name=workflow_name,
                workflow_input=workflow_input,
                workflow_id=id,
                task_queue=task_queue,
            )
        )

    def get_workflow_handle(self, workflow_id: str) -> FakeWorkflowHandle:
        _ = workflow_id
        return FakeWorkflowHandle()


class FakeWorkflowEventRecorder:
    def __init__(self) -> None:
        self.records: list[WorkflowEventRecord] = []

    async def record(self, record: WorkflowEventRecord) -> None:
        self.records.append(record)


def build_reminder(*, workflow_id: str | None = None) -> Reminder:
    return Reminder(
        reminder_id=ReminderId.from_string("00000000-0000-0000-0000-000000000001"),
        text="提醒我打卡",
        schedule=ReminderSchedule(
            remind_at=datetime(2026, 3, 20, 9, 0, tzinfo=UTC),
            timezone="Asia/Shanghai",
        ),
        conversation_id="conversation-1",
        session_id="session-1",
        dispatch_channel="console",
        dispatch_recipient_id="user-1",
        workflow_id=workflow_id,
    )


@pytest.mark.asyncio
async def test_temporal_gateway_uses_precomputed_workflow_id_and_records_success() -> None:
    recorder = FakeWorkflowEventRecorder()
    client = FakeTemporalClient()
    gateway = TemporalReminderWorkflowGateway(Settings(), recorder)
    gateway._client = cast(Client, client)

    workflow_id = await gateway.start_reminder(
        reminder=build_reminder(workflow_id="reminder:00000000-0000-0000-0000-000000000001"),
        dispatch_target=ReminderDispatchTarget(channel="console", recipient_id="user-1"),
    )

    assert workflow_id == "reminder:00000000-0000-0000-0000-000000000001"
    assert client.started_calls[0].workflow_id == workflow_id
    assert recorder.records[0].event_type == "workflow_started"
    assert recorder.records[0].success is True


@pytest.mark.asyncio
async def test_temporal_gateway_records_failure_when_start_workflow_fails() -> None:
    recorder = FakeWorkflowEventRecorder()
    client = FakeTemporalClient()
    client.start_error = RuntimeError("Temporal 不可用")
    gateway = TemporalReminderWorkflowGateway(Settings(), recorder)
    gateway._client = cast(Client, client)

    with pytest.raises(RuntimeError):
        await gateway.start_reminder(
            reminder=build_reminder(workflow_id="reminder:00000000-0000-0000-0000-000000000001"),
            dispatch_target=ReminderDispatchTarget(channel="console", recipient_id="user-1"),
        )

    assert recorder.records[0].event_type == "workflow_start_failed"
    assert recorder.records[0].success is False
    assert recorder.records[0].payload["error_type"] == "RuntimeError"
