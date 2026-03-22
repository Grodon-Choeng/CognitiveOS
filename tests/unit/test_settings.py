from app.config.settings import Settings


def test_settings_defaults() -> None:
    settings = Settings()

    assert settings.app_name == "CognitiveOS"
    assert settings.api_prefix == "/api/v1"
    assert settings.database_url.startswith("postgresql+asyncpg://")
    assert settings.temporal_task_queue == "cognitiveos-reminders"
    assert settings.openai_base_url == "https://api.openai.com/v1"
    assert settings.conversation_intent_model is None
