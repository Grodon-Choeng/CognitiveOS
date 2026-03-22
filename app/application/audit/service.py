import base64
import json
from collections.abc import Callable, Sequence
from datetime import datetime
from typing import Any

from sqlalchemy import Integer, String, and_, desc, func, literal, or_, select, union_all
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.application.audit.dto import AuditCursorDTO, AuditEventDTO, AuditEventPageDTO
from app.application.audit.errors import AuditQueryValidationError
from app.infrastructure.db.models.message_event import MessageEventLogModel
from app.infrastructure.db.models.model_invocation import ModelInvocationLogModel
from app.infrastructure.db.models.tool_invocation import ToolInvocationLogModel
from app.infrastructure.db.models.workflow_event import WorkflowEventLogModel

AUDIT_KIND_ORDER = {
    "message": 1,
    "model": 2,
    "tool": 3,
    "workflow": 4,
}


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
        raise AuditQueryValidationError(f"不支持的审计类型：{kind}")

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
        async with self.session_factory() as session:
            statement = _build_timeline_statement(
                conversation_id=conversation_id,
                session_id=session_id,
                success=success,
                channel=channel,
                provider=provider,
                tool_name=tool_name,
                workflow_type=workflow_type,
                recorded_after=recorded_after,
                recorded_before=recorded_before,
                cursor=cursor,
            )
            rows = (await session.execute(statement.limit(limit + 1))).mappings().all()

        page_rows = rows[:limit]
        items = [_build_audit_event_dto_from_timeline_row(row) for row in page_rows]
        next_cursor = None
        if len(rows) > limit and page_rows:
            last_row = page_rows[-1]
            next_cursor = encode_audit_cursor(
                recorded_at=last_row["recorded_at"],
                event_id=last_row["event_id"],
                kind=last_row["kind"],
            )
        return AuditEventPageDTO(items=items, next_cursor=next_cursor)

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
                success_column=MessageEventLogModel.success,
                recorded_at_column=MessageEventLogModel.recorded_at,
                event_id_column=MessageEventLogModel.event_id,
                conversation_id=conversation_id,
                session_id=session_id,
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
                        "adapter_name": row.adapter_name,
                        "latency_ms": row.latency_ms,
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
                success_column=ModelInvocationLogModel.success,
                recorded_at_column=ModelInvocationLogModel.recorded_at,
                event_id_column=ModelInvocationLogModel.invocation_id,
                conversation_id=conversation_id,
                session_id=session_id,
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
                success_column=ToolInvocationLogModel.success,
                recorded_at_column=ToolInvocationLogModel.recorded_at,
                event_id_column=ToolInvocationLogModel.invocation_id,
                conversation_id=conversation_id,
                session_id=session_id,
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
                success_column=WorkflowEventLogModel.success,
                recorded_at_column=WorkflowEventLogModel.recorded_at,
                event_id_column=WorkflowEventLogModel.event_id,
                conversation_id=conversation_id,
                session_id=session_id,
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


def encode_audit_cursor(
    *,
    recorded_at: datetime,
    event_id: str,
    kind: str | None = None,
) -> str:
    payload = {
        "recorded_at": recorded_at.isoformat(),
        "event_id": event_id,
        "kind": kind,
    }
    return base64.urlsafe_b64encode(json.dumps(payload).encode("utf-8")).decode("utf-8")


