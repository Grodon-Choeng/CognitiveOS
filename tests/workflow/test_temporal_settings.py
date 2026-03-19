from app.config.settings import Settings


def test_temporal_defaults_exist() -> None:
    settings = Settings()

    assert settings.temporal_host == "localhost:7233"
    assert settings.temporal_namespace == "default"
    assert settings.temporal_reminder_workflow_name == "reminder-workflow"
