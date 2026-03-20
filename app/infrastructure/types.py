# JSON 结构化类型别名：
# 用于边界层（LLM/tool/integration/agent）传递结构化数据时减少 Any 的蔓延。
type JSONPrimitive = str | int | float | bool | None
type JSONValue = JSONPrimitive | list["JSONValue"] | dict[str, "JSONValue"]
type JSONObject = dict[str, JSONValue]
