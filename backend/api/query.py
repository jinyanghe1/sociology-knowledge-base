# backend/api/query.py
from fastapi import APIRouter, HTTPException
from typing import Optional

from backend.models.schemas import (
    QueryRequest,
    QueryResponse,
    Source,
    QueryMode,
)
from backend.core_logic.embedding import get_embedding
from backend.vector_store.chroma_manager import ChromaManager

router = APIRouter(prefix="/api/query", tags=["query"])

chroma_manager = ChromaManager()


@router.post("", response_model=QueryResponse)
async def query_documents(request: QueryRequest):
    """Query documents using RAG."""
    try:
        query_embedding = get_embedding(request.question)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to generate embedding: {e}")

    # Build where filter from document_ids
    where_filter = None
    if request.document_ids:
        if len(request.document_ids) == 1:
            where_filter = {"document_id": request.document_ids[0]}

    try:
        results = chroma_manager.query(
            query_embedding=query_embedding,
            n_results=request.top_k,
            where=where_filter
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Query failed: {e}")

    sources = []
    context_chunks = []
    if results.get("ids") and len(results["ids"]) > 0:
        for i, chunk_id in enumerate(results["ids"][0]):
            doc_id = results["metadatas"][0][i].get("document_id", "") if results.get("metadatas") else ""

            if request.document_ids and doc_id not in request.document_ids:
                continue

            content = results["documents"][0][i]
            score = results["distances"][0][i] if results.get("distances") else 0.0

            sources.append(Source(
                chunk_id=chunk_id,
                document_id=doc_id,
                content=content,
                score=score
            ))
            context_chunks.append(content)

    if not sources:
        return QueryResponse(
            question=request.question,
            answer="No relevant documents found.",
            sources=[]
        )

    # Return chunks directly — Agent handles RAG reasoning
    return QueryResponse(
        question=request.question,
        answer=f"Found {len(sources)} relevant chunks. Use the sources below for RAG-enhanced reasoning.",
        sources=sources
    )


@router.get("/count")
async def get_chunk_count():
    return {"count": chroma_manager.count()}