def decode_audit_cursor(cursor: str) -> AuditCursorDTO:
    try:
        payload = json.loads(base64.urlsafe_b64decode(cursor.encode("utf-8")).decode("utf-8"))
        recorded_at = payload["recorded_at"]
        event_id = payload["event_id"]
    except (ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        raise AuditQueryValidationError("审计游标格式不合法。") from exc

    if not isinstance(recorded_at, str) or not isinstance(event_id, str):
        raise AuditQueryValidationError("审计游标格式不合法。")

    kind = payload.get("kind")
    if kind is not None and not isinstance(kind, str):
        raise AuditQueryValidationError("审计游标格式不合法。")

    return AuditCursorDTO(
        recorded_at=recorded_at,
        event_id=event_id,
        kind=kind,
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


def _build_timeline_statement(
    *,
    conversation_id: str | None,
    session_id: str | None,
    success: bool | None,
    channel: str | None,
    provider: str | None,
    tool_name: str | None,
    workflow_type: str | None,
    recorded_after: datetime | None,
    recorded_before: datetime | None,
    cursor: str | None,
) -> Any:
    timeline_source = union_all(
        _build_message_timeline_select(),
        _build_model_timeline_select(),
        _build_tool_timeline_select(),
        _build_workflow_timeline_select(),
    ).subquery("audit_timeline")
    statement = select(
        timeline_source.c.kind,
        timeline_source.c.kind_order,
        timeline_source.c.event_id,
        timeline_source.c.recorded_at,
        timeline_source.c.conversation_id,
        timeline_source.c.session_id,
        timeline_source.c.trace_id,
        timeline_source.c.chain_id,
        timeline_source.c.request_id,
        timeline_source.c.success,
        timeline_source.c.summary,
        timeline_source.c.payload,
    ).order_by(
        desc(timeline_source.c.recorded_at),
        desc(timeline_source.c.kind_order),
        desc(timeline_source.c.event_id),
    )
    return _apply_timeline_filters(
        statement=statement,
        timeline_source=timeline_source,
        conversation_id=conversation_id,
        session_id=session_id,
        success=success,
        channel=channel,
        provider=provider,
        tool_name=tool_name,
        workflow_type=workflow_type,
        recorded_after=recorded_after,
        recorded_before=recorded_before,
        cursor=cursor,
    )


def _apply_timeline_filters(
    *,
    statement: Any,
    timeline_source: Any,
    conversation_id: str | None,
    session_id: str | None,
    success: bool | None,
    channel: str | None,
    provider: str | None,
    tool_name: str | None,
    workflow_type: str | None,
    recorded_after: datetime | None,
    recorded_before: datetime | None,
    cursor: str | None,
) -> Any:
    if conversation_id:
        statement = statement.where(timeline_source.c.conversation_id == conversation_id)
    if session_id:
        statement = statement.where(timeline_source.c.session_id == session_id)
    if success is not None:
        statement = statement.where(timeline_source.c.success == success)
    if channel:
        statement = statement.where(timeline_source.c.channel == channel)
    if provider:
        statement = statement.where(timeline_source.c.provider == provider)
    if tool_name:
        statement = statement.where(timeline_source.c.tool_name == tool_name)
    if workflow_type:
        statement = statement.where(timeline_source.c.workflow_type == workflow_type)
    if recorded_after:
        statement = statement.where(timeline_source.c.recorded_at >= recorded_after)
    if recorded_before:
        statement = statement.where(timeline_source.c.recorded_at <= recorded_before)
    if cursor:
        decoded = decode_audit_cursor(cursor)
        recorded_at = datetime.fromisoformat(decoded.recorded_at)
        if decoded.kind is None:
            statement = statement.where(
                or_(
                    timeline_source.c.recorded_at < recorded_at,
                    and_(
                        timeline_source.c.recorded_at == recorded_at,
                        timeline_source.c.event_id < decoded.event_id,
                    ),
                )
            )
        else:
            kind_order = _resolve_audit_kind_order(decoded.kind)
            statement = statement.where(
                or_(
                    timeline_source.c.recorded_at < recorded_at,
                    and_(
                        timeline_source.c.recorded_at == recorded_at,
                        or_(
                            timeline_source.c.kind_order < kind_order,
                            and_(
                                timeline_source.c.kind_order == kind_order,
                                timeline_source.c.event_id < decoded.event_id,
                            ),
                        ),
                    ),
                )
            )
    return statement


def _build_message_timeline_select() -> Any:
    return select(
        literal("message", type_=String()).label("kind"),
        literal(AUDIT_KIND_ORDER["message"], type_=Integer()).label("kind_order"),
        MessageEventLogModel.event_id.label("event_id"),
        MessageEventLogModel.recorded_at.label("recorded_at"),
        MessageEventLogModel.conversation_id.label("conversation_id"),
        MessageEventLogModel.session_id.label("session_id"),
        MessageEventLogModel.trace_id.label("trace_id"),
        MessageEventLogModel.chain_id.label("chain_id"),
        MessageEventLogModel.request_id.label("request_id"),
        MessageEventLogModel.success.label("success"),
        func.concat(
            MessageEventLogModel.direction,
            ":",
            MessageEventLogModel.channel,
            ":",
            MessageEventLogModel.message_type,
        ).label("summary"),
        func.jsonb_build_object(
            "direction",
            MessageEventLogModel.direction,
            "channel",
            MessageEventLogModel.channel,
            "message_type",
            MessageEventLogModel.message_type,
            "adapter_name",
            MessageEventLogModel.adapter_name,
            "latency_ms",
            MessageEventLogModel.latency_ms,
            "text",
            MessageEventLogModel.text,
            "chat_id",
            MessageEventLogModel.chat_id,
            "thread_id",
            MessageEventLogModel.thread_id,
            "external_message_id",
            MessageEventLogModel.external_message_id,
            "metadata",
            MessageEventLogModel.metadata_json,
        ).label("payload"),
        MessageEventLogModel.channel.label("channel"),
        literal(None, type_=String()).label("provider"),
        literal(None, type_=String()).label("tool_name"),
        literal(None, type_=String()).label("workflow_type"),
    )


def _build_model_timeline_select() -> Any:
    return select(
        literal("model", type_=String()).label("kind"),
        literal(AUDIT_KIND_ORDER["model"], type_=Integer()).label("kind_order"),
        ModelInvocationLogModel.invocation_id.label("event_id"),
        ModelInvocationLogModel.recorded_at.label("recorded_at"),
        ModelInvocationLogModel.conversation_id.label("conversation_id"),
        ModelInvocationLogModel.session_id.label("session_id"),
        ModelInvocationLogModel.trace_id.label("trace_id"),
        ModelInvocationLogModel.chain_id.label("chain_id"),
        ModelInvocationLogModel.request_id.label("request_id"),
        ModelInvocationLogModel.success.label("success"),
        func.concat(
            func.coalesce(ModelInvocationLogModel.provider, "unknown"),
            ":",
            func.coalesce(ModelInvocationLogModel.model, "unknown"),
        ).label("summary"),
        func.jsonb_build_object(
            "operation",
            ModelInvocationLogModel.operation,
            "model_kind",
            ModelInvocationLogModel.model_kind,
            "latency_ms",
            ModelInvocationLogModel.latency_ms,
            "usage",
            ModelInvocationLogModel.usage,
        ).label("payload"),
        literal(None, type_=String()).label("channel"),
        ModelInvocationLogModel.provider.label("provider"),
        literal(None, type_=String()).label("tool_name"),
        literal(None, type_=String()).label("workflow_type"),
    )


def _build_tool_timeline_select() -> Any:
    return select(
        literal("tool", type_=String()).label("kind"),
        literal(AUDIT_KIND_ORDER["tool"], type_=Integer()).label("kind_order"),
        ToolInvocationLogModel.invocation_id.label("event_id"),
        ToolInvocationLogModel.recorded_at.label("recorded_at"),
        ToolInvocationLogModel.conversation_id.label("conversation_id"),
        ToolInvocationLogModel.session_id.label("session_id"),
        ToolInvocationLogModel.trace_id.label("trace_id"),
        ToolInvocationLogModel.chain_id.label("chain_id"),
        ToolInvocationLogModel.request_id.label("request_id"),
        ToolInvocationLogModel.success.label("success"),
        ToolInvocationLogModel.tool_name.label("summary"),
        func.jsonb_build_object(
            "tool_name",
            ToolInvocationLogModel.tool_name,
            "latency_ms",
            ToolInvocationLogModel.latency_ms,
            "timeout_seconds",
            ToolInvocationLogModel.timeout_seconds,
            "retry_limit",
            ToolInvocationLogModel.retry_limit,
        ).label("payload"),
        literal(None, type_=String()).label("channel"),
        literal(None, type_=String()).label("provider"),
        ToolInvocationLogModel.tool_name.label("tool_name"),
        literal(None, type_=String()).label("workflow_type"),
    )


def _build_workflow_timeline_select() -> Any:
    return select(
        literal("workflow", type_=String()).label("kind"),
        literal(AUDIT_KIND_ORDER["workflow"], type_=Integer()).label("kind_order"),
        WorkflowEventLogModel.event_id.label("event_id"),
        WorkflowEventLogModel.recorded_at.label("recorded_at"),
        WorkflowEventLogModel.conversation_id.label("conversation_id"),
        WorkflowEventLogModel.session_id.label("session_id"),
        WorkflowEventLogModel.trace_id.label("trace_id"),
        WorkflowEventLogModel.chain_id.label("chain_id"),
        WorkflowEventLogModel.request_id.label("request_id"),
        WorkflowEventLogModel.success.label("success"),
        func.concat(
            WorkflowEventLogModel.workflow_type,
            ":",
            WorkflowEventLogModel.event_type,
        ).label("summary"),
        func.jsonb_build_object(
            "workflow_id",
            WorkflowEventLogModel.workflow_id,
            "workflow_type",
            WorkflowEventLogModel.workflow_type,
            "event_type",
            WorkflowEventLogModel.event_type,
            "message",
            WorkflowEventLogModel.message,
            "payload",
            WorkflowEventLogModel.payload,
        ).label("payload"),
        literal(None, type_=String()).label("channel"),
        literal(None, type_=String()).label("provider"),
        literal(None, type_=String()).label("tool_name"),
        WorkflowEventLogModel.workflow_type.label("workflow_type"),
    )


def _build_audit_event_dto_from_timeline_row(row: Any) -> AuditEventDTO:
    payload = row["payload"]
    return AuditEventDTO(
        kind=row["kind"],
        event_id=row["event_id"],
        recorded_at=row["recorded_at"].isoformat(),
        conversation_id=row["conversation_id"],
        session_id=row["session_id"],
        trace_id=row["trace_id"],
        chain_id=row["chain_id"],
        request_id=row["request_id"],
        success=row["success"],
        summary=row["summary"],
        payload=payload if isinstance(payload, dict) else {},
    )


def _resolve_audit_kind_order(kind: str) -> int:
    try:
        return AUDIT_KIND_ORDER[kind]
    except KeyError as exc:
        raise AuditQueryValidationError(f"不支持的审计类型：{kind}") from exc
