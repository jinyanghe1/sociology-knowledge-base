"""Persistent JSON-backed catalog for indexed documents."""

from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

from mcp_server.models import IndexedDocument


class DocumentCatalog:
    """Persist indexed document metadata across MCP server restarts."""

    def __init__(self, catalog_path: str):
        self.catalog_path = Path(catalog_path)
        self.catalog_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        if not self.catalog_path.exists():
            self.catalog_path.write_text("[]\n", encoding="utf-8")

    def _load(self) -> List[IndexedDocument]:
        raw = json.loads(self.catalog_path.read_text(encoding="utf-8"))
        return [IndexedDocument.model_validate(item) for item in raw]

    def _save(self, records: List[IndexedDocument]) -> None:
        payload = [record.model_dump() for record in records]
        self.catalog_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    def list_documents(self) -> List[IndexedDocument]:
        with self._lock:
            records = self._load()
        return sorted(records, key=lambda item: item.indexed_at, reverse=True)

    def get(self, document_id: str) -> Optional[IndexedDocument]:
        with self._lock:
            for record in self._load():
                if record.id == document_id:
                    return record
        return None

    def get_by_path(self, path: str) -> Optional[IndexedDocument]:
        normalized = str(Path(path).expanduser().resolve())
        with self._lock:
            for record in self._load():
                if record.path == normalized:
                    return record
        return None

    def upsert(
        self,
        *,
        document_id: str,
        filename: str,
        path: str,
        file_type: str,
        chunk_count: int,
        status: str = "ready",
        size_bytes: int = 0,
    ) -> IndexedDocument:
        normalized = str(Path(path).expanduser().resolve())
        record = IndexedDocument(
            id=document_id,
            filename=filename,
            path=normalized,
            file_type=file_type,
            chunk_count=chunk_count,
            status=status,
            indexed_at=datetime.now(timezone.utc).isoformat(),
            size_bytes=size_bytes,
        )

        with self._lock:
            records = self._load()
            kept = [item for item in records if item.id != document_id and item.path != normalized]
            kept.append(record)
            self._save(kept)

        return record

    def delete(self, document_id: str) -> Optional[IndexedDocument]:
        with self._lock:
            records = self._load()
            deleted = None
            kept = []
            for record in records:
                if record.id == document_id:
                    deleted = record
                else:
                    kept.append(record)
            if deleted is not None:
                self._save(kept)
            return deleted
