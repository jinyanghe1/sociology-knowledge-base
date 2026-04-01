# backend/core_logic/store.py
"""Shared document store for backend.

All modules should import document_store from here to ensure consistency.
"""

import threading
from datetime import datetime
from typing import Dict, Optional
from backend.models.schemas import DocumentStatus, FileType

document_store: Dict[str, dict] = {}
_store_lock = threading.RLock()


def create_document(
    doc_id: str,
    filename: str,
    file_type: FileType,
    file_path: str,
) -> dict:
    """Create a new document entry in the store."""
    with _store_lock:
        document_store[doc_id] = {
            "id": doc_id,
            "filename": filename,
            "file_type": file_type,
            "file_path": file_path,
            "upload_time": datetime.now(),
            "status": DocumentStatus.PENDING,
            "chunk_count": 0,
        }
        return document_store[doc_id]


def get_document(doc_id: str) -> Optional[dict]:
    """Get document by ID."""
    with _store_lock:
        return document_store.get(doc_id)


def update_document_status(
    doc_id: str,
    status: DocumentStatus,
    chunk_count: Optional[int] = None
) -> Optional[dict]:
    """Update document status."""
    with _store_lock:
        if doc_id not in document_store:
            return None
        document_store[doc_id]["status"] = status
        if chunk_count is not None:
            document_store[doc_id]["chunk_count"] = chunk_count
        return document_store[doc_id]


def delete_document(doc_id: str) -> bool:
    """Delete document from store."""
    with _store_lock:
        if doc_id in document_store:
            del document_store[doc_id]
            return True
        return False
