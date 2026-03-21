from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.application.audit.dto import AuditEventDTO
from app.infrastructure.db.models.message_event import MessageEventLogModel
from app.infrastructure.db.models.model_invocation import ModelInvocationLogModel
from app.infrastructure.db.models.tool_invocation import ToolInvocationLogModel
from app.infrastructure.db.models.workflow_event import WorkflowEventLogModel


class AuditQueryService:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self.session_factory = session_factory

    async def list_events(
        self,
        *,
        kind: str,
        conversation_id: str | None = None,
        session_id: str | None = None,
        limit: int = 50,
    ) -> list[AuditEventDTO]:
        normalized_kind = kind.lower()
        if normalized_kind == "message":
            return await self._query_message_events(conversation_id, session_id, limit)
        if normalized_kind == "model":
            return await self._query_model_events(conversation_id, session_id, limit)
        if normalized_kind == "tool":
            return await self._query_tool_events(conversation_id, session_id, limit)
        if normalized_kind == "workflow":
            return await self._query_workflow_events(conversation_id, session_id, limit)
        raise ValueError(f"不支持的审计类型：{kind}")

    async def _query_message_events(
        self,
        conversation_id: str | None,
        session_id: str | None,
        limit: int,
    ) -> list[AuditEventDTO]:
        async with self.session_factory() as session:
            statement = select(MessageEventLogModel).order_by(
                desc(MessageEventLogModel.recorded_at)
            )
            if conversation_id:
                statement = statement.where(MessageEventLogModel.conversation_id == conversation_id)
            if session_id:
                statement = statement.where(MessageEventLogModel.session_id == session_id)
            rows = (await session.execute(statement.limit(limit))).scalars().all()
            return [
                AuditEventDTO(
                    kind="message",
                    event_id=row.event_id,
                    recorded_at=row.recorded_at.isoformat(),
                    conversation_id=row.conversation_id,
                    session_id=row.session_id,
                    trace_id=row.trace_id,
                    chain_id=row.chain_id,
                    request_id=row.request_id,
                    success=row.success,
                    summary=f"{row.direction}:{row.channel}:{row.message_type}",
                    payload={
                        "direction": row.direction,
                        "channel": row.channel,
                        "message_type": row.message_type,
                        "text": row.text,
                        "chat_id": row.chat_id,
                        "thread_id": row.thread_id,
                        "external_message_id": row.external_message_id,
                        "metadata": row.metadata_json,
                    },
                )
                for row in rows
            ]

    async def _query_model_events(
        self,
        conversation_id: str | None,
        session_id: str | None,
        limit: int,
    ) -> list[AuditEventDTO]:
        async with self.session_factory() as session:
            statement = select(ModelInvocationLogModel).order_by(
                desc(ModelInvocationLogModel.recorded_at)
            )
            if conversation_id:
                statement = statement.where(
                    ModelInvocationLogModel.conversation_id == conversation_id
                )
            if session_id:
                statement = statement.where(ModelInvocationLogModel.session_id == session_id)
            rows = (await session.execute(statement.limit(limit))).scalars().all()
            return [
                AuditEventDTO(
                    kind="model",
                    event_id=row.invocation_id,
                    recorded_at=row.recorded_at.isoformat(),
                    conversation_id=row.conversation_id,
                    session_id=row.session_id,
                    trace_id=row.trace_id,
                    chain_id=row.chain_id,
                    request_id=row.request_id,
                    success=row.success,
                    summary=f"{row.provider or 'unknown'}:{row.model or 'unknown'}",
                    payload={
                        "operation": row.operation,
                        "model_kind": row.model_kind,
                        "latency_ms": row.latency_ms,
                        "usage": row.usage,
                    },
                )
                for row in rows
            ]

    async def _query_tool_events(
        self,
        conversation_id: str | None,
        session_id: str | None,
        limit: int,
    ) -> list[AuditEventDTO]:
        async with self.session_factory() as session:
            statement = select(ToolInvocationLogModel).order_by(
                desc(ToolInvocationLogModel.recorded_at)
            )
            if conversation_id:
                statement = statement.where(
                    ToolInvocationLogModel.conversation_id == conversation_id
                )
            if session_id:
                statement = statement.where(ToolInvocationLogModel.session_id == session_id)
            rows = (await session.execute(statement.limit(limit))).scalars().all()
            return [
                AuditEventDTO(
                    kind="tool",
                    event_id=row.invocation_id,
                    recorded_at=row.recorded_at.isoformat(),
                    conversation_id=row.conversation_id,
                    session_id=row.session_id,
                    trace_id=row.trace_id,
                    chain_id=row.chain_id,
                    request_id=row.request_id,
                    success=row.success,
                    summary=row.tool_name,
                    payload={
                        "tool_name": row.tool_name,
                        "latency_ms": row.latency_ms,
                        "timeout_seconds": row.timeout_seconds,
                        "retry_limit": row.retry_limit,
                    },
                )
                for row in rows
            ]

    async def _query_workflow_events(
        self,
        conversation_id: str | None,
        session_id: str | None,
        limit: int,
    ) -> list[AuditEventDTO]:
        async with self.session_factory() as session:
            statement = select(WorkflowEventLogModel).order_by(
                desc(WorkflowEventLogModel.recorded_at)
            )
            if conversation_id:
                statement = statement.where(
                    WorkflowEventLogModel.conversation_id == conversation_id
                )
            if session_id:
                statement = statement.where(WorkflowEventLogModel.session_id == session_id)
            rows = (await session.execute(statement.limit(limit))).scalars().all()
            return [
                AuditEventDTO(
                    kind="workflow",
                    event_id=row.event_id,
                    recorded_at=row.recorded_at.isoformat(),
                    conversation_id=row.conversation_id,
                    session_id=row.session_id,
                    trace_id=row.trace_id,
                    chain_id=row.chain_id,
                    request_id=row.request_id,
                    success=row.success,
                    summary=f"{row.workflow_type}:{row.event_type}",
                    payload={
                        "workflow_id": row.workflow_id,
                        "workflow_type": row.workflow_type,
                        "event_type": row.event_type,
                        "message": row.message,
                        "payload": row.payload,
                    },
                )
                for row in rows
            ]
