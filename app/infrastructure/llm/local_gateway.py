from typing import Any, Protocol

import httpx

from app.infrastructure.llm.gateway import LLMGateway
from app.infrastructure.llm.models import GenerateRequest, GenerateResult
from app.infrastructure.types import JSONObject


class HTTPResponseProtocol(Protocol):
    def raise_for_status(self) -> None: ...

    def json(self) -> Any: ...


class LocalLLMRequestSender(Protocol):
    async def __call__(
        self,
        *,
        url: str,
        payload: JSONObject,
        timeout_seconds: float,
    ) -> HTTPResponseProtocol: ...


class LocalChatLLMGateway(LLMGateway):
    def __init__(
        self,
        *,
        model: str,
        base_url: str,
        timeout_seconds: float = 10.0,
        sender: LocalLLMRequestSender | None = None,
    ) -> None:
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.sender = sender or _default_local_sender

    async def generate(self, request: GenerateRequest) -> GenerateResult:
        response = await self.sender(
            url=self.base_url,
            payload={
                "model": request.model or self.model,
                "system_prompt": request.system_prompt or "",
                "input": request.prompt,
            },
            timeout_seconds=self.timeout_seconds,
        )
        response.raise_for_status()
        body = response.json()
        content = _extract_local_content(body)
        usage = _extract_local_usage(body)
        metadata = _extract_local_metadata(body)
        return GenerateResult(
            content=content,
            model=_extract_local_model(body, request.model or self.model),
            provider="local",
            usage=usage,
            raw_output=body if isinstance(body, dict) else {},
            metadata=metadata,
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


def _extract_local_content(body: Any) -> str:
    if not isinstance(body, dict):
        raise ValueError("本地 LLM 响应格式不合法。")
    output = body.get("output")
    if not isinstance(output, list) or not output:
        raise ValueError("本地 LLM 响应缺少 output。")

    for item in output:
        if not isinstance(item, dict):
            continue
        if item.get("type") != "message":
            continue
        content = item.get("content")
        if isinstance(content, str) and content.strip():
            return content.strip()

    for item in output:
        if not isinstance(item, dict):
            continue
        content = item.get("content")
        if isinstance(content, str) and content.strip():
            return content.strip()

    raise ValueError("本地 LLM 响应缺少可解析的 content。")


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
    stats = body.get("stats")
    if isinstance(stats, dict):
        time_to_first_token_seconds = stats.get("time_to_first_token_seconds")
        tokens_per_second = stats.get("tokens_per_second")
        if isinstance(time_to_first_token_seconds, (int, float)):
            metadata["time_to_first_token_seconds"] = float(time_to_first_token_seconds)
        if isinstance(tokens_per_second, (int, float)):
            metadata["tokens_per_second"] = float(tokens_per_second)
    return metadata


def _extract_local_model(body: Any, default_model: str) -> str:
    if not isinstance(body, dict):
        return default_model
    model_instance_id = body.get("model_instance_id")
    if isinstance(model_instance_id, str) and model_instance_id.strip():
        return model_instance_id
    return default_model
