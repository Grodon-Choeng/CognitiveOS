"""创建 message_event_logs 表。"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "20260321_0006"
down_revision = "20260321_0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "message_event_logs",
        sa.Column("event_id", sa.String(length=36), primary_key=True),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("direction", sa.String(length=16), nullable=False),
        sa.Column("channel", sa.String(length=32), nullable=False),
        sa.Column("message_type", sa.String(length=32), nullable=False),
        sa.Column("user_identity", sa.String(length=255), nullable=True),
        sa.Column("external_message_id", sa.String(length=255), nullable=True),
        sa.Column("root_message_id", sa.String(length=255), nullable=True),
        sa.Column("parent_message_id", sa.String(length=255), nullable=True),
        sa.Column("chat_id", sa.String(length=255), nullable=True),
        sa.Column("thread_id", sa.String(length=255), nullable=True),
        sa.Column("conversation_id", sa.String(length=36), nullable=True),
        sa.Column("session_id", sa.String(length=36), nullable=True),
        sa.Column("trace_id", sa.String(length=255), nullable=True),
        sa.Column("chain_id", sa.String(length=255), nullable=True),
        sa.Column("request_id", sa.String(length=255), nullable=True),
        sa.Column("text", sa.Text(), nullable=True),
        sa.Column("success", sa.Boolean(), nullable=False),
        sa.Column("error_code", sa.String(length=255), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column(
            "raw_payload",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_message_event_logs_recorded_at", "message_event_logs", ["recorded_at"])
    op.create_index(
        "ix_message_event_logs_conversation_id",
        "message_event_logs",
        ["conversation_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_message_event_logs_conversation_id", table_name="message_event_logs")
    op.drop_index("ix_message_event_logs_recorded_at", table_name="message_event_logs")
    op.drop_table("message_event_logs")
