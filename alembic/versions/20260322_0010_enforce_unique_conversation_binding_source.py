"""为会话来源绑定增加唯一约束并改为 upsert 友好。"""

from alembic import op

revision = "20260322_0010"
down_revision = "20260321_0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        WITH ranked AS (
            SELECT
                binding_id,
                ROW_NUMBER() OVER (
                    PARTITION BY channel, user_identity, chat_id, thread_id
                    ORDER BY updated_at DESC, created_at DESC, binding_id DESC
                ) AS row_number
            FROM conversation_bindings
        )
        DELETE FROM conversation_bindings
        WHERE binding_id IN (
            SELECT binding_id
            FROM ranked
            WHERE row_number > 1
        )
        """
    )
    op.drop_index("ix_conversation_bindings_lookup", table_name="conversation_bindings")
    op.create_index(
        "ux_conversation_bindings_source",
        "conversation_bindings",
        ["channel", "user_identity", "chat_id", "thread_id"],
        unique=True,
        postgresql_nulls_not_distinct=True,
    )


def downgrade() -> None:
    op.drop_index("ux_conversation_bindings_source", table_name="conversation_bindings")
    op.create_index(
        "ix_conversation_bindings_lookup",
        "conversation_bindings",
        ["channel", "user_identity", "chat_id", "thread_id"],
    )
