import json
from typing import Any, Protocol, cast

import httpx

from app.application.conversations.kernel.tool_adapter import to_openai_tools
from app.infrastructure.agents.models import (
    AgentChatTurnRequest,
    AgentChatTurnResult,
    AgentToolCall,
    ChatMessage,
)
from app.infrastructure.agents.runtime import AgentChatRuntime
from app.infrastructure.types import JSONObject, JSONValue


class HTTPResponseProtocol(Protocol):
    headers: Any

    def raise_for_status(self) -> None: ...

    def json(self) -> Any: ...


class OpenAIChatRequestSender(Protocol):
    async def __call__(
        self,
        *,
        url: str,
        headers: dict[str, str],
        payload: JSONObject,
        timeout_seconds: float,
    ) -> HTTPResponseProtocol: ...


class OpenAIChatAgentRuntime(AgentChatRuntime):
    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        base_url: str,
        timeout_seconds: float = 20.0,
        sender: OpenAIChatRequestSender | None = None,
    ) -> None:
        self.api_key = api_key
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.sender = sender or _default_openai_sender

    async def run_chat_turn(self, request: AgentChatTurnRequest) -> AgentChatTurnResult:
        payload = _build_openai_chat_payload(request=request, default_model=self.model)
        response = await self.sender(
            url=f"{self.base_url}/chat/completions",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            payload=payload,
            timeout_seconds=self.timeout_seconds,
        )
        response.raise_for_status()
        body = response.json()
        request_id = _extract_openai_request_id(response.headers)
        return _parse_openai_chat_response(
            body=body,
            default_model=request.model or self.model,
            request_id=request_id,
        )


async def _default_openai_sender(
    *,
    url: str,
    headers: dict[str, str],
    payload: JSONObject,
    timeout_seconds: float,
) -> httpx.Response:
    async with httpx.AsyncClient(timeout=timeout_seconds) as client:
        return await client.post(url, headers=headers, json=payload)


def _build_openai_chat_payload(
    *,
    request: AgentChatTurnRequest,
    default_model: str,
) -> JSONObject:
    messages: list[JSONObject] = []
    if request.system_prompt:
        messages.append({"role": "system", "content": request.system_prompt})
    messages.extend(_to_openai_message(message) for message in request.messages)
    payload: JSONObject = {
        "model": request.model or default_model,
        "messages": cast(JSONValue, messages),
        "temperature": 0,
    }
    if request.tools:
        payload["tools"] = to_openai_tools(request.tools)
        payload["tool_choice"] = request.tool_choice
    return payload


def _to_openai_message(message: ChatMessage) -> JSONObject:
    if message.role == "tool":
        payload: JSONObject = {
            "role": "tool",
            "content": message.content or "",
            "tool_call_id": message.tool_call_id or "",
        }
        if message.name is not None:
            payload["name"] = message.name
        return payload

    payload = {
        "role": message.role,
        "content": message.content or "",
    }
    if message.tool_calls:
        payload["tool_calls"] = [
            {
                "id": tool_call.id,
                "type": "function",
                "function": {
                    "name": tool_call.name,
                    "arguments": json.dumps(tool_call.arguments, ensure_ascii=False),
                },
            }
            for tool_call in message.tool_calls
        ]
    return payload


def _parse_openai_chat_response(
    *,
    body: Any,
    default_model: str,
    request_id: str | None,
) -> AgentChatTurnResult:
    if not isinstance(body, dict):
        raise ValueError("OpenAI chat 响应格式不合法。")
    choices = body.get("choices")
    if not isinstance(choices, list) or not choices:
        raise ValueError("OpenAI chat 响应缺少 choices。")
    first_choice = choices[0]
    if not isinstance(first_choice, dict):
        raise ValueError("OpenAI chat choice 格式不合法。")
    message = first_choice.get("message")
    if not isinstance(message, dict):
        raise ValueError("OpenAI chat 响应缺少 message。")
    return AgentChatTurnResult(
        output_text=_extract_openai_message_content(message),
        tool_calls=_extract_openai_tool_calls(message),
        stop_reason=_optional_string(first_choice.get("finish_reason")),
        provider="openai",
        model=str(body.get("model") or default_model),
        usage=_extract_openai_usage(body),
        raw_output=body if isinstance(body, dict) else {},
        metadata={"provider_request_id": request_id} if request_id else {},
    )


def _extract_openai_message_content(message: dict[str, object]) -> str | None:
    content = message.get("content")
    if isinstance(content, str):
        stripped = content.strip()
        return stripped or None
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, dict):
                text = item.get("text")
                if isinstance(text, str) and text.strip():
                    parts.append(text.strip())
        if parts:
            return "\n".join(parts)
    return None


def _extract_openai_tool_calls(message: dict[str, object]) -> list[AgentToolCall]:
    raw_tool_calls = message.get("tool_calls")
    if not isinstance(raw_tool_calls, list):
        return []

    tool_calls: list[AgentToolCall] = []
    for item in raw_tool_calls:
        if not isinstance(item, dict):
            continue
        function_payload = item.get("function")
        if not isinstance(function_payload, dict):
            continue
        name = function_payload.get("name")
        arguments = function_payload.get("arguments")
        if not isinstance(name, str):
            continue
        parsed_arguments = _parse_tool_arguments(arguments)
        tool_calls.append(
            AgentToolCall(
                id=str(item.get("id") or f"call_{len(tool_calls) + 1}"),
                name=name,
                arguments=parsed_arguments,
            )
        )
    return tool_calls


def _parse_tool_arguments(arguments: object) -> JSONObject:
    if isinstance(arguments, dict):
        return {str(key): cast(JSONValue, value) for key, value in arguments.items()}
    if not isinstance(arguments, str):
        return {}
    parsed = json.loads(arguments)
    if not isinstance(parsed, dict):
        raise ValueError("OpenAI tool call arguments 必须是 object。")
    return {str(key): cast(JSONValue, value) for key, value in parsed.items()}


def _extract_openai_usage(body: Any) -> dict[str, int]:
    if not isinstance(body, dict):
        return {}
    usage = body.get("usage")
    if not isinstance(usage, dict):
        return {}
    result: dict[str, int] = {}
    for key in ("prompt_tokens", "completion_tokens", "total_tokens"):
        value = usage.get(key)
        if isinstance(value, int):
            result[key] = value
    return result


def _extract_openai_request_id(headers: Any) -> str | None:
    if headers is None:
        return None
    request_id = headers.get("x-request-id")
    if isinstance(request_id, str):
        return request_id
    return None


def _optional_string(value: object) -> str | None:
    if isinstance(value, str) and value.strip():
        return value
    return None
