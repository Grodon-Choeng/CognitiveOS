import json
from pathlib import Path
from typing import cast

import pytest

from app.config.settings import Settings
from app.infrastructure.agents.models import (
    AgentChatTurnRequest,
    AgentChatTurnResult,
    AgentTurnRequest,
    AgentTurnResult,
    ChatMessage,
)
from app.infrastructure.agents.runtime import RecordingAgentChatRuntime, RecordingAgentRuntime
from app.infrastructure.db.session import get_session_factory
from app.infrastructure.llm.gateway import RecordingLLMGateway
from app.infrastructure.llm.models import GenerateRequest, GenerateResult
from app.infrastructure.types import JSONObject
from app.observability.model_invocations import (
    DatabaseModelInvocationRecorder,
    JsonlModelInvocationRecorder,
    ModelInvocationRecord,
    MultiModelInvocationRecorder,
    build_api_key_suffix,
)


class FakeLLMGateway:
    async def generate(self, request: GenerateRequest) -> GenerateResult:
        _ = request
        return GenerateResult(
            content="你好",
            model="gpt-test",
            provider="openai",
            usage={"input_tokens": 10, "output_tokens": 5, "total_tokens": 15},
            raw_output={"content": "你好", "finish_reason": "stop"},
            metadata={"provider_request_id": "req-1"},
        )


class FailingLLMGateway:
    async def generate(self, request: GenerateRequest) -> GenerateResult:
        _ = request
        raise RuntimeError("模型调用失败")


class FakeAgentRuntime:
    async def run_turn(self, request: AgentTurnRequest) -> AgentTurnResult:
        _ = request
        return AgentTurnResult(
            output_text="已处理",
            provider="anthropic",
            model="claude-test",
            usage={"input_tokens": 12, "output_tokens": 7, "total_tokens": 19},
            raw_output={"output_text": "已处理"},
            metadata={"agent_mode": "single_turn"},
        )


class FakeAgentChatRuntime:
    async def run_chat_turn(self, request: AgentChatTurnRequest) -> AgentChatTurnResult:
        _ = request
        return AgentChatTurnResult(
            output_text="聊天回合已处理",
            provider="openai",
            model="gpt-chat-test",
            usage={"prompt_tokens": 20, "completion_tokens": 8, "total_tokens": 28},
            raw_output={"output_text": "聊天回合已处理"},
            metadata={"agent_mode": "chat_turn"},
        )


class FakeDatabaseRecorder:
    def __init__(self) -> None:
        self.records: list[ModelInvocationRecord] = []

    async def record(self, record: ModelInvocationRecord) -> None:
        self.records.append(record)


def read_first_record(path: Path) -> JSONObject:
    lines = path.read_text(encoding="utf-8").splitlines()
    return cast(JSONObject, json.loads(lines[0]))


def test_build_api_key_suffix_returns_last_eight_chars() -> None:
    assert build_api_key_suffix("sk-1234567890abcdef") == "90abcdef"
    assert build_api_key_suffix("  key-1234  ") == "key-1234"
    assert build_api_key_suffix(None) is None


@pytest.mark.asyncio
async def test_recording_llm_gateway_records_success(tmp_path: Path) -> None:
    log_path = tmp_path / "model_invocations.jsonl"
    recorder = JsonlModelInvocationRecorder(str(log_path))
    gateway = RecordingLLMGateway(FakeLLMGateway(), recorder)

    await gateway.generate(
        GenerateRequest(
            prompt="你好",
            system_prompt="你是助手",
            provider="openai",
            model="gpt-test",
            session_id="session-1",
            conversation_id="conversation-1",
            trace_id="trace-1",
            chain_id="chain-1",
            request_id="request-1",
            api_key_suffix="90abcdef",
        )
    )

    record = read_first_record(log_path)
    assert record["operation"] == "llm.generate"
    assert record["provider"] == "openai"
    assert record["model"] == "gpt-test"
    assert record["api_key_suffix"] == "90abcdef"
    assert record["session_id"] == "session-1"
    assert record["trace_id"] == "trace-1"
    assert record["success"] is True
    assert record["usage"] == {
        "input_tokens": 10,
        "output_tokens": 5,
        "total_tokens": 15,
    }
    raw_input = cast(JSONObject, record["raw_input"])
    raw_output = cast(JSONObject, record["raw_output"])
    assert raw_input["prompt"] == "你好"
    assert raw_output["content"] == "你好"


