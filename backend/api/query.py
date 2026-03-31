# backend/api/query.py
from fastapi import APIRouter, HTTPException
from typing import Optional

from backend.models.schemas import (
    QueryRequest,
    QueryResponse,
    Source,
    QueryMode,
)
from backend.vector_store.chroma_manager import ChromaManager

router = APIRouter(prefix="/api/query", tags=["query"])

chroma_manager = ChromaManager()


def get_embedding(text: str) -> list[float]:
    import ollama
    response = ollama.embeddings(model="nomic-embed-text", prompt=text)
    return response["embedding"]


def generate_answer(question: str, context_chunks: list[str]) -> str:
    import ollama

    context = "\n\n".join(context_chunks)
    prompt = f"""Based on the following context, answer the question.

Context:
{context}

Question: {question}

Answer:"""

    response = ollama.generate(
        model="deepseek-r1:1.5b",
        prompt=prompt
    )
    return response["response"]


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
        # For multiple document_ids, ChromaDB doesn't support IN clause directly
        # We'll query with first doc and filter after

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

            # Filter by document_ids if specified
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

    answer = generate_answer(request.question, context_chunks)

    return QueryResponse(
        question=request.question,
        answer=answer,
        sources=sources
    )


@router.get("/count")
async def get_chunk_count():
    return {"count": chroma_manager.count()}
