import json
from pathlib import Path
from typing import cast

import pytest

from app.config.settings import Settings
from app.infrastructure.db.session import get_session_factory
from app.infrastructure.tools.mcp.protocol import (
    ToolCall,
    ToolExecutionOptions,
    ToolResult,
)
from app.infrastructure.tools.runtime.executor import RecordingToolRuntime
from app.infrastructure.types import JSONObject
from app.observability.tool_invocations import (
    DatabaseToolInvocationRecorder,
    JsonlToolInvocationRecorder,
    MultiToolInvocationRecorder,
    ToolInvocationRecord,
)


class FakeToolRuntime:
    async def execute(
        self,
        call: ToolCall,
        options: ToolExecutionOptions | None = None,
    ) -> ToolResult:
        _ = (call, options)
        return ToolResult(
            content="执行成功",
            metadata={"duration_hint_ms": 12},
        )


class FailingToolRuntime:
    async def execute(
        self,
        call: ToolCall,
        options: ToolExecutionOptions | None = None,
    ) -> ToolResult:
        _ = (call, options)
        raise RuntimeError("工具执行失败")


class FakeDatabaseRecorder:
    def __init__(self) -> None:
        self.records: list[ToolInvocationRecord] = []

    async def record(self, record: ToolInvocationRecord) -> None:
        self.records.append(record)


def read_first_record(path: Path) -> JSONObject:
    lines = path.read_text(encoding="utf-8").splitlines()
    return cast(JSONObject, json.loads(lines[0]))


@pytest.mark.asyncio
async def test_recording_tool_runtime_records_success(tmp_path: Path) -> None:
    log_path = tmp_path / "tool_invocations.jsonl"
    recorder = JsonlToolInvocationRecorder(str(log_path))
    runtime = RecordingToolRuntime(FakeToolRuntime(), recorder)

    await runtime.execute(
        ToolCall(
            name="calendar.create_event",
            session_id="session-1",
            conversation_id="conversation-1",
            trace_id="trace-1",
            chain_id="chain-1",
            request_id="request-1",
            arguments={"title": "站会"},
            metadata={"source": "agent"},
            options=ToolExecutionOptions(timeout_seconds=5.0, retry_limit=2),
        )
    )

    record = read_first_record(log_path)
    assert record["tool_name"] == "calendar.create_event"
    assert record["session_id"] == "session-1"
    assert record["success"] is True
    raw_input = cast(JSONObject, record["raw_input"])
    raw_output = cast(JSONObject, record["raw_output"])
    assert raw_input["name"] == "calendar.create_event"
    assert raw_output["content"] == "执行成功"


@pytest.mark.asyncio
async def test_recording_tool_runtime_records_failure(tmp_path: Path) -> None:
    log_path = tmp_path / "tool_invocations.jsonl"
    recorder = JsonlToolInvocationRecorder(str(log_path))
    runtime = RecordingToolRuntime(FailingToolRuntime(), recorder)

    with pytest.raises(RuntimeError):
        await runtime.execute(
            ToolCall(
                name="calendar.create_event",
                arguments={"title": "站会"},
            )
        )

    record = read_first_record(log_path)
    assert record["success"] is False
    assert record["error_code"] == "RuntimeError"
    assert record["error_message"] == "工具执行失败"


@pytest.mark.asyncio
async def test_multi_tool_invocation_recorder_writes_to_both_channels(
    tmp_path: Path,
) -> None:
    log_path = tmp_path / "tool_invocations.jsonl"
    jsonl_recorder = JsonlToolInvocationRecorder(str(log_path))
    database_recorder = FakeDatabaseRecorder()
    recorder = MultiToolInvocationRecorder([database_recorder, jsonl_recorder])

    await recorder.record(
        ToolInvocationRecord.create(
            tool_name="calendar.create_event",
            session_id="session-1",
            conversation_id="conversation-1",
            trace_id="trace-1",
            chain_id="chain-1",
            request_id="request-1",
            latency_ms=12.5,
            timeout_seconds=5.0,
            retry_limit=2,
            raw_input={"title": "站会"},
            raw_output={"content": "执行成功"},
        )
    )

    jsonl_record = read_first_record(log_path)
    assert jsonl_record["tool_name"] == "calendar.create_event"
    assert len(database_recorder.records) == 1


def test_database_tool_invocation_recorder_can_be_constructed() -> None:
    settings = Settings(
        database_url="postgresql+asyncpg://cognitiveos:cognitiveos@localhost:5432/cognitiveos"
    )
    session_factory = get_session_factory(settings)
    recorder = DatabaseToolInvocationRecorder(session_factory=session_factory)

    assert recorder.enabled is True
