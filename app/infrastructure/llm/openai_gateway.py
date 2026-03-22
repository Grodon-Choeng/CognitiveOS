from typing import Any, Protocol, cast

import httpx

from app.infrastructure.llm.gateway import LLMGateway
from app.infrastructure.llm.models import GenerateRequest, GenerateResult
from app.infrastructure.types import JSONObject, JSONValue


class HTTPResponseProtocol(Protocol):
    headers: Any

    def raise_for_status(self) -> None: ...

    def json(self) -> Any: ...


class OpenAIRequestSender(Protocol):
    async def __call__(
        self,
        *,
        url: str,
        headers: dict[str, str],
        payload: JSONObject,
        timeout_seconds: float,
    ) -> HTTPResponseProtocol: ...


class OpenAIChatLLMGateway(LLMGateway):
    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        base_url: str,
        timeout_seconds: float = 10.0,
        sender: OpenAIRequestSender | None = None,
    ) -> None:
        self.api_key = api_key
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.sender = sender or _default_openai_sender

    async def generate(self, request: GenerateRequest) -> GenerateResult:
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
        content = _extract_openai_content(body)
        usage = _extract_openai_usage(body)
        request_id = _extract_openai_request_id(response.headers)
        return GenerateResult(
            content=content,
            model=str(body.get("model") or request.model or self.model),
            provider="openai",
            usage=usage,
            raw_output=body if isinstance(body, dict) else {},
            metadata={"provider_request_id": request_id} if request_id is not None else {},
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
    request: GenerateRequest,
    default_model: str,
) -> JSONObject:
    messages: list[JSONObject] = []
    if request.system_prompt:
        messages.append({"role": "system", "content": request.system_prompt})
    messages.append({"role": "user", "content": request.prompt})
    return {
        "model": request.model or default_model,
        "messages": cast(JSONValue, messages),
        "temperature": 0,
        "response_format": {"type": "json_object"},
    }


def _extract_openai_content(body: Any) -> str:
    if not isinstance(body, dict):
        raise ValueError("OpenAI 响应格式不合法。")
    choices = body.get("choices")
    if not isinstance(choices, list) or not choices:
        raise ValueError("OpenAI 响应缺少 choices。")
    first_choice = choices[0]
    if not isinstance(first_choice, dict):
        raise ValueError("OpenAI choice 格式不合法。")
    message = first_choice.get("message")
    if not isinstance(message, dict):
        raise ValueError("OpenAI 响应缺少 message。")
    content = message.get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, dict):
                text = item.get("text")
                if isinstance(text, str):
                    parts.append(text)
        if parts:
            return "\n".join(parts)
    raise ValueError("OpenAI 响应缺少可解析的 content。")


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
