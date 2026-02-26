from uuid import UUID

from dishka import FromDishka
from dishka.integrations.litestar import inject
from litestar import Controller, post

from app.schemas import (
    IndexResponse,
    KnowledgeItemResponse,
    RAGRequest,
    RAGResponse,
    RebuildIndexResponse,
    SearchRequest,
    SearchResult,
)
from app.services import RetrievalService


class RetrievalController(Controller):
    path = ""
    tags = ["检索"]

    @post(
        path="/search",
        summary="语义搜索",
        description="基于向量相似度搜索知识库，返回与查询最相关的知识项。距离值越小表示相似度越高。",
    )
    @inject
    async def search(
        self,
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

    @post(
        path="/rag",
        summary="RAG 问答",
        description="基于知识库的检索增强生成。先检索相关知识项，再由 LLM 生成回答，并引用来源。",
    )
    @inject
    async def rag(
        self,
        data: RAGRequest,
        retrieval_service: FromDishka[RetrievalService],
    ) -> RAGResponse:
        answer = await retrieval_service.rag_query(data.query, data.top_k, user_id=data.user_id)

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

    @post(
        path="/index/{item_uuid:uuid}",
        summary="索引知识项",
        description="为单个知识项生成向量索引，使其可被语义搜索检索到。",
    )
    @inject
    async def index(
        self,
        item_uuid: UUID,
        retrieval_service: FromDishka[RetrievalService],
    ) -> IndexResponse:
        item = await retrieval_service.knowledge_service.get_by_uuid(item_uuid)
        await retrieval_service.index_item(item)
        return IndexResponse(status="indexed", uuid=str(item_uuid))

    @post(
        path="/index/rebuild",
        summary="重建索引",
        description="重建全部向量索引，处理所有未索引的知识项。适用于批量导入数据后的初始化。",
    )
    @inject
    async def rebuild(
        self, retrieval_service: FromDishka[RetrievalService]
    ) -> RebuildIndexResponse:
        count = await retrieval_service.rebuild_index()
        return RebuildIndexResponse(status="rebuilt", indexed_count=count)
