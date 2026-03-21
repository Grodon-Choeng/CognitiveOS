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
    redis_url: str = "redis://localhost:6379/0"
    feishu_app_id: str | None = None
    feishu_app_secret: str | None = None
    feishu_message_receive_id_type: str = "open_id"
    feishu_verification_token: str | None = None
    feishu_encrypt_key: str | None = None
    model_invocation_jsonl_enabled: bool = True
    model_invocation_jsonl_path: str = "logs/model_invocations.jsonl"
    model_invocation_db_enabled: bool = True
    tool_invocation_jsonl_enabled: bool = True
    tool_invocation_jsonl_path: str = "logs/tool_invocations.jsonl"
    tool_invocation_db_enabled: bool = True
    temporal_host: str = "localhost:7233"
    temporal_namespace: str = "default"
    temporal_task_queue: str = "cognitiveos-reminders"
    temporal_reminder_workflow_name: str = "reminder-workflow"
    openai_api_key: str | None = Field(default=None)

    model_config = SettingsConfigDict(
        env_prefix="COGNITIVE_OS_",
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