@pytest.mark.asyncio
async def test_recording_llm_gateway_records_failure(tmp_path: Path) -> None:
    log_path = tmp_path / "model_invocations.jsonl"
    recorder = JsonlModelInvocationRecorder(str(log_path))
    gateway = RecordingLLMGateway(FailingLLMGateway(), recorder)

    with pytest.raises(RuntimeError):
        await gateway.generate(
            GenerateRequest(
                prompt="失败测试",
                provider="openai",
                model="gpt-test",
                api_key_suffix="90abcdef",
            )
        )

    record = read_first_record(log_path)
    assert record["success"] is False
    assert record["error_type"] == "RuntimeError"
    assert record["error_message"] == "模型调用失败"


@pytest.mark.asyncio
async def test_recording_agent_runtime_records_success(tmp_path: Path) -> None:
    log_path = tmp_path / "model_invocations.jsonl"
    recorder = JsonlModelInvocationRecorder(str(log_path))
    runtime = RecordingAgentRuntime(FakeAgentRuntime(), recorder)

    await runtime.run_turn(
        AgentTurnRequest(
            user_message="帮我总结一下",
            conversation_id="conversation-2",
            session_id="session-2",
            trace_id="trace-2",
            chain_id="chain-2",
            request_id="request-2",
            provider="anthropic",
            model="claude-test",
            api_key_suffix="abcdef12",
        )
    )

    record = read_first_record(log_path)
    assert record["operation"] == "agent.run_turn"
    assert record["provider"] == "anthropic"
    assert record["model"] == "claude-test"
    assert record["session_id"] == "session-2"
    assert record["conversation_id"] == "conversation-2"
    raw_input = cast(JSONObject, record["raw_input"])
    raw_output = cast(JSONObject, record["raw_output"])
    assert raw_input["user_message"] == "帮我总结一下"
    assert raw_output["output_text"] == "已处理"


@pytest.mark.asyncio
async def test_recording_agent_chat_runtime_records_success(tmp_path: Path) -> None:
    log_path = tmp_path / "model_invocations.jsonl"
    recorder = JsonlModelInvocationRecorder(str(log_path))
    runtime = RecordingAgentChatRuntime(FakeAgentChatRuntime(), recorder)

    await runtime.run_chat_turn(
        AgentChatTurnRequest(
            system_prompt="你是测试助手",
            messages=[ChatMessage(role="user", content="帮我总结一下")],
            conversation_id="conversation-3",
            session_id="session-3",
            trace_id="trace-3",
            chain_id="chain-3",
            request_id="request-3",
            provider="openai",
            model="gpt-chat-test",
            api_key_suffix="abcdef12",
        )
    )

    record = read_first_record(log_path)
    assert record["operation"] == "agent.chat_turn"
    assert record["provider"] == "openai"
    assert record["model"] == "gpt-chat-test"
    raw_input = cast(JSONObject, record["raw_input"])
    raw_output = cast(JSONObject, record["raw_output"])
    assert raw_input["system_prompt"] == "你是测试助手"
    messages = cast(list[JSONObject], raw_input["messages"])
    assert messages[0]["content"] == "帮我总结一下"
    assert raw_output["output_text"] == "聊天回合已处理"


@pytest.mark.asyncio
async def test_multi_model_invocation_recorder_writes_to_both_channels(
    tmp_path: Path,
) -> None:
    log_path = tmp_path / "model_invocations.jsonl"
    jsonl_recorder = JsonlModelInvocationRecorder(str(log_path))
    database_recorder = FakeDatabaseRecorder()
    recorder = MultiModelInvocationRecorder([database_recorder, jsonl_recorder])

    await recorder.record(
        build_sample_record(
            provider="openai",
            model="gpt-test",
        )
    )

    jsonl_record = read_first_record(log_path)
    assert jsonl_record["provider"] == "openai"
    assert len(database_recorder.records) == 1


def build_sample_record(*, provider: str, model: str) -> ModelInvocationRecord:
    return ModelInvocationRecord.create(
        operation="llm.generate",
        model_kind="llm",
        provider=provider,
        model=model,
        api_key_suffix="90abcdef",
        session_id="session-1",
        conversation_id="conversation-1",
        trace_id="trace-1",
        chain_id="chain-1",
        request_id="request-1",
        latency_ms=12.5,
        usage={"input_tokens": 10, "output_tokens": 5, "total_tokens": 15},
        raw_input={"prompt": "你好"},
        raw_output={"content": "你好"},
    )


def test_database_model_invocation_recorder_can_be_constructed() -> None:
    settings = Settings(
        database_url="postgresql+asyncpg://cognitiveos:cognitiveos@localhost:5432/cognitiveos"
    )
    session_factory = get_session_factory(settings)
    recorder = DatabaseModelInvocationRecorder(session_factory=session_factory)

    assert recorder.enabled is True
