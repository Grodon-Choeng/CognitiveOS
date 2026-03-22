"""为 memories 增加归档字段。"""

import sqlalchemy as sa

from alembic import op

revision = "20260322_0014"
down_revision = "20260322_0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "memories",
        sa.Column("status", sa.String(length=32), nullable=False, server_default="active"),
    )
    op.add_column(
        "memories",
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_memories_status", "memories", ["status"])
    op.alter_column("memories", "status", server_default=None)


def downgrade() -> None:
    op.drop_index("ix_memories_status", table_name="memories")
    op.drop_column("memories", "archived_at")
    op.drop_column("memories", "status")
