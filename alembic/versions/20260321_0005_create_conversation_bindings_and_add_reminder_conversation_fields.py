"""创建 conversation_bindings 并为 reminders 增加内部会话字段。"""

import sqlalchemy as sa

from alembic import op

revision = "20260321_0005"
down_revision = "20260321_0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "conversation_bindings",
        sa.Column("binding_id", sa.String(length=36), primary_key=True),
        sa.Column("conversation_id", sa.String(length=36), nullable=False),
        sa.Column("session_id", sa.String(length=36), nullable=False),
        sa.Column("channel", sa.String(length=32), nullable=False),
        sa.Column("user_identity", sa.String(length=255), nullable=False),
        sa.Column("chat_id", sa.String(length=255), nullable=True),
        sa.Column("thread_id", sa.String(length=255), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_conversation_bindings_conversation_id",
        "conversation_bindings",
        ["conversation_id"],
    )
    op.add_column("reminders", sa.Column("conversation_id", sa.String(length=36), nullable=True))
    op.add_column("reminders", sa.Column("session_id", sa.String(length=36), nullable=True))
    op.create_index("ix_reminders_conversation_id", "reminders", ["conversation_id"])


def downgrade() -> None:
    op.drop_index("ix_reminders_conversation_id", table_name="reminders")
    op.drop_column("reminders", "session_id")
    op.drop_column("reminders", "conversation_id")
    op.drop_index(
        "ix_conversation_bindings_conversation_id",
        table_name="conversation_bindings",
    )
    op.drop_table("conversation_bindings")
