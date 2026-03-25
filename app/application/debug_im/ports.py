from typing import Protocol

from app.application.debug_im.dto import (
    DebugIMMessageDTO,
    DebugIMMessageListDTO,
    DebugIMSessionListDTO,
)


class DebugIMMessageStore(Protocol):
    async def list_messages(
        self,
        *,
        user_identity: str,
        chat_id: str | None,
        thread_id: str | None,
        limit: int,
    ) -> DebugIMMessageListDTO: ...

    async def list_messages_after(
        self,
        *,
        user_identity: str,
        chat_id: str | None,
        thread_id: str | None,
        after_recorded_at: str | None,
        after_event_id: str | None,
        limit: int,
    ) -> DebugIMMessageListDTO: ...

    async def list_sessions(
        self,
        *,
        user_identity: str | None,
        limit: int,
    ) -> DebugIMSessionListDTO: ...

    async def get_message_by_external_id(
        self,
        *,
        user_identity: str,
        external_message_id: str,
        chat_id: str | None,
        thread_id: str | None,
    ) -> DebugIMMessageDTO | None: ...
