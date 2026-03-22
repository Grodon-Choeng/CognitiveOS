from typing import cast

import pytest

from app.infrastructure.llm.models import GenerateRequest
from app.infrastructure.llm.openai_gateway import OpenAIChatLLMGateway


class FakeResponse:
    def __init__(self) -> None:
        self.headers = {"x-request-id": "req-123"}

    def raise_for_status(self) -> None:
        return None

    def json(self) -> object:
        return {
            "model": "gpt-test",
            "choices": [{"message": {"content": '{"intent":"task_create","content":"买牛奶"}'}}],
            "usage": {
                "prompt_tokens": 10,
                "completion_tokens": 5,
                "total_tokens": 15,
            },
        }


@pytest.mark.asyncio
async def test_openai_chat_llm_gateway_builds_request_and_parses_response() -> None:
    captured: dict[str, object] = {}

    async def fake_sender(**kwargs: object) -> FakeResponse:
        captured.update(kwargs)
        return FakeResponse()

    gateway = OpenAIChatLLMGateway(
        api_key="sk-test",
        model="gpt-test",
        base_url="https://api.openai.com/v1",
        sender=fake_sender,
    )

    result = await gateway.generate(
        GenerateRequest(
            prompt="用户输入：帮我买牛奶",
            system_prompt="你是分类器",
            provider="openai",
            model="gpt-test",
        )
    )

    assert captured["url"] == "https://api.openai.com/v1/chat/completions"
    headers = cast(dict[str, str], captured["headers"])
    assert "Authorization" in headers
    assert result.provider == "openai"
    assert result.model == "gpt-test"
    assert result.usage["total_tokens"] == 15
