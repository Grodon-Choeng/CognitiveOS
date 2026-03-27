"""智能体运行时契约与实现。"""

from app.infrastructure.agents.local_chat_runtime import LocalChatAgentRuntime
from app.infrastructure.agents.models import (
    AgentChatTurnRequest,
    AgentChatTurnResult,
    AgentToolCall,
    AgentTurnRequest,
    AgentTurnResult,
    ChatMessage,
)
from app.infrastructure.agents.openai_chat_runtime import OpenAIChatAgentRuntime
from app.infrastructure.agents.runtime import (
    AgentChatRuntime,
    AgentRuntime,
    NoopAgentRuntime,
    RecordingAgentChatRuntime,
    RecordingAgentRuntime,
)

__all__ = [
    "AgentChatRuntime",
    "AgentChatTurnRequest",
    "AgentChatTurnResult",
    "AgentRuntime",
    "AgentToolCall",
    "AgentTurnRequest",
    "AgentTurnResult",
    "ChatMessage",
    "LocalChatAgentRuntime",
    "NoopAgentRuntime",
    "OpenAIChatAgentRuntime",
    "RecordingAgentChatRuntime",
    "RecordingAgentRuntime",
]
