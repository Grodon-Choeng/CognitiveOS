import pytest

from app.infrastructure.agents.local_chat_runtime import LocalChatAgentRuntime
from app.infrastructure.agents.models import AgentChatTurnRequest, ChatMessage
from app.infrastructure.tools.mcp.protocol import ToolDefinition


class FakeResponse:
    def raise_for_status(self) -> None:
        return None

    def json(self) -> object:
        return {
            "model_instance_id": "qwen/qwen3-8b",
            "output": [
                {
                    "type": "tool_call",
                    "id": "call_local_1",
                    "name": "overview.get",
                    "arguments": {"recent_activity_limit": 3},
                },
                {"type": "message", "content": "这里是最终回复"},
            ],
            "stats": {
                "input_tokens": 12,
                "total_output_tokens": 18,
            },
            "response_id": "resp_local_1",
            "stop_reason": "message",
        }


@pytest.mark.asyncio
async def test_local_chat_agent_runtime_builds_payload_and_parses_output() -> None:
    captured: dict[str, object] = {}

    async def fake_sender(**kwargs: object) -> FakeResponse:
        captured.update(kwargs)
        return FakeResponse()

    runtime = LocalChatAgentRuntime(
        model="qwen/qwen3-8b",
        base_url="http://localhost:1234/api/v1/chat",
        sender=fake_sender,
    )

    result = await runtime.run_chat_turn(
        AgentChatTurnRequest(
            system_prompt="你是本地测试助手",
            messages=[ChatMessage(role="user", content="给我看概览")],
            tools=[
                ToolDefinition(
                    name="overview.get",
                    description="查看概览。",
                    input_schema={
                        "type": "object",
                        "properties": {
                            "recent_activity_limit": {"type": "integer"},
                        },
                    },
                )
            ],
            provider="local",
            model="qwen/qwen3-8b",
        )
    )

    assert captured["url"] == "http://localhost:1234/api/v1/chat"
    payload = captured["payload"]
    assert payload == {
        "model": "qwen/qwen3-8b",
        "system_prompt": "你是本地测试助手",
        "messages": [{"role": "user", "content": "给我看概览"}],
        "tools": [
            {
                "name": "overview.get",
                "description": "查看概览。",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "recent_activity_limit": {"type": "integer"},
                    },
                },
            }
        ],
        "tool_choice": "auto",
    }
    assert result.tool_calls[0].name == "overview.get"
    assert result.tool_calls[0].arguments == {"recent_activity_limit": 3}
    assert result.output_text == "这里是最终回复"
    assert result.usage["total_tokens"] == 30
    assert result.metadata["provider_request_id"] == "resp_local_1"
