"""创建 workflow_event_logs 表。"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "20260321_0007"
down_revision = "20260321_0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "workflow_event_logs",
        sa.Column("event_id", sa.String(length=36), primary_key=True),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("workflow_id", sa.String(length=255), nullable=False),
        sa.Column("workflow_type", sa.String(length=128), nullable=False),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("conversation_id", sa.String(length=36), nullable=True),
        sa.Column("session_id", sa.String(length=36), nullable=True),
        sa.Column("trace_id", sa.String(length=255), nullable=True),
        sa.Column("chain_id", sa.String(length=255), nullable=True),
        sa.Column("request_id", sa.String(length=255), nullable=True),
        sa.Column("success", sa.Boolean(), nullable=False),
        sa.Column("message", sa.Text(), nullable=True),
        sa.Column(
            "payload",
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
    op.create_index("ix_workflow_event_logs_recorded_at", "workflow_event_logs", ["recorded_at"])
    op.create_index(
        "ix_workflow_event_logs_conversation_id",
        "workflow_event_logs",
        ["conversation_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_workflow_event_logs_conversation_id", table_name="workflow_event_logs")
    op.drop_index("ix_workflow_event_logs_recorded_at", table_name="workflow_event_logs")
    op.drop_table("workflow_event_logs")
