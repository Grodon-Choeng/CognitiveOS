from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, Index, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.db.base import Base
from app.infrastructure.types import JSONObject


class AssistantTurnStateModel(Base):
    __tablename__ = "assistant_turn_states"
    __table_args__ = (
        Index("ix_assistant_turn_states_updated_at", "updated_at"),
    )

    conversation_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    session_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    focused_object_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    focused_object_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    dialogue_mode: Mapped[str] = mapped_column(String(32), nullable=False, server_default="normal")
    last_action_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    last_action_success: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default="true",
    )
    visible_candidates_json: Mapped[list[JSONObject] | None] = mapped_column(
        JSON,
        nullable=True,
    )
    pending_confirmation_json: Mapped[JSONObject | None] = mapped_column(JSON, nullable=True)
    state_json: Mapped[JSONObject] = mapped_column(JSON, nullable=False, default=dict)
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
