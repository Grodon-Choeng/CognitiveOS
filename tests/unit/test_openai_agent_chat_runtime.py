from typing import cast

import pytest

from app.infrastructure.agents.models import AgentChatTurnRequest, ChatMessage
from app.infrastructure.agents.openai_chat_runtime import OpenAIChatAgentRuntime
from app.infrastructure.tools.mcp.protocol import ToolDefinition


class FakeResponse:
    def __init__(self) -> None:
        self.headers = {"x-request-id": "req-chat-1"}

    def raise_for_status(self) -> None:
        return None

    def json(self) -> object:
        return {
            "model": "gpt-4.1-mini",
            "choices": [
                {
                    "finish_reason": "tool_calls",
                    "message": {
                        "content": None,
                        "tool_calls": [
                            {
                                "id": "call_1",
                                "type": "function",
                                "function": {
                                    "name": "tasks.list",
                                    "arguments": '{"limit": 1}',
                                },
                            }
                        ],
                    },
                }
            ],
            "usage": {
                "prompt_tokens": 10,
                "completion_tokens": 6,
                "total_tokens": 16,
            },
        }


@pytest.mark.asyncio
async def test_openai_chat_agent_runtime_builds_payload_and_parses_tool_calls() -> None:
    captured: dict[str, object] = {}

    async def fake_sender(**kwargs: object) -> FakeResponse:
        captured.update(kwargs)
        return FakeResponse()

    runtime = OpenAIChatAgentRuntime(
        api_key="sk-test",
        model="gpt-4.1-mini",
        base_url="https://api.openai.com/v1",
        sender=fake_sender,
    )

    result = await runtime.run_chat_turn(
        AgentChatTurnRequest(
            system_prompt="你是测试助手",
            messages=[ChatMessage(role="user", content="列出最近待办")],
            tools=[
                ToolDefinition(
                    name="tasks.list",
                    description="列出待办。",
                    input_schema={
                        "type": "object",
                        "properties": {"limit": {"type": "integer"}},
                    },
                )
            ],
            provider="openai",
            model="gpt-4.1-mini",
        )
    )

    assert captured["url"] == "https://api.openai.com/v1/chat/completions"
    payload = cast(dict[str, object], captured["payload"])
    messages = cast(list[dict[str, object]], payload["messages"])
    assert messages[0] == {"role": "system", "content": "你是测试助手"}
    assert messages[1] == {"role": "user", "content": "列出最近待办"}
    assert payload["tool_choice"] == "auto"
    assert result.output_text is None
    assert result.tool_calls[0].name == "tasks.list"
    assert result.tool_calls[0].arguments == {"limit": 1}
    assert result.metadata["provider_request_id"] == "req-chat-1"
