from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.db.base import Base
from app.infrastructure.types import JSONObject


class ToolInvocationLogModel(Base):
    __tablename__ = "tool_invocation_logs"

    invocation_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    tool_name: Mapped[str] = mapped_column(String(128), nullable=False)
    session_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    conversation_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    trace_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    chain_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    request_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    latency_ms: Mapped[float] = mapped_column(Float, nullable=False)
    timeout_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    retry_limit: Mapped[int] = mapped_column(Integer, nullable=False)
    success: Mapped[bool] = mapped_column(Boolean, nullable=False)
    error_code: Mapped[str | None] = mapped_column(String(255), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
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
