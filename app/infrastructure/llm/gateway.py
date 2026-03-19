from typing import Protocol

from app.infrastructure.llm.models import GenerateRequest, GenerateResult


class LLMGateway(Protocol):
    async def generate(self, request: GenerateRequest) -> GenerateResult: ...


class NoopLLMGateway:
    async def generate(self, request: GenerateRequest) -> GenerateResult:
        _ = request
        raise NotImplementedError("LLM 模型提供商尚未接入具体实现。")
