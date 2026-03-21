import base64
import json
from collections.abc import Callable, Sequence
from datetime import datetime
from typing import Any

from sqlalchemy import and_, desc, or_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.application.audit.dto import AuditCursorDTO, AuditEventDTO, AuditEventPageDTO
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
        success: bool | None = None,
        channel: str | None = None,
        provider: str | None = None,
        tool_name: str | None = None,
        workflow_type: str | None = None,
        recorded_after: datetime | None = None,
        recorded_before: datetime | None = None,
        cursor: str | None = None,
        limit: int = 50,
    ) -> AuditEventPageDTO:
        normalized_kind = kind.lower()
        if normalized_kind == "message":
            return await self._query_message_events(
                conversation_id=conversation_id,
                session_id=session_id,
                success=success,
                channel=channel,
                recorded_after=recorded_after,
                recorded_before=recorded_before,
                cursor=cursor,
                limit=limit,
            )
        if normalized_kind == "model":
            return await self._query_model_events(
                conversation_id=conversation_id,
                session_id=session_id,
                success=success,
                provider=provider,
                recorded_after=recorded_after,
                recorded_before=recorded_before,
                cursor=cursor,
                limit=limit,
            )
        if normalized_kind == "tool":
            return await self._query_tool_events(
                conversation_id=conversation_id,
                session_id=session_id,
                success=success,
                tool_name=tool_name,
                recorded_after=recorded_after,
                recorded_before=recorded_before,
                cursor=cursor,
                limit=limit,
            )
        if normalized_kind == "workflow":
            return await self._query_workflow_events(
                conversation_id=conversation_id,
                session_id=session_id,
                success=success,
                workflow_type=workflow_type,
                recorded_after=recorded_after,
                recorded_before=recorded_before,
                cursor=cursor,
                limit=limit,
            )
        raise ValueError(f"不支持的审计类型：{kind}")

    async def list_timeline(
        self,
        *,
        conversation_id: str | None = None,
        session_id: str | None = None,
        success: bool | None = None,
        channel: str | None = None,
        provider: str | None = None,
        tool_name: str | None = None,
        workflow_type: str | None = None,
        recorded_after: datetime | None = None,
        recorded_before: datetime | None = None,
        cursor: str | None = None,
        limit: int = 50,
    ) -> AuditEventPageDTO:
        model_page = await self._query_model_events(
            conversation_id=conversation_id,
            session_id=session_id,
            success=success,
            provider=provider,
            recorded_after=recorded_after,
            recorded_before=recorded_before,
            cursor=cursor,
            limit=limit,
        )
        tool_page = await self._query_tool_events(
            conversation_id=conversation_id,
            session_id=session_id,
            success=success,
            tool_name=tool_name,
            recorded_after=recorded_after,
            recorded_before=recorded_before,
            cursor=cursor,
            limit=limit,
        )
        message_page = await self._query_message_events(
            conversation_id=conversation_id,
            session_id=session_id,
            success=success,
            channel=channel,
            recorded_after=recorded_after,
            recorded_before=recorded_before,
            cursor=cursor,
            limit=limit,
        )
        workflow_page = await self._query_workflow_events(
            conversation_id=conversation_id,
            session_id=session_id,
            success=success,
            workflow_type=workflow_type,
            recorded_after=recorded_after,
            recorded_before=recorded_before,
            cursor=cursor,
            limit=limit,
        )

        items = sorted(
            [
                *message_page.items,
                *model_page.items,
                *tool_page.items,
                *workflow_page.items,
            ],
            key=lambda item: (item.recorded_at, item.event_id),
            reverse=True,
        )
        page_items = items[:limit]

        has_more = (
            any(
                page.next_cursor is not None
                for page in (message_page, model_page, tool_page, workflow_page)
            )
            or len(items) > limit
        )

        if not has_more or not page_items:
            return AuditEventPageDTO(items=page_items, next_cursor=None)

        last_item = page_items[-1]
        next_cursor = encode_audit_cursor(
            recorded_at=datetime.fromisoformat(last_item.recorded_at),
            event_id=last_item.event_id,
        )
        return AuditEventPageDTO(items=page_items, next_cursor=next_cursor)

    async def _query_message_events(
        self,
        *,
        conversation_id: str | None,
        session_id: str | None,
        success: bool | None,
        channel: str | None,
        recorded_after: datetime | None,
        recorded_before: datetime | None,
        cursor: str | None,
        limit: int,
    ) -> AuditEventPageDTO:
        async with self.session_factory() as session:
            statement = select(MessageEventLogModel).order_by(
                desc(MessageEventLogModel.recorded_at),
                desc(MessageEventLogModel.event_id),
            )
            statement = _apply_common_filters(
                statement=statement,
                conversation_column=MessageEventLogModel.conversation_id,
                session_column=MessageEventLogModel.session_id,
                recorded_at_column=MessageEventLogModel.recorded_at,
                event_id_column=MessageEventLogModel.event_id,
                conversation_id=conversation_id,
                session_id=session_id,
                success_column=MessageEventLogModel.success,
                success=success,
                recorded_after=recorded_after,
                recorded_before=recorded_before,
                cursor=cursor,
            )
            if channel:
                statement = statement.where(MessageEventLogModel.channel == channel)
            rows = (await session.execute(statement.limit(limit + 1))).scalars().all()
            page_rows = rows[:limit]
            items = [
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
                for row in page_rows
            ]
            return AuditEventPageDTO(
                items=items,
                next_cursor=_build_next_cursor(
                    page_rows=page_rows,
                    rows=rows,
                    limit=limit,
                    event_id_getter=lambda row: row.event_id,
                ),
            )

    async def _query_model_events(
        self,
        *,
        conversation_id: str | None,
        session_id: str | None,
        success: bool | None,
        provider: str | None,
        recorded_after: datetime | None,
        recorded_before: datetime | None,
        cursor: str | None,
        limit: int,
    ) -> AuditEventPageDTO:
        async with self.session_factory() as session:
            statement = select(ModelInvocationLogModel).order_by(
                desc(ModelInvocationLogModel.recorded_at),
                desc(ModelInvocationLogModel.invocation_id),
            )
            statement = _apply_common_filters(
                statement=statement,
                conversation_column=ModelInvocationLogModel.conversation_id,
                session_column=ModelInvocationLogModel.session_id,
                recorded_at_column=ModelInvocationLogModel.recorded_at,
                event_id_column=ModelInvocationLogModel.invocation_id,
                conversation_id=conversation_id,
                session_id=session_id,
                success_column=ModelInvocationLogModel.success,
                success=success,
                recorded_after=recorded_after,
                recorded_before=recorded_before,
                cursor=cursor,
            )
            if provider:
                statement = statement.where(ModelInvocationLogModel.provider == provider)
            rows = (await session.execute(statement.limit(limit + 1))).scalars().all()
            page_rows = rows[:limit]
            items = [
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
                for row in page_rows
            ]
            return AuditEventPageDTO(
                items=items,
                next_cursor=_build_next_cursor(
                    page_rows=page_rows,
                    rows=rows,
                    limit=limit,
                    event_id_getter=lambda row: row.invocation_id,
                ),
            )

    async def _query_tool_events(
        self,
        *,
        conversation_id: str | None,
        session_id: str | None,
        success: bool | None,
        tool_name: str | None,
        recorded_after: datetime | None,
        recorded_before: datetime | None,
        cursor: str | None,
        limit: int,
    ) -> AuditEventPageDTO:
        async with self.session_factory() as session:
            statement = select(ToolInvocationLogModel).order_by(
                desc(ToolInvocationLogModel.recorded_at),
                desc(ToolInvocationLogModel.invocation_id),
            )
            statement = _apply_common_filters(
                statement=statement,
                conversation_column=ToolInvocationLogModel.conversation_id,
                session_column=ToolInvocationLogModel.session_id,
                recorded_at_column=ToolInvocationLogModel.recorded_at,
                event_id_column=ToolInvocationLogModel.invocation_id,
                conversation_id=conversation_id,
                session_id=session_id,
                success_column=ToolInvocationLogModel.success,
                success=success,
                recorded_after=recorded_after,
                recorded_before=recorded_before,
                cursor=cursor,
            )
            if tool_name:
                statement = statement.where(ToolInvocationLogModel.tool_name == tool_name)
            rows = (await session.execute(statement.limit(limit + 1))).scalars().all()
            page_rows = rows[:limit]
            items = [
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
                for row in page_rows
            ]
            return AuditEventPageDTO(
                items=items,
                next_cursor=_build_next_cursor(
                    page_rows=page_rows,
                    rows=rows,
                    limit=limit,
                    event_id_getter=lambda row: row.invocation_id,
                ),
            )

    async def _query_workflow_events(
        self,
        *,
        conversation_id: str | None,
        session_id: str | None,
        success: bool | None,
        workflow_type: str | None,
        recorded_after: datetime | None,
        recorded_before: datetime | None,
        cursor: str | None,
        limit: int,
    ) -> AuditEventPageDTO:
        async with self.session_factory() as session:
            statement = select(WorkflowEventLogModel).order_by(
                desc(WorkflowEventLogModel.recorded_at),
                desc(WorkflowEventLogModel.event_id),
            )
            statement = _apply_common_filters(
                statement=statement,
                conversation_column=WorkflowEventLogModel.conversation_id,
                session_column=WorkflowEventLogModel.session_id,
                recorded_at_column=WorkflowEventLogModel.recorded_at,
                event_id_column=WorkflowEventLogModel.event_id,
                conversation_id=conversation_id,
                session_id=session_id,
                success_column=WorkflowEventLogModel.success,
                success=success,
                recorded_after=recorded_after,
                recorded_before=recorded_before,
                cursor=cursor,
            )
            if workflow_type:
                statement = statement.where(WorkflowEventLogModel.workflow_type == workflow_type)
            rows = (await session.execute(statement.limit(limit + 1))).scalars().all()
            page_rows = rows[:limit]
            items = [
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
                for row in page_rows
            ]
            return AuditEventPageDTO(
                items=items,
                next_cursor=_build_next_cursor(
                    page_rows=page_rows,
                    rows=rows,
                    limit=limit,
                    event_id_getter=lambda row: row.event_id,
                ),
            )


