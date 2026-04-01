"""Structured output models for MCP tools."""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class IndexedDocument(BaseModel):
    """Indexed document metadata persisted by the MCP server."""

    id: str
    filename: str
    path: str
    file_type: str
    chunk_count: int
    status: str
    indexed_at: str
    size_bytes: int = 0


class IndexDocumentResult(BaseModel):
    """Result for indexing a file or directory."""

    requested_path: str
    indexed_count: int
    skipped_count: int = 0
    documents: List[IndexedDocument] = Field(default_factory=list)
    errors: List[str] = Field(default_factory=list)


class DocumentListResult(BaseModel):
    """Result for listing indexed documents."""

    total: int
    documents: List[IndexedDocument] = Field(default_factory=list)


class DeleteDocumentResult(BaseModel):
    """Result for deleting an indexed document."""

    document_id: str
    deleted: bool
    filename: Optional[str] = None
    path: Optional[str] = None
    deleted_chunks: int = 0
    message: str


class DocumentInfoResult(BaseModel):
    """Detailed metadata for a single document."""

    document: Optional[IndexedDocument] = None
    found: bool
    message: str


class SearchHit(BaseModel):
    """Single source chunk returned by vector search."""

    chunk_id: str
    document_id: str
    filename: str
    path: str
    content: str
    score: float
    metadata: Dict[str, Any] = Field(default_factory=dict)


class SearchResult(BaseModel):
    """Structured search result for MCP clients."""

    query: str
    total_hits: int
    hits: List[SearchHit] = Field(default_factory=list)
    note: Optional[str] = None


class StatsResult(BaseModel):
    """High-level knowledge base statistics."""

    documents_count: int
    chunks_count: int
    collection_name: str
    cache_size: int
