from typing import Any, Protocol, cast

import httpx

from app.application.conversations.kernel.tool_adapter import to_anthropic_tools
from app.infrastructure.agents.models import (
    AgentChatTurnRequest,
    AgentChatTurnResult,
    AgentToolCall,
    ChatMessage,
)
from app.infrastructure.agents.runtime import AgentChatRuntime
from app.infrastructure.types import JSONObject, JSONValue


class HTTPResponseProtocol(Protocol):
    def raise_for_status(self) -> None: ...

    def json(self) -> Any: ...


class LocalAgentChatRequestSender(Protocol):
    async def __call__(
        self,
        *,
        url: str,
        payload: JSONObject,
        timeout_seconds: float,
    ) -> HTTPResponseProtocol: ...


class LocalChatAgentRuntime(AgentChatRuntime):
    def __init__(
        self,
        *,
        model: str,
        base_url: str,
        timeout_seconds: float = 20.0,
        sender: LocalAgentChatRequestSender | None = None,
    ) -> None:
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.sender = sender or _default_local_sender

    async def run_chat_turn(self, request: AgentChatTurnRequest) -> AgentChatTurnResult:
        response = await self.sender(
            url=self.base_url,
            payload=_build_local_chat_payload(request=request, default_model=self.model),
            timeout_seconds=self.timeout_seconds,
        )
        response.raise_for_status()
        body = response.json()
        return _parse_local_chat_response(
            body=body,
            default_model=request.model or self.model,
        )


async def _default_local_sender(
    *,
    url: str,
    payload: JSONObject,
    timeout_seconds: float,
) -> httpx.Response:
    async with httpx.AsyncClient(timeout=timeout_seconds, trust_env=False) as client:
        return await client.post(
            url,
            headers={"Content-Type": "application/json"},
            json=payload,
        )


def _build_local_chat_payload(
    *,
    request: AgentChatTurnRequest,
    default_model: str,
) -> JSONObject:
    payload: JSONObject = {
        "model": request.model or default_model,
        "system_prompt": request.system_prompt or "",
        "messages": [_to_local_message(message) for message in request.messages],
        "tool_choice": request.tool_choice,
    }
    if request.tools:
        payload["tools"] = to_anthropic_tools(request.tools)
    return payload


def _to_local_message(message: ChatMessage) -> JSONObject:
    payload: JSONObject = {
        "role": message.role,
        "content": message.content or "",
    }
    if message.name is not None:
        payload["name"] = message.name
    if message.tool_call_id is not None:
        payload["tool_call_id"] = message.tool_call_id
    if message.tool_calls:
        payload["tool_calls"] = [
            {
                "id": tool_call.id,
                "name": tool_call.name,
                "arguments": tool_call.arguments,
            }
            for tool_call in message.tool_calls
        ]
    return payload


def _parse_local_chat_response(
    *,
    body: Any,
    default_model: str,
) -> AgentChatTurnResult:
    if not isinstance(body, dict):
        raise ValueError("本地 agent chat 响应格式不合法。")
    output = body.get("output")
    if not isinstance(output, list) or not output:
        raise ValueError("本地 agent chat 响应缺少 output。")

    output_text: str | None = None
    tool_calls: list[AgentToolCall] = []
    for item in output:
        if not isinstance(item, dict):
            continue
        item_type = item.get("type")
        if item_type == "tool_call":
            name = item.get("name")
            arguments = item.get("arguments")
            if isinstance(name, str):
                tool_calls.append(
                    AgentToolCall(
                        id=str(item.get("id") or f"call_{len(tool_calls) + 1}"),
                        name=name,
                        arguments=_coerce_arguments(arguments),
                    )
                )
            continue
        if item_type == "message":
            content = item.get("content")
            if isinstance(content, str) and content.strip():
                output_text = content.strip()
                break

    return AgentChatTurnResult(
        output_text=output_text,
        tool_calls=tool_calls,
        stop_reason=_optional_string(body.get("stop_reason")),
        provider="local",
        model=_extract_local_model(body, default_model),
        usage=_extract_local_usage(body),
        raw_output=body if isinstance(body, dict) else {},
        metadata=_extract_local_metadata(body),
    )


def _coerce_arguments(arguments: object) -> JSONObject:
    if isinstance(arguments, dict):
        return {str(key): cast(JSONValue, value) for key, value in arguments.items()}
    return {}


def _extract_local_usage(body: Any) -> dict[str, int]:
    if not isinstance(body, dict):
        return {}
    stats = body.get("stats")
    if not isinstance(stats, dict):
        return {}

    prompt_tokens = stats.get("input_tokens")
    completion_tokens = stats.get("total_output_tokens")
    result: dict[str, int] = {}
    if isinstance(prompt_tokens, int):
        result["prompt_tokens"] = prompt_tokens
    if isinstance(completion_tokens, int):
        result["completion_tokens"] = completion_tokens
    if isinstance(prompt_tokens, int) and isinstance(completion_tokens, int):
        result["total_tokens"] = prompt_tokens + completion_tokens
    return result


def _extract_local_metadata(body: Any) -> JSONObject:
    if not isinstance(body, dict):
        return {}
    metadata: JSONObject = {}
    response_id = body.get("response_id")
    if isinstance(response_id, str):
        metadata["provider_request_id"] = response_id
    return metadata


def _extract_local_model(body: Any, default_model: str) -> str:
    if not isinstance(body, dict):
        return default_model
    model_instance_id = body.get("model_instance_id")
    if isinstance(model_instance_id, str) and model_instance_id.strip():
        return model_instance_id
    return default_model


def _optional_string(value: object) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None
