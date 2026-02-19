from enum import Enum
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Environment(str, Enum):
    DEVELOPMENT = "development"
    STAGING = "staging"
    PRODUCTION = "production"


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

    @property
    def raw_path(self) -> Path:
        return self.storage_path / "raw"

    @property
    def structured_path(self) -> Path:
        return self.storage_path / "structured"

    @property
    def is_production(self) -> bool:
        return self.environment == Environment.PRODUCTION


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
