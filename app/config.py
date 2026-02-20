from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

from app.constants import CACHE_DEFAULT_TTL, CACHE_PROMPT_TTL, DEFAULT_EMBEDDING_DIMENSION
from app.enums import Environment, IMProvider


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
    cache_default_ttl: int = CACHE_DEFAULT_TTL
    cache_prompt_ttl: int = CACHE_PROMPT_TTL

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
    embedding_dimension: int = DEFAULT_EMBEDDING_DIMENSION

    vector_index_path: str = "storage/vectors/index.faiss"

    api_key: str = ""
    api_key_header: str = "X-API-Key"

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
