"""Documents API - File upload and management with multi-format support.

Supports: PDF, DOC, DOCX, PPT, PPTX, MD, TXT
"""

import os
import shutil
import uuid
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, UploadFile, File, HTTPException, BackgroundTasks
from pydantic import BaseModel

from backend.core_logic.parser import DocumentParser
from backend.core_logic.store import (
    document_store, 
    create_document, 
    delete_document as delete_from_store,
    update_document_status
)
from backend.models.schemas import DocumentStatus, FileType

router = APIRouter(prefix="/api/documents", tags=["documents"])

UPLOAD_DIR = Path("./uploads")
UPLOAD_DIR.mkdir(exist_ok=True)

# File extension to FileType mapping
FILE_TYPE_MAP = {
    '.pdf': FileType.PDF,
    '.doc': FileType.TEXT,  # Legacy DOC treated as text after conversion
    '.docx': FileType.TEXT,
    '.ppt': FileType.TEXT,
    '.pptx': FileType.TEXT,
    '.md': FileType.MARKDOWN,
    '.markdown': FileType.MARKDOWN,
    '.txt': FileType.TEXT,
    '.rst': FileType.TEXT,
}


def get_file_type(filename: str) -> FileType:
    """Get FileType from filename extension."""
    ext = Path(filename).suffix.lower()
    if ext in FILE_TYPE_MAP:
        return FILE_TYPE_MAP[ext]
    # Try to infer from content or default to TEXT
    return FileType.TEXT


def is_supported_file(filename: str) -> bool:
    """Check if file type is supported."""
    ext = Path(filename).suffix.lower()
    return ext in FILE_TYPE_MAP or ext in ['.html', '.htm']


class DocumentResponse(BaseModel):
    """Document response model."""
    id: str
    filename: str
    file_type: str
    upload_time: str
    status: str
    chunk_count: int


class BatchUploadResponse(BaseModel):
    """Batch upload response."""
    successful: List[DocumentResponse]
    failed: List[dict]


@router.post("", response_model=DocumentResponse)
async def upload_document(file: UploadFile = File(...)):
    """Upload and register a new document."""
    if not is_supported_file(file.filename):
        raise HTTPException(
            status_code=400, 
            detail=f"Unsupported file type: {file.filename}. Supported: {list(FILE_TYPE_MAP.keys())}"
        )
    
    file_type = get_file_type(file.filename)
    doc_id = str(uuid.uuid4())
    file_path = UPLOAD_DIR / f"{doc_id}_{file.filename}"

    try:
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save file: {e}")

    doc = create_document(
        doc_id=doc_id,
        filename=file.filename,
        file_type=file_type,
        file_path=str(file_path)
    )

    return DocumentResponse(
        id=doc["id"],
        filename=doc["filename"],
        file_type=doc["file_type"].value,
        upload_time=doc["upload_time"].isoformat(),
        status=doc["status"].value,
        chunk_count=doc["chunk_count"]
    )


@router.post("/batch", response_model=BatchUploadResponse)
async def upload_documents_batch(files: List[UploadFile] = File(...)):
    """Upload multiple documents in batch."""
    successful = []
    failed = []
    
    for file in files:
        try:
            if not is_supported_file(file.filename):
                failed.append({
                    "filename": file.filename,
                    "error": "Unsupported file type"
                })
                continue
            
            file_type = get_file_type(file.filename)
            doc_id = str(uuid.uuid4())
            file_path = UPLOAD_DIR / f"{doc_id}_{file.filename}"
            
            with open(file_path, "wb") as buffer:
                shutil.copyfileobj(file.file, buffer)
            
            doc = create_document(
                doc_id=doc_id,
                filename=file.filename,
                file_type=file_type,
                file_path=str(file_path)
            )
            
            successful.append(DocumentResponse(
                id=doc["id"],
                filename=doc["filename"],
                file_type=doc["file_type"].value,
                upload_time=doc["upload_time"].isoformat(),
                status=doc["status"].value,
                chunk_count=doc["chunk_count"]
            ))
            
        except Exception as e:
            failed.append({
                "filename": file.filename,
                "error": str(e)
            })
    
    return BatchUploadResponse(successful=successful, failed=failed)


@router.get("", response_model=List[DocumentResponse])
async def list_documents():
    """List all documents."""
    return [
        DocumentResponse(
            id=doc["id"],
            filename=doc["filename"],
            file_type=doc["file_type"].value if hasattr(doc["file_type"], 'value') else doc["file_type"],
            upload_time=doc["upload_time"].isoformat() if hasattr(doc["upload_time"], 'isoformat') else str(doc["upload_time"]),
            status=doc["status"].value if hasattr(doc["status"], 'value') else doc["status"],
            chunk_count=doc["chunk_count"]
        )
        for doc in document_store.values()
    ]


@router.get("/{document_id}", response_model=DocumentResponse)
async def get_document(document_id: str):
    """Get a specific document."""
    if document_id not in document_store:
        raise HTTPException(status_code=404, detail="Document not found")
    
    doc = document_store[document_id]
    return DocumentResponse(
        id=doc["id"],
        filename=doc["filename"],
        file_type=doc["file_type"].value if hasattr(doc["file_type"], 'value') else doc["file_type"],
        upload_time=doc["upload_time"].isoformat() if hasattr(doc["upload_time"], 'isoformat') else str(doc["upload_time"]),
        status=doc["status"].value if hasattr(doc["status"], 'value') else doc["status"],
        chunk_count=doc["chunk_count"]
    )


@router.delete("/{document_id}")
async def delete_document_endpoint(document_id: str):
    """Delete a document and its file."""
    if document_id not in document_store:
        raise HTTPException(status_code=404, detail="Document not found")

    doc = document_store[document_id]
    file_path = Path(doc["file_path"])
    if file_path.exists():
        file_path.unlink()

    delete_from_store(document_id)
    return {"message": "Document deleted successfully"}


@router.patch("/{document_id}/status")
async def update_document_status_endpoint(
    document_id: str,
    status: DocumentStatus,
    chunk_count: Optional[int] = None
):
    """Update document processing status."""
    result = update_document_status(document_id, status, chunk_count)
    if not result:
        raise HTTPException(status_code=404, detail="Document not found")

    return {
        "message": "Status updated", 
        "document": DocumentResponse(
            id=result["id"],
            filename=result["filename"],
            file_type=result["file_type"].value if hasattr(result["file_type"], 'value') else result["file_type"],
            upload_time=result["upload_time"].isoformat() if hasattr(result["upload_time"], 'isoformat') else str(result["upload_time"]),
            status=result["status"].value if hasattr(result["status"], 'value') else result["status"],
            chunk_count=result["chunk_count"]
        )
    }
