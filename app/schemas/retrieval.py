from dataclasses import dataclass, field

from app.schemas.webhook import KnowledgeItemResponse


@dataclass
class SearchRequest:
    query: str = field(
        metadata={
            "description": "搜索查询文本",
            "examples": ["学习笔记"],
        }
    )
    top_k: int = field(
        default=5,
        metadata={
            "description": "返回结果数量，最大 20",
            "examples": [5, 10],
        },
    )


@dataclass
class SearchResult:
    item: KnowledgeItemResponse = field(metadata={"description": "知识项详情"})
    distance: float = field(metadata={"description": "向量距离（越小越相似）"})


@dataclass
class RAGRequest:
    query: str = field(
        metadata={
            "description": "问题文本",
            "examples": ["我学过什么关于 Python 的内容？"],
        }
    )
    top_k: int = field(
        default=5,
        metadata={
            "description": "检索上下文数量",
            "examples": [5, 10],
        },
    )


@dataclass
class RAGResponse:
    query: str = field(metadata={"description": "原始问题"})
    answer: str = field(metadata={"description": "LLM 生成的回答"})
    sources: list[KnowledgeItemResponse] = field(metadata={"description": "引用的知识项列表"})


@dataclass
class IndexResponse:
    status: str = field(metadata={"description": "操作状态"})
    uuid: str | None = field(default=None, metadata={"description": "知识项 UUID"})


@dataclass
class RebuildIndexResponse:
    status: str = field(metadata={"description": "操作状态"})
    indexed_count: int = field(metadata={"description": "本次索引的知识项数量"})
