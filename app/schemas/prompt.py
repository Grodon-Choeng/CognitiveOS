from dataclasses import dataclass, field


@dataclass
class PromptResponse:
    id: int = field(metadata={"description": "提示词 ID"})
    name: str = field(metadata={"description": "提示词名称（唯一）"})
    description: str | None = field(metadata={"description": "描述说明"})
    content: str = field(metadata={"description": "提示词内容"})
    category: str = field(metadata={"description": "分类标识"})
    created_at: str = field(metadata={"description": "创建时间 (ISO 8601)"})
    updated_at: str = field(metadata={"description": "更新时间 (ISO 8601)"})


@dataclass
class PromptCreateRequest:
    name: str = field(
        metadata={
            "description": "提示词名称（唯一）",
            "examples": ["custom_prompt"],
        }
    )
    content: str = field(
        metadata={
            "description": "提示词内容",
            "examples": ["这是一个自定义提示词..."],
        }
    )
    description: str | None = field(
        default=None,
        metadata={"description": "描述说明"},
    )
    category: str = field(
        default="general",
        metadata={
            "description": "分类标识",
            "examples": ["general", "rag", "summarization"],
        },
    )


@dataclass
class PromptUpdateRequest:
    content: str = field(
        metadata={
            "description": "新的提示词内容",
            "examples": ["更新后的提示词内容..."],
        }
    )
    description: str | None = field(
        default=None,
        metadata={"description": "新的描述说明"},
    )


@dataclass
class PromptDeleteResponse:
    status: str = field(metadata={"description": "操作状态"})
    name: str = field(metadata={"description": "被删除的提示词名称"})
