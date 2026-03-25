from datetime import datetime

from sqlalchemy import and_, desc, or_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.application.debug_im.dto import (
    DebugIMMessageDTO,
    DebugIMMessageListDTO,
    DebugIMSessionDTO,
    DebugIMSessionListDTO,
)
from app.infrastructure.db.models.message_event import MessageEventLogModel


class SQLAlchemyDebugIMMessageStore:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self.session_factory = session_factory

    async def list_messages(
        self,
        *,
        user_identity: str,
        chat_id: str | None,
        thread_id: str | None,
        limit: int,
    ) -> DebugIMMessageListDTO:
        async with self.session_factory() as session:
            statement = (
                select(MessageEventLogModel)
                .where(MessageEventLogModel.channel == "debug_im")
                .where(MessageEventLogModel.user_identity == user_identity)
                .order_by(
                    desc(MessageEventLogModel.recorded_at),
                    desc(MessageEventLogModel.event_id),
                )
                .limit(limit)
            )
            statement = _apply_optional_session_filters(
                statement=statement,
                chat_id=chat_id,
                thread_id=thread_id,
            )
            rows = (await session.execute(statement)).scalars().all()
        return DebugIMMessageListDTO(items=[_to_message_dto(row) for row in reversed(rows)])

    async def list_messages_after(
        self,
        *,
        user_identity: str,
        chat_id: str | None,
        thread_id: str | None,
        after_recorded_at: str | None,
        after_event_id: str | None,
        limit: int,
    ) -> DebugIMMessageListDTO:
        async with self.session_factory() as session:
            statement = (
                select(MessageEventLogModel)
                .where(MessageEventLogModel.channel == "debug_im")
                .where(MessageEventLogModel.user_identity == user_identity)
                .order_by(
                    MessageEventLogModel.recorded_at.asc(),
                    MessageEventLogModel.event_id.asc(),
                )
                .limit(limit)
            )
            statement = _apply_optional_session_filters(
                statement=statement,
                chat_id=chat_id,
                thread_id=thread_id,
            )
            if after_recorded_at is not None:
                after_dt = datetime.fromisoformat(after_recorded_at)
                after_event = after_event_id or ""
                statement = statement.where(
                    or_(
                        MessageEventLogModel.recorded_at > after_dt,
                        and_(
                            MessageEventLogModel.recorded_at == after_dt,
                            MessageEventLogModel.event_id > after_event,
                        ),
                    )
                )
            rows = (await session.execute(statement)).scalars().all()
        return DebugIMMessageListDTO(items=[_to_message_dto(row) for row in rows])

    async def list_sessions(
        self,
        *,
        user_identity: str | None,
        limit: int,
    ) -> DebugIMSessionListDTO:
        sample_limit = max(limit * 20, 200)
        async with self.session_factory() as session:
            statement = (
                select(MessageEventLogModel)
                .where(MessageEventLogModel.channel == "debug_im")
                .order_by(
                    desc(MessageEventLogModel.recorded_at),
                    desc(MessageEventLogModel.event_id),
                )
                .limit(sample_limit)
            )
            if user_identity is not None:
                statement = statement.where(MessageEventLogModel.user_identity == user_identity)
            rows = (await session.execute(statement)).scalars().all()

        items: list[DebugIMSessionDTO] = []
        seen: set[tuple[str, str | None, str | None]] = set()
        for row in rows:
            if row.user_identity is None:
                continue
            key = (row.user_identity, row.chat_id, row.thread_id)
            if key in seen:
                continue
            seen.add(key)
            items.append(
                DebugIMSessionDTO(
                    session_key=_build_session_key(*key),
                    user_identity=row.user_identity,
                    chat_id=row.chat_id,
                    thread_id=row.thread_id,
                    conversation_id=row.conversation_id,
                    session_id=row.session_id,
                    last_message_at=row.recorded_at.isoformat(),
                    last_message_direction=row.direction,
                    last_message_text=row.text,
                    last_external_message_id=row.external_message_id,
                )
            )
            if len(items) >= limit:
                break
        return DebugIMSessionListDTO(items=items)

    async def get_message_by_external_id(
        self,
        *,
        user_identity: str,
        external_message_id: str,
        chat_id: str | None,
        thread_id: str | None,
    ) -> DebugIMMessageDTO | None:
        async with self.session_factory() as session:
            statement = (
                select(MessageEventLogModel)
                .where(MessageEventLogModel.channel == "debug_im")
                .where(MessageEventLogModel.user_identity == user_identity)
                .where(MessageEventLogModel.external_message_id == external_message_id)
                .order_by(
                    desc(MessageEventLogModel.recorded_at),
                    desc(MessageEventLogModel.event_id),
                )
                .limit(1)
            )
            statement = _apply_optional_session_filters(
                statement=statement,
                chat_id=chat_id,
                thread_id=thread_id,
            )
            row = (await session.execute(statement)).scalar_one_or_none()
        if row is None:
            return None
        return _to_message_dto(row)


def _apply_optional_session_filters(
    *,
    statement: object,
    chat_id: str | None,
    thread_id: str | None,
) -> object:
    if chat_id is not None:
        statement = statement.where(MessageEventLogModel.chat_id == chat_id)
    if thread_id is not None:
        statement = statement.where(MessageEventLogModel.thread_id == thread_id)
    return statement


def _to_message_dto(row: MessageEventLogModel) -> DebugIMMessageDTO:
    return DebugIMMessageDTO(
        event_id=row.event_id,
        recorded_at=row.recorded_at.isoformat(),
        direction=row.direction,
        channel=row.channel,
        user_identity=row.user_identity,
        chat_id=row.chat_id,
        thread_id=row.thread_id,
        conversation_id=row.conversation_id,
        session_id=row.session_id,
        external_message_id=row.external_message_id,
        root_message_id=row.root_message_id,
        parent_message_id=row.parent_message_id,
        text=row.text,
        success=row.success,
        adapter_name=row.adapter_name,
        metadata=row.metadata_json,
    )


def _build_session_key(
    user_identity: str,
    chat_id: str | None,
    thread_id: str | None,
) -> str:
    return f"{user_identity}::{chat_id or ''}::{thread_id or ''}"
