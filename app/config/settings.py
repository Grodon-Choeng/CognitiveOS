from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "CognitiveOS"
    app_version: str = "0.1.0"
    app_env: str = "dev"
    debug: bool = False
    api_prefix: str = "/api/v1"
    database_url: str = "postgresql+asyncpg://cognitiveos:cognitiveos@localhost:5432/cognitiveos"
    database_echo: bool = False
    temporal_host: str = "localhost:7233"
    temporal_namespace: str = "default"
    temporal_task_queue: str = "cognitiveos-reminders"
    temporal_reminder_workflow_name: str = "reminder-workflow"
    openai_api_key: str | None = Field(default=None)

    model_config = SettingsConfigDict(
        env_prefix="COGNITIVE_OS_",
        case_sensitive=False,
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
