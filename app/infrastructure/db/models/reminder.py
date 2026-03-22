from datetime import datetime

from sqlalchemy import DateTime, Index, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.db.base import Base


class ReminderModel(Base):
    __tablename__ = "reminders"
    __table_args__ = (
        Index("ix_reminders_conversation_id", "conversation_id"),
        Index(
            "ix_reminders_dispatch_channel_recipient",
            "dispatch_channel",
            "dispatch_recipient_id",
        ),
        Index("ix_reminders_dispatch_message_id", "dispatch_message_id"),
        Index(
            "ix_reminders_pending_conversation_lookup",
            "status",
            "conversation_id",
            "created_at",
        ),
        Index(
            "ix_reminders_pending_dispatch_lookup",
            "status",
            "dispatch_channel",
            "dispatch_recipient_id",
            "created_at",
        ),
        Index(
            "ix_reminders_pending_dispatch_chat_lookup",
            "status",
            "dispatch_channel",
            "dispatch_recipient_id",
            "dispatch_chat_id",
            "dispatch_thread_id",
            "created_at",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    text: Mapped[str] = mapped_column(String(500))
    remind_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    timezone: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    workflow_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    conversation_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    session_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    dispatch_channel: Mapped[str | None] = mapped_column(String(32), nullable=True)
    dispatch_recipient_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    dispatch_chat_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    dispatch_thread_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    dispatch_message_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    last_user_reply: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
