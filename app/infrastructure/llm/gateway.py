from time import perf_counter
from typing import Protocol

from app.infrastructure.llm.models import GenerateRequest, GenerateResult
from app.infrastructure.types import JSONObject
from app.observability.model_invocations import ModelInvocationRecord, ModelInvocationRecorder


class LLMGateway(Protocol):
    async def generate(self, request: GenerateRequest) -> GenerateResult: ...


class NoopLLMGateway:
    async def generate(self, request: GenerateRequest) -> GenerateResult:
        _ = request
        raise NotImplementedError("LLM 模型提供商尚未接入具体实现。")


class RecordingLLMGateway:
    def __init__(
        self,
        inner: LLMGateway,
        recorder: ModelInvocationRecorder,
    ) -> None:
        self.inner = inner
        self.recorder = recorder

    async def generate(self, request: GenerateRequest) -> GenerateResult:
        started_at = perf_counter()

        try:
            result = await self.inner.generate(request)
        except Exception as exc:
            await self.recorder.record(
                ModelInvocationRecord.create(
                    operation="llm.generate",
                    model_kind=request.model_kind,
                    provider=request.provider,
                    model=request.model,
                    api_key_suffix=request.api_key_suffix,
                    session_id=request.session_id,
                    conversation_id=request.conversation_id,
                    trace_id=request.trace_id,
                    chain_id=request.chain_id,
                    request_id=request.request_id,
                    latency_ms=(perf_counter() - started_at) * 1000,
                    success=False,
                    error_type=type(exc).__name__,
                    error_message=str(exc),
                    raw_input=_build_llm_raw_input(request),
                    raw_output={},
                    metadata=request.metadata,
                )
            )
            raise

        await self.recorder.record(
            ModelInvocationRecord.create(
                operation="llm.generate",
                model_kind=request.model_kind,
                provider=result.provider or request.provider,
                model=result.model or request.model,
                api_key_suffix=request.api_key_suffix,
                session_id=request.session_id,
                conversation_id=request.conversation_id,
                trace_id=request.trace_id,
                chain_id=request.chain_id,
                request_id=request.request_id,
                latency_ms=(perf_counter() - started_at) * 1000,
                usage=result.usage,
                raw_input=_build_llm_raw_input(request),
                raw_output=_build_llm_raw_output(result),
                metadata={**request.metadata, **result.metadata},
            )
        )
        return result


def _build_llm_raw_input(request: GenerateRequest) -> JSONObject:
    if request.raw_input:
        return request.raw_input

    return {
        "prompt": request.prompt,
        "system_prompt": request.system_prompt,
        "metadata": request.metadata,
    }


def _build_llm_raw_output(result: GenerateResult) -> JSONObject:
    if result.raw_output:
        return result.raw_output

    return {
        "content": result.content,
        "usage": _build_usage_payload(result.usage),
        "metadata": result.metadata,
    }


def _build_usage_payload(usage: dict[str, int]) -> JSONObject:
    return {key: value for key, value in usage.items()}
