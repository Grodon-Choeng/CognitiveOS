from typing import Protocol

from app.infrastructure.agents.models import AgentTurnRequest, AgentTurnResult


class AgentRuntime(Protocol):
    async def run_turn(self, request: AgentTurnRequest) -> AgentTurnResult: ...


class NoopAgentRuntime:
    async def run_turn(self, request: AgentTurnRequest) -> AgentTurnResult:
        _ = request
        raise NotImplementedError("Agent 运行时尚未接入具体实现。")
