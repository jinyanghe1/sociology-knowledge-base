"""FastAPI Backend - AI Knowledge Base API.

Optimized for large knowledge bases with:
- Batch document processing
- Caching
- Async operations
"""

import os
import uuid
from contextlib import asynccontextmanager
from typing import List

from fastapi import FastAPI, HTTPException, UploadFile, File, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from backend.api import documents, query
from backend.api.agents import router as agents_router
from backend.core_logic.embedding import get_embedding, DEFAULT_EMBED_MODEL
from backend.core_logic.parser import DocumentParser
from backend.core_logic.store import document_store, update_document_status
from backend.models.schemas import DocumentStatus, FileType
from backend.vector_store.chroma_manager import ChromaManager, get_embedding_cache

# Initialize components
chroma_manager = ChromaManager(persist_directory="./data/chroma")
parser = DocumentParser()
embedding_cache = get_embedding_cache()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler."""
    # Startup
    os.makedirs("./uploads", exist_ok=True)
    os.makedirs("./data/chroma", exist_ok=True)
    os.makedirs("./logs", exist_ok=True)
    print("🚀 AI Knowledge Base API starting...")
    yield
    # Shutdown
    print("🛑 AI Knowledge Base API shutting down...")


app = FastAPI(
    title="AI Knowledge Base API",
    description="本地运行的类 NotebookLM 精简知识库 API - 支持 PDF/DOC/DOCX/PPT/PPTX/MD/TXT",
    version="1.1.0",
    lifespan=lifespan,
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(documents.router)
app.include_router(query.router)
app.include_router(agents_router)


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "message": "AI Knowledge Base API",
        "status": "running",
        "version": "1.1.0",
        "features": ["RAG", "Agentic Notes", "Multi-format support"]
    }


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "documents": len(document_store),
        "chunks": chroma_manager.count(),
        "cache_size": len(embedding_cache._cache) if embedding_cache else 0
    }


@app.get("/stats")
async def get_stats():
    """Get system statistics."""
    return {
        **chroma_manager.get_stats(),
        "documents_in_store": len(document_store),
        "embedding_cache_size": len(embedding_cache._cache) if embedding_cache else 0,
    }


@app.post("/documents/{document_id}/process")
async def process_document(document_id: str):
    """Process a document: parse, embed, and index."""
    if document_id not in document_store:
        raise HTTPException(status_code=404, detail="Document not found")

    doc = document_store[document_id]
    doc["status"] = DocumentStatus.PROCESSING

    try:
        # Parse document
        file_path = doc["file_path"]
        file_type = doc["file_type"]
        
        # Convert FileType enum to string for parser
        if isinstance(file_type, FileType):
            parser_type = file_type.value
        else:
            parser_type = file_type
        
        chunks = parser.parse(file_path, parser_type)
        
        if not chunks:
            doc["status"] = DocumentStatus.ERROR
            raise HTTPException(status_code=400, detail="No content extracted from document")
        
        # Generate embeddings with caching
        embeddings = []
        contents = []
        metadatas = []
        
        for chunk in chunks:
            content = chunk["content"]
            cache_key = f"{hash(content)}"
            
            # Check cache
            cached_embedding = embedding_cache.get(content, DEFAULT_EMBED_MODEL)
            if cached_embedding:
                embedding = cached_embedding
            else:
                embedding = get_embedding(content)
                embedding_cache.put(content, DEFAULT_EMBED_MODEL, embedding)
            
            embeddings.append(embedding)
            contents.append(content)
            metadatas.append({
                "document_id": document_id,
                "chunk_index": chunk.get("chunk_index", 0),
                "source": chunk.get("metadata", {}).get("source", file_path),
                **{k: v for k, v in chunk.get("metadata", {}).items() if k != "source"}
            })
        
        # Batch add to vector store
        chunk_ids = [chunk["id"] for chunk in chunks]
        result = chroma_manager.add_documents(
            ids=chunk_ids,
            embeddings=embeddings,
            documents=contents,
            metadatas=metadatas
        )
        
        if result["errors"]:
            doc["status"] = DocumentStatus.ERROR
            raise HTTPException(status_code=500, detail=f"Indexing errors: {result['errors']}")
        
        # Update document status
        doc["status"] = DocumentStatus.READY
        doc["chunk_count"] = len(chunks)
        
        return {
            "message": "Document processed successfully",
            "document_id": document_id,
            "chunk_count": len(chunks),
            "indexed": result["added_count"]
        }

    except Exception as e:
        doc["status"] = DocumentStatus.ERROR
        raise HTTPException(status_code=500, detail=f"Processing failed: {str(e)}")


@app.post("/documents/batch/process")
async def batch_process_documents(document_ids: List[str]):
    """Process multiple documents in batch."""
    results = {"successful": [], "failed": []}
    
    for doc_id in document_ids:
        try:
            if doc_id not in document_store:
                results["failed"].append({"id": doc_id, "error": "Document not found"})
                continue
            
            doc = document_store[doc_id]
            doc["status"] = DocumentStatus.PROCESSING
            
            # Parse
            chunks = parser.parse(doc["file_path"], doc["file_type"].value)
            if not chunks:
                results["failed"].append({"id": doc_id, "error": "No content extracted"})
                doc["status"] = DocumentStatus.ERROR
                continue
            
            # Generate embeddings
            embeddings = []
            for chunk in chunks:
                embeddings.append(get_embedding(chunk["content"]))
            
            # Index
            chroma_manager.add_documents(
                ids=[c["id"] for c in chunks],
                embeddings=embeddings,
                documents=[c["content"] for c in chunks],
                metadatas=[{
                    "document_id": doc_id,
                    "chunk_index": c.get("chunk_index", 0)
                } for c in chunks]
            )
            
            doc["status"] = DocumentStatus.READY
            doc["chunk_count"] = len(chunks)
            results["successful"].append({"id": doc_id, "chunks": len(chunks)})
            
        except Exception as e:
            if doc_id in document_store:
                document_store[doc_id]["status"] = DocumentStatus.ERROR
            results["failed"].append({"id": doc_id, "error": str(e)})
    
    return results


@app.post("/cache/clear")
async def clear_cache():
    """Clear all caches."""
    chroma_manager._clear_cache()
    embedding_cache.clear()
    return {"message": "Caches cleared"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
