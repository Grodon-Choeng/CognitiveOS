import json
from pathlib import Path
from typing import cast

import pytest

from app.config.settings import Settings
from app.infrastructure.db.session import get_session_factory
from app.infrastructure.integrations.messaging.base import (
    MessageTarget,
    OutboundMessage,
    SendResult,
)
from app.infrastructure.integrations.messaging.recording_adapter import RecordingMessagingAdapter
from app.infrastructure.types import JSONObject
from app.observability.message_events import (
    DatabaseMessageEventRecorder,
    JsonlMessageEventRecorder,
    MessageEventRecord,
    MultiMessageEventRecorder,
)


class FakeMessagingAdapter:
    async def send_message(
        self,
        target: MessageTarget,
        content: OutboundMessage,
    ) -> SendResult:
        _ = (target, content)
        return SendResult(
            accepted=True,
            external_message_id="om_sent_1",
            metadata={"provider": "feishu", "adapter": "feishu"},
        )


class FakeFailingMessagingAdapter:
    async def send_message(
        self,
        target: MessageTarget,
        content: OutboundMessage,
    ) -> SendResult:
        _ = (target, content)
        raise RuntimeError("发送失败")


class FakeDatabaseRecorder:
    def __init__(self) -> None:
        self.records: list[MessageEventRecord] = []

    async def record(self, record: MessageEventRecord) -> None:
        self.records.append(record)


def read_first_record(path: Path) -> JSONObject:
    lines = path.read_text(encoding="utf-8").splitlines()
    return cast(JSONObject, json.loads(lines[0]))


@pytest.mark.asyncio
async def test_recording_messaging_adapter_records_outbound_success(tmp_path: Path) -> None:
    log_path = tmp_path / "message_events.jsonl"
    recorder = JsonlMessageEventRecorder(str(log_path))
    adapter = RecordingMessagingAdapter(FakeMessagingAdapter(), recorder)

    await adapter.send_message(
        MessageTarget(channel="feishu", recipient_id="ou_123"),
        OutboundMessage(
            text="你好",
            metadata={
                "conversation_id": "conversation-1",
                "session_id": "session-1",
                "chat_id": "oc_123",
                "thread_id": "ot_123",
            },
        ),
    )

    record = read_first_record(log_path)
    assert record["direction"] == "outbound"
    assert record["channel"] == "feishu"
    assert record["adapter_name"] == "feishu"
    assert record["external_message_id"] == "om_sent_1"
    assert record["conversation_id"] == "conversation-1"
    assert record["session_id"] == "session-1"
    assert isinstance(record["latency_ms"], float)


@pytest.mark.asyncio
async def test_recording_messaging_adapter_records_outbound_failure(tmp_path: Path) -> None:
    log_path = tmp_path / "message_events.jsonl"
    recorder = JsonlMessageEventRecorder(str(log_path))
    adapter = RecordingMessagingAdapter(FakeFailingMessagingAdapter(), recorder)

    with pytest.raises(RuntimeError):
        await adapter.send_message(
            MessageTarget(channel="feishu", recipient_id="ou_123"),
            OutboundMessage(text="你好"),
        )

    record = read_first_record(log_path)
    assert record["direction"] == "outbound"
    assert record["adapter_name"] == "FakeFailingMessagingAdapter"
    assert record["success"] is False
    assert record["error_code"] == "RuntimeError"
    assert isinstance(record["latency_ms"], float)


@pytest.mark.asyncio
async def test_multi_message_event_recorder_writes_to_both_channels(tmp_path: Path) -> None:
    log_path = tmp_path / "message_events.jsonl"
    jsonl_recorder = JsonlMessageEventRecorder(str(log_path))
    database_recorder = FakeDatabaseRecorder()
    recorder = MultiMessageEventRecorder([database_recorder, jsonl_recorder])

    await recorder.record(
        MessageEventRecord.create(
            direction="inbound",
            channel="feishu",
            message_type="text",
            user_identity="ou_123",
            external_message_id="om_1",
            root_message_id=None,
            parent_message_id=None,
            chat_id="oc_123",
            thread_id="ot_123",
            conversation_id="conversation-1",
            session_id="session-1",
            trace_id=None,
            chain_id=None,
            request_id=None,
            adapter_name=None,
            latency_ms=12.5,
            text="你好",
            raw_payload={"text": "你好"},
        )
    )

    assert len(database_recorder.records) == 1
    jsonl_record = read_first_record(log_path)
    assert jsonl_record["direction"] == "inbound"
    assert jsonl_record["latency_ms"] == 12.5


def test_database_message_event_recorder_can_be_constructed() -> None:
    settings = Settings(
        database_url="postgresql+asyncpg://cognitiveos:cognitiveos@localhost:5432/cognitiveos"
    )
    session_factory = get_session_factory(settings)
    recorder = DatabaseMessageEventRecorder(session_factory=session_factory)

    assert recorder.enabled is True
