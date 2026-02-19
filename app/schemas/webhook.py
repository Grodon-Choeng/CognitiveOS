from dataclasses import dataclass, field
from uuid import UUID


@dataclass
class CaptureRequest:
    content: str = field(
        metadata={
            "description": "笔记内容，支持多行文本",
            "examples": ["今天学到了一个新概念：认知负荷理论"],
        }
    )
    source: str = field(
        default="im",
        metadata={
            "description": "来源标识，如 telegram、wechat、manual",
            "examples": ["telegram", "wechat"],
        },
    )


@dataclass
class CaptureResponse:
    uuid: UUID = field(
        metadata={
            "description": "知识项唯一标识，用于后续查询和操作",
            "examples": ["e238a58f-3d25-49fb-b80b-f8c0e33b76f3"],
        }
    )


@dataclass
class KnowledgeItemResponse:
    uuid: UUID = field(metadata={"description": "知识项唯一标识"})
    raw_text: str = field(metadata={"description": "原始文本（完整）"})
    structured_text: str | None = field(
        metadata={"description": "结构化文本（Markdown），未处理时为 null"}
    )
    source: str = field(metadata={"description": "来源标识"})
    tags: list[str] = field(metadata={"description": "标签列表"})
    links: list[str] = field(metadata={"description": "双链列表（Obsidian 格式）"})
    created_at: str = field(metadata={"description": "创建时间 (ISO 8601)"})
    updated_at: str = field(metadata={"description": "最后更新时间 (ISO 8601)"})


@dataclass
class KnowledgeItemListResponse:
    uuid: UUID = field(metadata={"description": "知识项唯一标识"})
    raw_text: str = field(metadata={"description": "原始文本（截断至 100 字符）"})
    source: str = field(metadata={"description": "来源标识"})
    tags: list[str] = field(metadata={"description": "标签列表"})
    created_at: str = field(metadata={"description": "创建时间 (ISO 8601)"})


@dataclass
class StructuredResponse:
    uuid: UUID = field(metadata={"description": "知识项唯一标识"})
    title: str = field(metadata={"description": "提取的标题"})
    file_path: str | None = field(
        metadata={"description": "生成的 Markdown 文件路径，失败时为 null"}
    )


@dataclass
class ErrorResponse:
    error: str = field(metadata={"description": "错误代码"})
    detail: str | None = field(default=None, metadata={"description": "错误详情信息"})
