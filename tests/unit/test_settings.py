from app.config.settings import Settings


def test_settings_defaults() -> None:
    settings = Settings(_env_file=None)  # type: ignore[call-arg]

    assert settings.app_name == "CognitiveOS"
    assert settings.api_prefix == "/api/v1"
    assert settings.database_url.startswith("postgresql+asyncpg://")
    assert settings.temporal_task_queue == "cognitiveos-reminders"
    assert settings.llm_default_provider == "openai"
    assert settings.conversation_llm_provider is None
    assert settings.openai_base_url == "https://api.openai.com/v1"
    assert settings.local_llm_base_url == "http://localhost:1234/api/v1/chat"
    assert settings.conversation_intent_model is None
    assert settings.effective_conversation_llm_provider == "openai"
    assert settings.effective_conversation_llm_endpoint == "https://api.openai.com/v1"
    assert settings.effective_conversation_intent_model is None


def test_settings_use_default_llm_profile_as_conversation_fallback() -> None:
    settings = Settings(
        _env_file=None,  # type: ignore[call-arg]
        llm_default_provider="local",
        llm_default_endpoint="http://localhost:11434/v1/chat",
        llm_default_small_model="qwen2.5-7b",
        llm_default_large_model="qwen2.5-72b",
    )

    assert settings.effective_conversation_llm_provider == "local"
    assert settings.effective_conversation_llm_endpoint == "http://localhost:11434/v1/chat"
    assert settings.effective_conversation_intent_model == "qwen2.5-7b"
    assert settings.effective_default_large_model == "qwen2.5-72b"
    assert settings.effective_conversation_llm_api_key is None


def test_settings_allow_conversation_level_llm_overrides() -> None:
    settings = Settings(
        _env_file=None,  # type: ignore[call-arg]
        llm_default_provider="openai",
        llm_default_endpoint="https://fallback.example.com/v1",
        llm_default_api_key="fallback-key",
        llm_default_small_model="fallback-small",
        conversation_llm_provider="openai",
        conversation_llm_endpoint="https://conversation.example.com/v1",
        conversation_llm_api_key="conversation-key",
        conversation_intent_model="gpt-4.1-mini",
    )

    assert settings.effective_conversation_llm_provider == "openai"
    assert settings.effective_conversation_llm_endpoint == "https://conversation.example.com/v1"
    assert settings.effective_conversation_llm_api_key == "conversation-key"
    assert settings.effective_conversation_intent_model == "gpt-4.1-mini"
