from app.config.settings import Settings


def test_settings_defaults() -> None:
    settings = Settings()

    assert settings.app_name == "CognitiveOS"
    assert settings.api_prefix == "/api/v1"
    assert settings.database_url.startswith("postgresql+asyncpg://")
    assert settings.temporal_task_queue == "cognitiveos-reminders"
