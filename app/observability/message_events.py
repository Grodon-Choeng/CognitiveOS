import json
import logging
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.infrastructure.db.models.message_event import MessageEventLogModel
from app.infrastructure.types import JSONObject


@dataclass(slots=True, frozen=True)
class MessageEventRecord:
    event_id: str
    recorded_at: str
    direction: str
    channel: str
    message_type: str
    user_identity: str | None
    external_message_id: str | None
    root_message_id: str | None
    parent_message_id: str | None
    chat_id: str | None
    thread_id: str | None
    conversation_id: str | None
    session_id: str | None
    trace_id: str | None
    chain_id: str | None
    request_id: str | None
    text: str | None
    success: bool = True
    error_code: str | None = None
    error_message: str | None = None
    raw_payload: JSONObject = field(default_factory=dict)
    metadata: JSONObject = field(default_factory=dict)

    @classmethod
    def create(
        cls,
        *,
        direction: str,
        channel: str,
        message_type: str,
        user_identity: str | None,
        external_message_id: str | None,
        root_message_id: str | None,
        parent_message_id: str | None,
        chat_id: str | None,
        thread_id: str | None,
        conversation_id: str | None,
        session_id: str | None,
        trace_id: str | None,
        chain_id: str | None,
        request_id: str | None,
        text: str | None,
        success: bool = True,
        error_code: str | None = None,
        error_message: str | None = None,
        raw_payload: JSONObject | None = None,
        metadata: JSONObject | None = None,
    ) -> "MessageEventRecord":
        return cls(
            event_id=str(uuid4()),
            recorded_at=datetime.now(UTC).isoformat(),
            direction=direction,
            channel=channel,
            message_type=message_type,
            user_identity=user_identity,
            external_message_id=external_message_id,
            root_message_id=root_message_id,
            parent_message_id=parent_message_id,
            chat_id=chat_id,
            thread_id=thread_id,
            conversation_id=conversation_id,
            session_id=session_id,
            trace_id=trace_id,
            chain_id=chain_id,
            request_id=request_id,
            text=text,
            success=success,
            error_code=error_code,
            error_message=error_message,
            raw_payload=raw_payload or {},
            metadata=metadata or {},
        )


class MessageEventRecorder(Protocol):
    async def record(self, record: MessageEventRecord) -> None: ...


class JsonlMessageEventRecorder:
    def __init__(self, path: str, enabled: bool = True) -> None:
        self.path = Path(path)
        self.enabled = enabled
        self.logger = logging.getLogger(__name__)

    async def record(self, record: MessageEventRecord) -> None:
        if not self.enabled:
            return

        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as file_handle:
            file_handle.write(json.dumps(asdict(record), ensure_ascii=False) + "\n")

        self.logger.info(
            "消息事件已写入文件。",
            extra={
                "event_id": record.event_id,
                "direction": record.direction,
                "channel": record.channel,
                "conversation_id": record.conversation_id,
            },
        )


class DatabaseMessageEventRecorder:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        enabled: bool = True,
    ) -> None:
        self.session_factory = session_factory
        self.enabled = enabled
        self.logger = logging.getLogger(__name__)

    async def record(self, record: MessageEventRecord) -> None:
        if not self.enabled:
            return

        async with self.session_factory() as session:
            session.add(_build_message_event_model(record))
            await session.commit()

        self.logger.info(
            "消息事件已写入数据库。",
            extra={
                "event_id": record.event_id,
                "direction": record.direction,
                "channel": record.channel,
                "conversation_id": record.conversation_id,
            },
        )


class MultiMessageEventRecorder:
    def __init__(self, recorders: list[MessageEventRecorder]) -> None:
        self.recorders = recorders

    async def record(self, record: MessageEventRecord) -> None:
        for recorder in self.recorders:
            await recorder.record(record)


def _build_message_event_model(record: MessageEventRecord) -> MessageEventLogModel:
    return MessageEventLogModel(
        event_id=record.event_id,
        recorded_at=datetime.fromisoformat(record.recorded_at),
        direction=record.direction,
        channel=record.channel,
        message_type=record.message_type,
        user_identity=record.user_identity,
        external_message_id=record.external_message_id,
        root_message_id=record.root_message_id,
        parent_message_id=record.parent_message_id,
        chat_id=record.chat_id,
        thread_id=record.thread_id,
        conversation_id=record.conversation_id,
        session_id=record.session_id,
        trace_id=record.trace_id,
        chain_id=record.chain_id,
        request_id=record.request_id,
        text=record.text,
        success=record.success,
        error_code=record.error_code,
        error_message=record.error_message,
        raw_payload=record.raw_payload,
        metadata_json=record.metadata,
    )
