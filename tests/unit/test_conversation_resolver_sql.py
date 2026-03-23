from sqlalchemy.dialects import postgresql

from app.infrastructure.conversations.resolver import _build_binding_upsert_statement


def test_binding_upsert_statement_uses_conflict_update() -> None:
    statement = _build_binding_upsert_statement(
        binding_id="binding-1",
        conversation_id="conversation-1",
        session_id="session-1",
        channel="feishu",
        user_identity="ou_123",
        chat_id="oc_123",
        thread_id="ot_123",
    )

    compiled = str(
        statement.compile(
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    )

    assert 'ON CONFLICT (channel, user_identity, chat_id, thread_id)' in compiled
    assert "DO UPDATE SET" in compiled
