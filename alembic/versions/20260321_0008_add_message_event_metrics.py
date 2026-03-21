"""为 message_event_logs 增加适配器与耗时字段。"""

import sqlalchemy as sa

from alembic import op

revision = "20260321_0008"
down_revision = "20260321_0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "message_event_logs",
        sa.Column("adapter_name", sa.String(length=128), nullable=True),
    )
    op.add_column(
        "message_event_logs",
        sa.Column("latency_ms", sa.Float(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("message_event_logs", "latency_ms")
    op.drop_column("message_event_logs", "adapter_name")
