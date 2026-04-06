"""Pydantic models for AI Knowledge Base.

Data models aligned with SCHEMA.json specification.
"""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
from uuid import uuid4

from pydantic import BaseModel, Field, field_serializer


class DocumentStatus(str, Enum):
    """Document processing status."""

    PENDING = "pending"
    PROCESSING = "processing"
    READY = "ready"
    ERROR = "error"


class FileType(str, Enum):
    """Supported file types."""

    PDF = "pdf"
    DOC = "doc"
    DOCX = "docx"
    PPT = "ppt"
    PPTX = "pptx"
    MARKDOWN = "markdown"
    TEXT = "text"
    HTML = "html"


class Document(BaseModel):
    """Document model representing uploaded files.

    Matches SCHEMA.json document specification.
    """

    id: str = Field(default_factory=lambda: str(uuid4()))
    filename: str
    file_type: FileType
    upload_time: datetime = Field(default_factory=datetime.utcnow)
    status: DocumentStatus = DocumentStatus.PENDING
    chunk_count: int = 0
    metadata: Dict[str, Any] = Field(default_factory=dict)

    @field_serializer("upload_time")
    def serialize_datetime(self, value: datetime) -> str:
        return value.isoformat()


class Chunk(BaseModel):
    """Text chunk model with embedding.

    Matches SCHEMA.json chunk specification.
    """

    id: str = Field(default_factory=lambda: str(uuid4()))
    document_id: str
    content: str
    chunk_index: int
    embedding: Optional[List[float]] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class QueryMode(str, Enum):
    """Query operation mode."""

    RAG = "rag"
    AGENTIC = "agentic"


class QueryRequest(BaseModel):
    """Query request model.

    Matches SCHEMA.json query specification.
    """

    question: str
    mode: QueryMode = QueryMode.RAG
    top_k: int = 5
    document_ids: Optional[List[str]] = None


class Source(BaseModel):
    """Source chunk with relevance score."""

    chunk_id: str
    document_id: str
    content: str
    score: float


class QueryResponse(BaseModel):
    """Query response model."""

    id: str = Field(default_factory=lambda: str(uuid4()))
    question: str
    answer: str
    sources: List[Source] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.utcnow)

    @field_serializer("created_at")
    def serialize_datetime(self, value: datetime) -> str:
        return value.isoformat()


class AgentRole(str, Enum):
    """Agent message roles."""

    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"


class AgentMessage(BaseModel):
    """Agent communication message.

    Matches SCHEMA.json agent_message specification.
    """

    id: str = Field(default_factory=lambda: str(uuid4()))
    agent: str = "default"
    role: AgentRole
    content: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    parent_id: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)

    @field_serializer("timestamp")
    def serialize_datetime(self, value: datetime) -> str:
        return value.isoformat()


class DocumentUploadResponse(BaseModel):
    """Response for document upload."""

    document: Document
    message: str = "Document uploaded successfully"


class AgentTaskType(str, Enum):
    """Available agent task types."""

    SUMMARIZE = "summarize"
    COMPARE = "compare"
    OUTLINE = "outline"


class AgentTaskRequest(BaseModel):
    """Request for agent task execution."""

    task_type: AgentTaskType
    document_ids: List[str]
    parameters: Dict[str, Any] = Field(default_factory=dict)


class AgentTaskResponse(BaseModel):
    """Response from agent task execution."""

    task_id: str = Field(default_factory=lambda: str(uuid4()))
    result: str
    sources: List[Source] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)
