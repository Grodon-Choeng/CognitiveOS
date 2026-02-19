from dataclasses import dataclass, field


@dataclass
class CursorPaginationResponse[T]:
    items: list[T] = field(metadata={"description": "数据列表"})
    next_cursor: str | None = field(metadata={"description": "下一页游标，无更多数据时为 null"})
    has_more: bool = field(metadata={"description": "是否还有更多数据"})
