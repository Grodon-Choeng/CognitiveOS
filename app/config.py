from functools import lru_cache
from pathlib import Path
from typing import Any

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.constants import CACHE_DEFAULT_TTL, CACHE_PROMPT_TTL, DEFAULT_EMBEDDING_DIMENSION
from app.enums import Environment, IMProvider


class IMConfig:
    def __init__(
        self,
        provider: IMProvider,
        webhook_url: str,
        secret: str = "",
        enabled: bool = True,
        **kwargs: Any,
    ) -> None:
        self.provider = provider
        self.webhook_url = webhook_url
        self.secret = secret
        self.enabled = enabled
        self.extra = kwargs

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "IMConfig":
        return cls(
            provider=IMProvider(data["provider"]),
            webhook_url=data.get("webhook_url", ""),
            secret=data.get("secret", ""),
            enabled=data.get("enabled", True),
            **{
                k: v
                for k, v in data.items()
                if k not in ("provider", "webhook_url", "secret", "enabled")
            },
        )

    def to_dict(self) -> dict[str, Any]:
        result = {
            "provider": self.provider.value,
            "webhook_url": self.webhook_url,
            "secret": self.secret,
            "enabled": self.enabled,
        }
        result.update(self.extra)
        return result


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
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

    im_configs: list[dict[str, Any]] = []
    im_enabled: bool = False

    im_provider: str = ""
    im_webhook_url: str = ""
    im_secret: str = ""

    llm_model: str = "openai/gpt-4o-mini"
    llm_api_key: str = ""
    llm_base_url: str = ""
    embedding_model: str = "openai/text-embedding-3-small"
    embedding_dimension: int = DEFAULT_EMBEDDING_DIMENSION

    vector_index_path: str = "storage/vectors/index.faiss"

    api_key: str = ""
    api_key_header: str = "X-API-Key"

    @field_validator("im_configs", mode="before")
    @classmethod
    def parse_im_configs(cls, v: Any) -> list[dict[str, Any]]:
        if isinstance(v, str):
            import json

            try:
                return json.loads(v)
            except json.JSONDecodeError:
                return []
        return v or []

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._migrate_legacy_im_config()

    def _migrate_legacy_im_config(self) -> None:
        if self.im_provider and self.im_webhook_url and not self.im_configs:
            self.im_configs = [
                {
                    "provider": self.im_provider,
                    "webhook_url": self.im_webhook_url,
                    "secret": self.im_secret,
                    "enabled": True,
                }
            ]

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

    def get_im_configs(self) -> list[IMConfig]:
        return [IMConfig.from_dict(cfg) for cfg in self.im_configs if cfg.get("enabled", True)]

    def get_im_config(self, provider: IMProvider) -> IMConfig | None:
        for cfg in self.get_im_configs():
            if cfg.provider == provider:
                return cfg
        return None


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
