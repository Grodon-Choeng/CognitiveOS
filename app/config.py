from enum import Enum
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Environment(str, Enum):
    DEVELOPMENT = "development"
    STAGING = "staging"
    PRODUCTION = "production"


class IMProvider(str, Enum):
    WECOM = "wecom"
    DINGTALK = "dingtalk"
    FEISHU = "feishu"
    DISCORD = "discord"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    environment: Environment = Environment.DEVELOPMENT
    debug: bool = True

    db_path: str = "cognitive.db"
    storage_path: Path = Path("storage")

    cache_url: str = "redis://localhost:6379/0"
    cache_enabled: bool = False
    cache_default_ttl: int = 300

    log_level: str = "INFO"

    markdown_debug_mode: bool = False

    im_provider: IMProvider = IMProvider.WECOM
    im_webhook_url: str = ""
    im_secret: str = ""
    im_enabled: bool = False

    llm_model: str = "openai/gpt-4o-mini"
    llm_api_key: str = ""
    llm_base_url: str = ""
    embedding_model: str = "openai/text-embedding-3-small"
    embedding_dimension: int = 1536

    vector_index_path: str = "storage/vectors/index.faiss"

    @property
    def raw_path(self) -> Path:
        return self.storage_path / "raw"

    @property
    def structured_path(self) -> Path:
        return self.storage_path / "structured"

    @property
    def vector_path(self) -> Path:
        return self.storage_path / "vectors"

    @property
    def is_production(self) -> bool:
        return self.environment == Environment.PRODUCTION


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
