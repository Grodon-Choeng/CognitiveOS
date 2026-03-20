import json
import logging
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.infrastructure.db.models.tool_invocation import ToolInvocationLogModel
from app.infrastructure.tools.mcp.protocol import ToolCall, ToolResult
from app.infrastructure.types import JSONObject


@dataclass(slots=True, frozen=True)
class ToolInvocationRecord:
    invocation_id: str
    recorded_at: str
    tool_name: str
    session_id: str | None
    conversation_id: str | None
    trace_id: str | None
    chain_id: str | None
    request_id: str | None
    latency_ms: float
    timeout_seconds: float | None
    retry_limit: int
    success: bool = True
    error_code: str | None = None
    error_message: str | None = None
    raw_input: JSONObject = field(default_factory=dict)
    raw_output: JSONObject = field(default_factory=dict)
    metadata: JSONObject = field(default_factory=dict)

    @classmethod
    def create(
        cls,
        *,
        tool_name: str,
        session_id: str | None,
        conversation_id: str | None,
        trace_id: str | None,
        chain_id: str | None,
        request_id: str | None,
        latency_ms: float,
        timeout_seconds: float | None,
        retry_limit: int,
        success: bool = True,
        error_code: str | None = None,
        error_message: str | None = None,
        raw_input: JSONObject | None = None,
        raw_output: JSONObject | None = None,
        metadata: JSONObject | None = None,
    ) -> "ToolInvocationRecord":
        return cls(
            invocation_id=str(uuid4()),
            recorded_at=datetime.now(UTC).isoformat(),
            tool_name=tool_name,
            session_id=session_id,
            conversation_id=conversation_id,
            trace_id=trace_id,
            chain_id=chain_id,
            request_id=request_id,
            latency_ms=latency_ms,
            timeout_seconds=timeout_seconds,
            retry_limit=retry_limit,
            success=success,
            error_code=error_code,
            error_message=error_message,
            raw_input=raw_input or {},
            raw_output=raw_output or {},
            metadata=metadata or {},
        )


class ToolInvocationRecorder(Protocol):
    async def record(self, record: ToolInvocationRecord) -> None: ...


class JsonlToolInvocationRecorder:
    def __init__(self, path: str, enabled: bool = True) -> None:
        self.path = Path(path)
        self.enabled = enabled
        self.logger = logging.getLogger(__name__)

    async def record(self, record: ToolInvocationRecord) -> None:
        if not self.enabled:
            return

        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = asdict(record)
        with self.path.open("a", encoding="utf-8") as file_handle:
            file_handle.write(json.dumps(payload, ensure_ascii=False) + "\n")

        self.logger.info(
            "工具调用记录已写入。",
            extra={
                "invocation_id": record.invocation_id,
                "tool_name": record.tool_name,
                "success": record.success,
            },
        )


class DatabaseToolInvocationRecorder:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        enabled: bool = True,
    ) -> None:
        self.session_factory = session_factory
        self.enabled = enabled
        self.logger = logging.getLogger(__name__)

    async def record(self, record: ToolInvocationRecord) -> None:
        if not self.enabled:
            return

        async with self.session_factory() as session:
            session.add(_build_tool_invocation_log_model(record))
            await session.commit()

        self.logger.info(
            "工具调用记录已写入数据库。",
            extra={
                "invocation_id": record.invocation_id,
                "tool_name": record.tool_name,
                "success": record.success,
            },
        )


class MultiToolInvocationRecorder:
    def __init__(self, recorders: list[ToolInvocationRecorder]) -> None:
        self.recorders = recorders

    async def record(self, record: ToolInvocationRecord) -> None:
        for recorder in self.recorders:
            await recorder.record(record)


def build_tool_raw_input(call: ToolCall) -> JSONObject:
    return {
        "name": call.name,
        "arguments": call.arguments,
        "metadata": call.metadata,
        "options": {
            "timeout_seconds": call.options.timeout_seconds,
            "retry_limit": call.options.retry_limit,
            "trace_metadata": call.options.trace_metadata,
        },
    }


def build_tool_raw_output(result: ToolResult) -> JSONObject:
    return {
        "content": result.content,
        "is_error": result.is_error,
        "error": {
            "code": result.error.code,
            "message": result.error.message,
        }
        if result.error
        else {},
        "metadata": result.metadata,
    }


def _build_tool_invocation_log_model(
    record: ToolInvocationRecord,
) -> ToolInvocationLogModel:
    return ToolInvocationLogModel(
        invocation_id=record.invocation_id,
        recorded_at=datetime.fromisoformat(record.recorded_at),
        tool_name=record.tool_name,
        session_id=record.session_id,
        conversation_id=record.conversation_id,
        trace_id=record.trace_id,
        chain_id=record.chain_id,
        request_id=record.request_id,
        latency_ms=record.latency_ms,
        timeout_seconds=record.timeout_seconds,
        retry_limit=record.retry_limit,
        success=record.success,
        error_code=record.error_code,
        error_message=record.error_message,
        raw_input=record.raw_input,
        raw_output=record.raw_output,
        metadata_json=record.metadata,
    )
