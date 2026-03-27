from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from app.application.conversations.kernel.tool_adapter import (
    build_tool_definition,
    to_anthropic_tools,
    to_openai_tools,
)


class Priority(StrEnum):
    LOW = "low"
    HIGH = "high"


class SampleToolInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(..., description="标题")
    due_at: datetime = Field(..., description="截止时间")
    priority: Priority = Field(default=Priority.LOW, description="优先级")
    note: str | None = Field(default=None, description="备注")


def test_build_tool_definition_uses_pydantic_schema() -> None:
    definition = build_tool_definition(
        name="tasks.schedule",
        description="创建一个带时间的待办。",
        input_model=SampleToolInput,
    )

    assert definition.name == "tasks.schedule"
    assert definition.description == "创建一个带时间的待办。"
    assert definition.input_schema["type"] == "object"
    properties = definition.input_schema["properties"]
    assert isinstance(properties, dict)
    assert properties["due_at"]["format"] == "date-time"
    assert properties["priority"]["default"] == "low"
    assert definition.input_schema["additionalProperties"] is False


def test_tool_adapter_converts_to_openai_and_anthropic_shapes() -> None:
    definition = build_tool_definition(
        name="tasks.schedule",
        description="创建一个带时间的待办。",
        input_model=SampleToolInput,
    )

    openai_tools = to_openai_tools([definition])
    anthropic_tools = to_anthropic_tools([definition])
    expected_schema = dict(definition.input_schema)
    expected_schema.pop("title", None)

    assert openai_tools == [
        {
            "type": "function",
            "function": {
                "name": "tasks.schedule",
                "description": "创建一个带时间的待办。",
                "parameters": expected_schema,
            },
        }
    ]
    assert anthropic_tools == [
        {
            "name": "tasks.schedule",
            "description": "创建一个带时间的待办。",
            "input_schema": expected_schema,
        }
    ]
