import json
import logging
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.infrastructure.db.models.model_invocation import ModelInvocationLogModel
from app.infrastructure.types import JSONObject


def build_api_key_suffix(secret: str | None) -> str | None:
    if secret is None:
        return None

    normalized_secret = secret.strip()
    if not normalized_secret:
        return None

    return normalized_secret[-8:]


@dataclass(slots=True, frozen=True)
class ModelInvocationRecord:
    invocation_id: str
    recorded_at: str
    operation: str
    model_kind: str
    provider: str | None
    model: str | None
    api_key_suffix: str | None
    session_id: str | None
    conversation_id: str | None
    trace_id: str | None
    chain_id: str | None
    request_id: str | None
    latency_ms: float
    usage: dict[str, int] = field(default_factory=dict)
    success: bool = True
    error_type: str | None = None
    error_message: str | None = None
    raw_input: JSONObject = field(default_factory=dict)
    raw_output: JSONObject = field(default_factory=dict)
    metadata: JSONObject = field(default_factory=dict)

    @classmethod
    def create(
        cls,
        *,
        operation: str,
        model_kind: str,
        provider: str | None,
        model: str | None,
        api_key_suffix: str | None,
        session_id: str | None,
        conversation_id: str | None,
        trace_id: str | None,
        chain_id: str | None,
        request_id: str | None,
        latency_ms: float,
        usage: dict[str, int] | None = None,
        success: bool = True,
        error_type: str | None = None,
        error_message: str | None = None,
        raw_input: JSONObject | None = None,
        raw_output: JSONObject | None = None,
        metadata: JSONObject | None = None,
    ) -> "ModelInvocationRecord":
        return cls(
            invocation_id=str(uuid4()),
            recorded_at=datetime.now(UTC).isoformat(),
            operation=operation,
            model_kind=model_kind,
            provider=provider,
            model=model,
            api_key_suffix=api_key_suffix,
            session_id=session_id,
            conversation_id=conversation_id,
            trace_id=trace_id,
            chain_id=chain_id,
            request_id=request_id,
            latency_ms=latency_ms,
            usage=usage or {},
            success=success,
            error_type=error_type,
            error_message=error_message,
            raw_input=raw_input or {},
            raw_output=raw_output or {},
            metadata=metadata or {},
        )


class ModelInvocationRecorder(Protocol):
    async def record(self, record: ModelInvocationRecord) -> None: ...


class JsonlModelInvocationRecorder:
    def __init__(self, path: str, enabled: bool = True) -> None:
        self.path = Path(path)
        self.enabled = enabled
        self.logger = logging.getLogger(__name__)

    async def record(self, record: ModelInvocationRecord) -> None:
        if not self.enabled:
            return

        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = asdict(record)
        with self.path.open("a", encoding="utf-8") as file_handle:
            file_handle.write(json.dumps(payload, ensure_ascii=False) + "\n")

        self.logger.info(
            "模型调用记录已写入。",
            extra={
                "invocation_id": record.invocation_id,
                "operation": record.operation,
                "provider": record.provider,
                "model": record.model,
                "success": record.success,
            },
        )


class DatabaseModelInvocationRecorder:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        enabled: bool = True,
    ) -> None:
        self.session_factory = session_factory
        self.enabled = enabled
        self.logger = logging.getLogger(__name__)

    async def record(self, record: ModelInvocationRecord) -> None:
        if not self.enabled:
            return

        async with self.session_factory() as session:
            session.add(_build_model_invocation_log_model(record))
            await session.commit()

        self.logger.info(
            "模型调用记录已写入数据库。",
            extra={
                "invocation_id": record.invocation_id,
                "operation": record.operation,
                "provider": record.provider,
                "model": record.model,
                "success": record.success,
            },
        )


class MultiModelInvocationRecorder:
    def __init__(self, recorders: list[ModelInvocationRecorder]) -> None:
        self.recorders = recorders

    async def record(self, record: ModelInvocationRecord) -> None:
        for recorder in self.recorders:
            await recorder.record(record)


def _build_model_invocation_log_model(
    record: ModelInvocationRecord,
) -> ModelInvocationLogModel:
    return ModelInvocationLogModel(
        invocation_id=record.invocation_id,
        recorded_at=datetime.fromisoformat(record.recorded_at),
        operation=record.operation,
        model_kind=record.model_kind,
        provider=record.provider,
        model=record.model,
        api_key_suffix=record.api_key_suffix,
        session_id=record.session_id,
        conversation_id=record.conversation_id,
        trace_id=record.trace_id,
        chain_id=record.chain_id,
        request_id=record.request_id,
        latency_ms=record.latency_ms,
        success=record.success,
        error_type=record.error_type,
        error_message=record.error_message,
        usage=record.usage,
        raw_input=record.raw_input,
        raw_output=record.raw_output,
        metadata_json=record.metadata,
    )
