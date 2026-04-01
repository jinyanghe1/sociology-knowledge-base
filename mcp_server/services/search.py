"""Vector search service for the MCP server."""

from __future__ import annotations

from typing import List, Optional

from backend.core_logic.embedding import get_embedding
from backend.vector_store.chroma_manager import ChromaManager
from mcp_server.catalog import DocumentCatalog
from mcp_server.models import SearchHit, SearchResult, StatsResult


class SearchService:
    """Execute vector search and enrich hits with document metadata."""

    def __init__(self, *, chroma_manager: ChromaManager, catalog: DocumentCatalog):
        self.chroma_manager = chroma_manager
        self.catalog = catalog

    def rag_search(
        self,
        query: str,
        *,
        top_k: int = 5,
        document_ids: Optional[List[str]] = None,
    ) -> SearchResult:
        if top_k <= 0:
            raise ValueError("top_k must be greater than 0")

        query_embedding = get_embedding(query)
        where = None
        if document_ids and len(document_ids) == 1:
            where = {"document_id": document_ids[0]}

        raw_results = self.chroma_manager.query(
            query_embedding=query_embedding,
            n_results=max(top_k * 3, top_k),
            where=where,
        )

        ids = raw_results.get("ids") or [[]]
        documents = raw_results.get("documents") or [[]]
        metadatas = raw_results.get("metadatas") or [[]]
        distances = raw_results.get("distances") or [[]]

        hits: List[SearchHit] = []
        for index, chunk_id in enumerate(ids[0]):
            metadata = metadatas[0][index] if metadatas and metadatas[0] else {}
            document_id = metadata.get("document_id", "")
            if document_ids and document_id not in document_ids:
                continue

            catalog_record = self.catalog.get(document_id)
            distance = float(distances[0][index]) if distances and distances[0] else 0.0
            score = max(0.0, min(1.0, 1.0 - distance))
            hits.append(
                SearchHit(
                    chunk_id=chunk_id,
                    document_id=document_id,
                    filename=metadata.get("filename") or (catalog_record.filename if catalog_record else ""),
                    path=metadata.get("path") or (catalog_record.path if catalog_record else ""),
                    content=documents[0][index],
                    score=score,
                    metadata=metadata,
                )
            )
            if len(hits) >= top_k:
                break

        return SearchResult(
            query=query,
            total_hits=len(hits),
            hits=hits,
            note=None if hits else "No indexed content matched the query.",
        )

    def get_stats(self) -> StatsResult:
        stats = self.chroma_manager.get_stats()
        return StatsResult(
            documents_count=len(self.catalog.list_documents()),
            chunks_count=self.chroma_manager.count(),
            collection_name=stats["collection_name"],
            cache_size=stats["cache_size"],
        )
