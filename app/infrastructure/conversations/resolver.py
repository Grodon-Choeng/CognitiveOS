from dataclasses import dataclass
from typing import Any
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.application.conversations.ports import (
    ConversationContextResolver,
    ResolvedConversationContext,
)
from app.infrastructure.db.models.conversation_binding import ConversationBindingModel


@dataclass(slots=True)
class _ConversationBinding:
    binding_id: str
    conversation_id: str
    session_id: str
    channel: str
    user_identity: str
    chat_id: str | None
    thread_id: str | None


class SqlAlchemyConversationContextResolver(ConversationContextResolver):
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self.session_factory = session_factory

    async def resolve_for_outbound(
        self,
        *,
        provided_conversation_id: str | None,
        provided_session_id: str | None,
        source_channel: str | None,
        source_user_id: str | None,
        source_chat_id: str | None,
        source_thread_id: str | None,
    ) -> ResolvedConversationContext:
        if provided_conversation_id:
            existing_binding = await self._get_binding_by_conversation_id(provided_conversation_id)
            resolved_session_id = (
                provided_session_id
                or (existing_binding.session_id if existing_binding else None)
                or self._new_id()
            )
            if source_channel and source_user_id:
                await self._save_binding(
                    conversation_id=provided_conversation_id,
                    session_id=resolved_session_id,
                    channel=source_channel,
                    user_identity=source_user_id,
                    chat_id=source_chat_id,
                    thread_id=source_thread_id,
                )
            return ResolvedConversationContext(
                conversation_id=provided_conversation_id,
                session_id=resolved_session_id,
            )

        if source_channel and source_user_id:
            existing_binding = await self._find_binding(
                channel=source_channel,
                user_identity=source_user_id,
                chat_id=source_chat_id,
                thread_id=source_thread_id,
            )
            if existing_binding is not None:
                resolved_session_id = provided_session_id or existing_binding.session_id
                return ResolvedConversationContext(
                    conversation_id=existing_binding.conversation_id,
                    session_id=resolved_session_id,
                )

        conversation_id = self._new_id()
        session_id = provided_session_id or self._new_id()
        if source_channel and source_user_id:
            await self._save_binding(
                conversation_id=conversation_id,
                session_id=session_id,
                channel=source_channel,
                user_identity=source_user_id,
                chat_id=source_chat_id,
                thread_id=source_thread_id,
            )
        return ResolvedConversationContext(
            conversation_id=conversation_id,
            session_id=session_id,
        )

    async def resolve_for_inbound(
        self,
        *,
        source_channel: str,
        source_user_id: str,
        source_chat_id: str | None,
        source_thread_id: str | None,
    ) -> ResolvedConversationContext:
        return await self.resolve_for_outbound(
            provided_conversation_id=None,
            provided_session_id=None,
            source_channel=source_channel,
            source_user_id=source_user_id,
            source_chat_id=source_chat_id,
            source_thread_id=source_thread_id,
        )

    async def _find_binding(
        self,
        *,
        channel: str,
        user_identity: str,
        chat_id: str | None,
        thread_id: str | None,
    ) -> _ConversationBinding | None:
        async with self.session_factory() as session:
            statement = (
                _build_binding_lookup_statement(
                    channel=channel,
                    user_identity=user_identity,
                    chat_id=chat_id,
                    thread_id=thread_id,
                )
                .order_by(ConversationBindingModel.updated_at.desc())
                .limit(1)
            )
            result = await session.execute(statement)
            model = result.scalar_one_or_none()
            if model is None:
                return None
            return self._to_binding(model)

    async def _get_binding_by_conversation_id(
        self,
        conversation_id: str,
    ) -> _ConversationBinding | None:
        async with self.session_factory() as session:
            statement = (
                select(ConversationBindingModel)
                .where(ConversationBindingModel.conversation_id == conversation_id)
                .order_by(ConversationBindingModel.updated_at.desc())
                .limit(1)
            )
            result = await session.execute(statement)
            model = result.scalar_one_or_none()
            if model is None:
                return None
            return self._to_binding(model)

    async def _save_binding(
        self,
        *,
        conversation_id: str,
        session_id: str,
        channel: str,
        user_identity: str,
        chat_id: str | None,
        thread_id: str | None,
    ) -> None:
        async with self.session_factory() as session:
            statement = _build_binding_lookup_statement(
                channel=channel,
                user_identity=user_identity,
                chat_id=chat_id,
                thread_id=thread_id,
            )
            existing = (await session.execute(statement.limit(1))).scalar_one_or_none()
            if existing is None:
                session.add(
                    ConversationBindingModel(
                        binding_id=self._new_id(),
                        conversation_id=conversation_id,
                        session_id=session_id,
                        channel=channel,
                        user_identity=user_identity,
                        chat_id=chat_id,
                        thread_id=thread_id,
                    )
                )
            else:
                existing.conversation_id = conversation_id
                existing.session_id = session_id
                existing.chat_id = chat_id
                existing.thread_id = thread_id
            await session.commit()

    @staticmethod
    def _to_binding(model: ConversationBindingModel) -> _ConversationBinding:
        return _ConversationBinding(
            binding_id=model.binding_id,
            conversation_id=model.conversation_id,
            session_id=model.session_id,
            channel=model.channel,
            user_identity=model.user_identity,
            chat_id=model.chat_id,
            thread_id=model.thread_id,
        )

    @staticmethod
    def _new_id() -> str:
        return str(uuid4())


def _build_binding_lookup_statement(
    *,
    channel: str,
    user_identity: str,
    chat_id: str | None,
    thread_id: str | None,
) -> Any:
    statement = (
        select(ConversationBindingModel)
        .where(ConversationBindingModel.channel == channel)
        .where(ConversationBindingModel.user_identity == user_identity)
    )
    if chat_id is None:
        statement = statement.where(ConversationBindingModel.chat_id.is_(None))
    else:
        statement = statement.where(ConversationBindingModel.chat_id == chat_id)
    if thread_id is None:
        statement = statement.where(ConversationBindingModel.thread_id.is_(None))
    else:
        statement = statement.where(ConversationBindingModel.thread_id == thread_id)
    return statement
