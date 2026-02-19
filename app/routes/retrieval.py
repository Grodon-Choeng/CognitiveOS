from dataclasses import dataclass
from uuid import UUID

from litestar import post
from dishka import FromDishka
from dishka.integrations.litestar import inject

from app.schemas.webhook import KnowledgeItemResponse
from app.services.retrieval_service import RetrievalService


@dataclass
class SearchRequest:
    query: str
    top_k: int = 5


@dataclass
class SearchResult:
    item: KnowledgeItemResponse
    distance: float


@dataclass
class RAGRequest:
    query: str
    top_k: int = 5


@dataclass
class RAGResponse:
    query: str
    answer: str
    sources: list[KnowledgeItemResponse]


@post("/search")
@inject
async def search(
    data: SearchRequest,
    retrieval_service: FromDishka[RetrievalService],
) -> list[SearchResult]:
    results = await retrieval_service.search_similar(data.query, data.top_k)

    search_results = []
    for result in results:
        item = await retrieval_service.knowledge_service.get_by_id(result["item_id"])
        search_results.append(
            SearchResult(
                item=KnowledgeItemResponse(
                    uuid=item.uuid,
                    raw_text=item.raw_text,
                    structured_text=item.structured_text,
                    source=item.source,
                    tags=item.tags or [],
                    links=item.links or [],
                    created_at=item.created_at.isoformat() if item.created_at else "",
                    updated_at=item.updated_at.isoformat() if item.updated_at else "",
                ),
                distance=result["distance"],
            )
        )

    return search_results


@post("/rag")
@inject
async def rag_query(
    data: RAGRequest,
    retrieval_service: FromDishka[RetrievalService],
) -> RAGResponse:
    answer = await retrieval_service.rag_query(data.query, data.top_k)

    items = await retrieval_service.search_and_retrieve(data.query, data.top_k)

    sources = [
        KnowledgeItemResponse(
            uuid=item.uuid,
            raw_text=item.raw_text,
            structured_text=item.structured_text,
            source=item.source,
            tags=item.tags or [],
            links=item.links or [],
            created_at=item.created_at.isoformat() if item.created_at else "",
            updated_at=item.updated_at.isoformat() if item.updated_at else "",
        )
        for item in items
    ]

    return RAGResponse(query=data.query, answer=answer, sources=sources)


@post("/index/{item_uuid:uuid}")
@inject
async def index_item(
    item_uuid: UUID,
    retrieval_service: FromDishka[RetrievalService],
) -> dict:
    item = await retrieval_service.knowledge_service.get_by_uuid(item_uuid)
    await retrieval_service.index_item(item)
    return {"status": "indexed", "uuid": str(item_uuid)}


@post("/index/rebuild")
@inject
async def rebuild_index(
    retrieval_service: FromDishka[RetrievalService],
) -> dict:
    count = await retrieval_service.rebuild_index()
    return {"status": "rebuilt", "indexed_count": count}
