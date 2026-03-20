"""创建 tool_invocation_logs 表。"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "20260320_0003"
down_revision = "20260320_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "tool_invocation_logs",
        sa.Column("invocation_id", sa.String(length=36), primary_key=True),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("tool_name", sa.String(length=128), nullable=False),
        sa.Column("session_id", sa.String(length=255), nullable=True),
        sa.Column("conversation_id", sa.String(length=255), nullable=True),
        sa.Column("trace_id", sa.String(length=255), nullable=True),
        sa.Column("chain_id", sa.String(length=255), nullable=True),
        sa.Column("request_id", sa.String(length=255), nullable=True),
        sa.Column("latency_ms", sa.Float(), nullable=False),
        sa.Column("timeout_seconds", sa.Float(), nullable=True),
        sa.Column("retry_limit", sa.Integer(), nullable=False),
        sa.Column("success", sa.Boolean(), nullable=False),
        sa.Column("error_code", sa.String(length=255), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column(
            "raw_input",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "raw_output",
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
    op.create_index(
        "ix_tool_invocation_logs_recorded_at",
        "tool_invocation_logs",
        ["recorded_at"],
    )
    op.create_index(
        "ix_tool_invocation_logs_session_id",
        "tool_invocation_logs",
        ["session_id"],
    )
    op.create_index(
        "ix_tool_invocation_logs_trace_id",
        "tool_invocation_logs",
        ["trace_id"],
    )
    op.create_index(
        "ix_tool_invocation_logs_tool_name",
        "tool_invocation_logs",
        ["tool_name"],
    )


def downgrade() -> None:
    op.drop_index("ix_tool_invocation_logs_tool_name", table_name="tool_invocation_logs")
    op.drop_index("ix_tool_invocation_logs_trace_id", table_name="tool_invocation_logs")
    op.drop_index("ix_tool_invocation_logs_session_id", table_name="tool_invocation_logs")
    op.drop_index("ix_tool_invocation_logs_recorded_at", table_name="tool_invocation_logs")
    op.drop_table("tool_invocation_logs")
