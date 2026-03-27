from collections.abc import Iterable
from copy import deepcopy

from pydantic import BaseModel

from app.infrastructure.tools.mcp.protocol import ToolDefinition
from app.infrastructure.types import JSONObject, JSONValue


def build_tool_definition(
    *,
    name: str,
    description: str,
    input_model: type[BaseModel],
) -> ToolDefinition:
    return ToolDefinition(
        name=name,
        description=description,
        input_schema=_normalize_schema(input_model.model_json_schema()),
        output_schema={},
    )


def to_openai_tools(definitions: Iterable[ToolDefinition]) -> list[JSONObject]:
    tools: list[JSONObject] = []
    for definition in definitions:
        tools.append(
            {
                "type": "function",
                "function": {
                    "name": definition.name,
                    "description": definition.description,
                    "parameters": _sanitize_schema_for_provider(definition.input_schema),
                },
            }
        )
    return tools


def to_anthropic_tools(definitions: Iterable[ToolDefinition]) -> list[JSONObject]:
    tools: list[JSONObject] = []
    for definition in definitions:
        tools.append(
            {
                "name": definition.name,
                "description": definition.description,
                "input_schema": _sanitize_schema_for_provider(definition.input_schema),
            }
        )
    return tools


def _sanitize_schema_for_provider(schema: JSONObject) -> JSONObject:
    sanitized = deepcopy(schema)
    sanitized.pop("title", None)
    return sanitized


def _normalize_schema(value: object) -> JSONObject:
    normalized = _normalize_json_value(value)
    if not isinstance(normalized, dict):
        raise TypeError("工具输入 schema 必须是 JSON object。")
    return normalized


def _normalize_json_value(value: object) -> JSONValue:
    if value is None or isinstance(value, str | int | float | bool):
        return value
    if isinstance(value, dict):
        return {str(key): _normalize_json_value(item) for key, item in value.items()}
    if isinstance(value, list | tuple):
        return [_normalize_json_value(item) for item in value]
    return str(value)
