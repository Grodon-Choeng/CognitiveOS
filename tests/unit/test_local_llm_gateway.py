import pytest

from app.infrastructure.llm.local_gateway import LocalChatLLMGateway
from app.infrastructure.llm.models import GenerateRequest


class FakeResponse:
    def raise_for_status(self) -> None:
        return None

    def json(self) -> object:
        return {
            "model_instance_id": "qwen/qwen3-8b",
            "output": [
                {"type": "reasoning", "content": "thinking"},
                {"type": "message", "content": '{"reply_text":"你好呀"}'},
            ],
            "stats": {
                "input_tokens": 12,
                "total_output_tokens": 34,
                "tokens_per_second": 22.5,
                "time_to_first_token_seconds": 0.42,
            },
            "response_id": "resp_123",
        }


@pytest.mark.asyncio
async def test_local_chat_llm_gateway_builds_request_and_parses_response() -> None:
    captured: dict[str, object] = {}

    async def fake_sender(**kwargs: object) -> FakeResponse:
        captured.update(kwargs)
        return FakeResponse()

    gateway = LocalChatLLMGateway(
        model="qwen/qwen3-8b",
        base_url="http://localhost:1234/api/v1/chat",
        sender=fake_sender,
    )

    result = await gateway.generate(
        GenerateRequest(
            prompt="用户输入：你能干啥",
            system_prompt="你是助手",
            provider="local",
            model="qwen/qwen3-8b",
        )
    )

    assert captured["url"] == "http://localhost:1234/api/v1/chat"
    assert captured["payload"] == {
        "model": "qwen/qwen3-8b",
        "system_prompt": "你是助手",
        "input": "用户输入：你能干啥",
    }
    assert result.provider == "local"
    assert result.model == "qwen/qwen3-8b"
    assert result.content == '{"reply_text":"你好呀"}'
    assert result.usage["prompt_tokens"] == 12
    assert result.usage["completion_tokens"] == 34
    assert result.usage["total_tokens"] == 46
    assert result.metadata["provider_request_id"] == "resp_123"
