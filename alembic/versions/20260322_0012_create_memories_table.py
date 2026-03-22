"""创建 memories 表。"""

import sqlalchemy as sa

from alembic import op

revision = "20260322_0012"
down_revision = "20260322_0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "memories",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("conversation_id", sa.String(length=36), nullable=True),
        sa.Column("session_id", sa.String(length=36), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_memories_conversation_id", "memories", ["conversation_id"])
    op.create_index("ix_memories_session_id", "memories", ["session_id"])
    op.create_index("ix_memories_created_at", "memories", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_memories_created_at", table_name="memories")
    op.drop_index("ix_memories_session_id", table_name="memories")
    op.drop_index("ix_memories_conversation_id", table_name="memories")
    op.drop_table("memories")
