from datetime import datetime

from sqlalchemy import DateTime, Index, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.db.base import Base


class MemoryModel(Base):
    __tablename__ = "memories"
    __table_args__ = (
        Index("ix_memories_conversation_id", "conversation_id"),
        Index("ix_memories_session_id", "session_id"),
        Index("ix_memories_created_at", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    conversation_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    session_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