def _apply_common_filters(
    *,
    statement: Any,
    conversation_column: Any,
    session_column: Any,
    success_column: Any,
    recorded_at_column: Any,
    event_id_column: Any,
    conversation_id: str | None,
    session_id: str | None,
    success: bool | None,
    recorded_after: datetime | None,
    recorded_before: datetime | None,
    cursor: str | None,
) -> Any:
    if conversation_id:
        statement = statement.where(conversation_column == conversation_id)
    if session_id:
        statement = statement.where(session_column == session_id)
    if success is not None:
        statement = statement.where(success_column == success)
    if recorded_after:
        statement = statement.where(recorded_at_column >= recorded_after)
    if recorded_before:
        statement = statement.where(recorded_at_column <= recorded_before)
    if cursor:
        decoded = decode_audit_cursor(cursor)
        recorded_at = datetime.fromisoformat(decoded.recorded_at)
        statement = statement.where(
            or_(
                recorded_at_column < recorded_at,
                and_(
                    recorded_at_column == recorded_at,
                    event_id_column < decoded.event_id,
                ),
            )
        )
    return statement


def encode_audit_cursor(*, recorded_at: datetime, event_id: str) -> str:
    payload = {
        "recorded_at": recorded_at.isoformat(),
        "event_id": event_id,
    }
    return base64.urlsafe_b64encode(json.dumps(payload).encode("utf-8")).decode("utf-8")


def decode_audit_cursor(cursor: str) -> AuditCursorDTO:
    payload = json.loads(base64.urlsafe_b64decode(cursor.encode("utf-8")).decode("utf-8"))
    return AuditCursorDTO(
        recorded_at=payload["recorded_at"],
        event_id=payload["event_id"],
    )


def _build_next_cursor(
    *,
    page_rows: Sequence[Any],
    rows: Sequence[Any],
    limit: int,
    event_id_getter: Callable[[Any], str],
) -> str | None:
    if len(rows) <= limit or not page_rows:
        return None
    last_row = page_rows[-1]
    return encode_audit_cursor(
        recorded_at=last_row.recorded_at,
        event_id=event_id_getter(last_row),
    )
