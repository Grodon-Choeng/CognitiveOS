"""为 reminders 增加循环 schedule 持久化字段。"""

import sqlalchemy as sa

from alembic import op

revision = "20260326_0016"
down_revision = "20260324_0015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("reminders", sa.Column("recurrence_json", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("reminders", "recurrence_json")
