from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, Index, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.db.base import Base
from app.infrastructure.types import JSONObject


class ModelInvocationLogModel(Base):
    __tablename__ = "model_invocation_logs"
    __table_args__ = (
        Index("ix_model_invocation_logs_recorded_at", "recorded_at"),
        Index("ix_model_invocation_logs_session_id", "session_id"),
        Index("ix_model_invocation_logs_trace_id", "trace_id"),
        Index("ix_model_invocation_logs_conversation_id", "conversation_id"),
        Index("ix_model_invocation_logs_provider", "provider"),
    )

    invocation_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    operation: Mapped[str] = mapped_column(String(64), nullable=False)
    model_kind: Mapped[str] = mapped_column(String(32), nullable=False)
    provider: Mapped[str | None] = mapped_column(String(64), nullable=True)
    model: Mapped[str | None] = mapped_column(String(128), nullable=True)
    api_key_suffix: Mapped[str | None] = mapped_column(String(16), nullable=True)
    session_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    conversation_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    trace_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    chain_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    request_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    latency_ms: Mapped[float] = mapped_column(Float, nullable=False)
    success: Mapped[bool] = mapped_column(Boolean, nullable=False)
    error_type: Mapped[str | None] = mapped_column(String(255), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    usage: Mapped[JSONObject] = mapped_column(JSONB, nullable=False, default=dict)
    raw_input: Mapped[JSONObject] = mapped_column(JSONB, nullable=False, default=dict)
    raw_output: Mapped[JSONObject] = mapped_column(JSONB, nullable=False, default=dict)
    metadata_json: Mapped[JSONObject] = mapped_column(
        "metadata",
        JSONB,
        nullable=False,
        default=dict,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
