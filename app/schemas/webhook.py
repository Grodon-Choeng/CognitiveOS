from dataclasses import dataclass
from uuid import UUID


@dataclass
class CaptureRequest:
    content: str
    source: str = "im"


@dataclass
class CaptureResponse:
    uuid: UUID


@dataclass
class KnowledgeItemResponse:
    uuid: UUID
    raw_text: str
    structured_text: str | None
    source: str
    tags: list[str]
    links: list[str]
    created_at: str
    updated_at: str


@dataclass
class KnowledgeItemListResponse:
    uuid: UUID
    raw_text: str
    source: str
    tags: list[str]
    created_at: str


@dataclass
class StructuredResponse:
    uuid: UUID
    title: str
    file_path: str | None


@dataclass
class ErrorResponse:
    error: str
    detail: str | None = None
