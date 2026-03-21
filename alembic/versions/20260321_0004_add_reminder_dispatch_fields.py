"""为 reminders 表增加消息派发关联字段。"""

import sqlalchemy as sa

from alembic import op

revision = "20260321_0004"
down_revision = "20260320_0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("reminders", sa.Column("dispatch_channel", sa.String(length=32), nullable=True))
    op.add_column(
        "reminders",
        sa.Column("dispatch_recipient_id", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "reminders",
        sa.Column("dispatch_chat_id", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "reminders",
        sa.Column("dispatch_thread_id", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "reminders",
        sa.Column("dispatch_message_id", sa.String(length=255), nullable=True),
    )
    op.create_index(
        "ix_reminders_dispatch_channel_recipient",
        "reminders",
        ["dispatch_channel", "dispatch_recipient_id"],
    )
    op.create_index(
        "ix_reminders_dispatch_message_id",
        "reminders",
        ["dispatch_message_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_reminders_dispatch_message_id", table_name="reminders")
    op.drop_index("ix_reminders_dispatch_channel_recipient", table_name="reminders")
    op.drop_column("reminders", "dispatch_message_id")
    op.drop_column("reminders", "dispatch_thread_id")
    op.drop_column("reminders", "dispatch_chat_id")
    op.drop_column("reminders", "dispatch_recipient_id")
    op.drop_column("reminders", "dispatch_channel")
