import json
import logging
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.infrastructure.db.models.workflow_event import WorkflowEventLogModel
from app.infrastructure.types import JSONObject


@dataclass(slots=True, frozen=True)
class WorkflowEventRecord:
    event_id: str
    recorded_at: str
    workflow_id: str
    workflow_type: str
    event_type: str
    conversation_id: str | None
    session_id: str | None
    trace_id: str | None
    chain_id: str | None
    request_id: str | None
    success: bool = True
    message: str | None = None
    payload: JSONObject = field(default_factory=dict)

    @classmethod
    def create(
        cls,
        *,
        workflow_id: str,
        workflow_type: str,
        event_type: str,
        conversation_id: str | None,
        session_id: str | None,
        trace_id: str | None,
        chain_id: str | None,
        request_id: str | None,
        success: bool = True,
        message: str | None = None,
        payload: JSONObject | None = None,
    ) -> "WorkflowEventRecord":
        return cls(
            event_id=str(uuid4()),
            recorded_at=datetime.now(UTC).isoformat(),
            workflow_id=workflow_id,
            workflow_type=workflow_type,
            event_type=event_type,
            conversation_id=conversation_id,
            session_id=session_id,
            trace_id=trace_id,
            chain_id=chain_id,
            request_id=request_id,
            success=success,
            message=message,
            payload=payload or {},
        )


class WorkflowEventRecorder(Protocol):
    async def record(self, record: WorkflowEventRecord) -> None: ...


class JsonlWorkflowEventRecorder:
    def __init__(self, path: str, enabled: bool = True) -> None:
        self.path = Path(path)
        self.enabled = enabled
        self.logger = logging.getLogger(__name__)

    async def record(self, record: WorkflowEventRecord) -> None:
        if not self.enabled:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as file_handle:
            file_handle.write(json.dumps(asdict(record), ensure_ascii=False) + "\n")
        self.logger.info(
            "工作流事件已写入文件。",
            extra={
                "event_id": record.event_id,
                "workflow_id": record.workflow_id,
                "event_type": record.event_type,
            },
        )


class DatabaseWorkflowEventRecorder:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        enabled: bool = True,
    ) -> None:
        self.session_factory = session_factory
        self.enabled = enabled
        self.logger = logging.getLogger(__name__)

    async def record(self, record: WorkflowEventRecord) -> None:
        if not self.enabled:
            return
        async with self.session_factory() as session:
            session.add(_build_workflow_event_model(record))
            await session.commit()
        self.logger.info(
            "工作流事件已写入数据库。",
            extra={
                "event_id": record.event_id,
                "workflow_id": record.workflow_id,
                "event_type": record.event_type,
            },
        )


class MultiWorkflowEventRecorder:
    def __init__(self, recorders: list[WorkflowEventRecorder]) -> None:
        self.recorders = recorders

    async def record(self, record: WorkflowEventRecord) -> None:
        for recorder in self.recorders:
            await recorder.record(record)


def _build_workflow_event_model(record: WorkflowEventRecord) -> WorkflowEventLogModel:
    return WorkflowEventLogModel(
        event_id=record.event_id,
        recorded_at=datetime.fromisoformat(record.recorded_at),
        workflow_id=record.workflow_id,
        workflow_type=record.workflow_type,
        event_type=record.event_type,
        conversation_id=record.conversation_id,
        session_id=record.session_id,
        trace_id=record.trace_id,
        chain_id=record.chain_id,
        request_id=record.request_id,
        success=record.success,
        message=record.message,
        payload=record.payload,
    )
