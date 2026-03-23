from app.config.settings import Settings


def test_settings_defaults() -> None:
    settings = Settings(_env_file=None)  # type: ignore[call-arg]

    assert settings.app_name == "CognitiveOS"
    assert settings.api_prefix == "/api/v1"
    assert settings.database_url.startswith("postgresql+asyncpg://")
    assert settings.temporal_task_queue == "cognitiveos-reminders"
    assert settings.conversation_llm_provider == "openai"
    assert settings.openai_base_url == "https://api.openai.com/v1"
    assert settings.local_llm_base_url == "http://localhost:1234/api/v1/chat"
    assert settings.conversation_intent_model is None
