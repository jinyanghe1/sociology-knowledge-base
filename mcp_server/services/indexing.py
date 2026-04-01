"""Document indexing service for the MCP server."""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import List, Optional

from backend.core_logic.embedding import get_embedding
from backend.core_logic.parser import DocumentParser
from backend.vector_store.chroma_manager import ChromaManager
from mcp_server.catalog import DocumentCatalog
from mcp_server.models import DeleteDocumentResult, IndexDocumentResult, IndexedDocument


class IndexingService:
    """Parse documents, generate embeddings, and update the catalog."""

    def __init__(
        self,
        *,
        parser: DocumentParser,
        chroma_manager: ChromaManager,
        catalog: DocumentCatalog,
    ):
        self.parser = parser
        self.chroma_manager = chroma_manager
        self.catalog = catalog

    def index_path(self, path: str) -> IndexDocumentResult:
        target = Path(path).expanduser().resolve()
        if not target.exists():
            raise FileNotFoundError(f"Path does not exist: {target}")

        if target.is_dir():
            return self._index_directory(target)

        document = self._index_file(target)
        return IndexDocumentResult(
            requested_path=str(target),
            indexed_count=1,
            documents=[document],
        )

    def delete_document(self, document_id: str) -> DeleteDocumentResult:
        record = self.catalog.get(document_id)
        if record is None:
            return DeleteDocumentResult(
                document_id=document_id,
                deleted=False,
                message="Document not found in MCP catalog.",
            )

        self.chroma_manager.delete_by_document_id(document_id)
        self.catalog.delete(document_id)
        return DeleteDocumentResult(
            document_id=document_id,
            deleted=True,
            filename=record.filename,
            path=record.path,
            deleted_chunks=record.chunk_count,
            message="Document deleted from catalog and vector store.",
        )

    def _index_directory(self, directory: Path) -> IndexDocumentResult:
        documents: List[IndexedDocument] = []
        errors: List[str] = []
        skipped_count = 0

        for file_path in sorted(path for path in directory.rglob("*") if path.is_file()):
            if not self.parser.is_supported(str(file_path)):
                skipped_count += 1
                continue

            try:
                documents.append(self._index_file(file_path))
            except Exception as exc:
                errors.append(f"{file_path}: {exc}")

        return IndexDocumentResult(
            requested_path=str(directory),
            indexed_count=len(documents),
            skipped_count=skipped_count,
            documents=documents,
            errors=errors,
        )

    def _index_file(self, file_path: Path) -> IndexedDocument:
        file_type = self.parser.get_file_type(str(file_path))
        if file_type is None:
            raise ValueError(f"Unsupported file type: {file_path.suffix}")

        existing = self.catalog.get_by_path(str(file_path))
        document_id = existing.id if existing else str(uuid.uuid4())

        if existing is not None:
            self.chroma_manager.delete_by_document_id(document_id)

        chunks = self.parser.parse(str(file_path), file_type)
        if not chunks:
            raise ValueError("No content extracted from document")

        embeddings = []
        documents = []
        metadatas = []
        chunk_ids = []

        for chunk in chunks:
            content = chunk["content"]
            embeddings.append(get_embedding(content))
            documents.append(content)
            chunk_ids.append(chunk["id"])
            metadatas.append(
                {
                    "document_id": document_id,
                    "filename": file_path.name,
                    "path": str(file_path),
                    "file_type": file_type,
                    "chunk_index": chunk.get("chunk_index", 0),
                    **chunk.get("metadata", {}),
                }
            )

        result = self.chroma_manager.add_documents(
            ids=chunk_ids,
            embeddings=embeddings,
            documents=documents,
            metadatas=metadatas,
        )
        if result["errors"]:
            raise RuntimeError("; ".join(result["errors"]))

        return self.catalog.upsert(
            document_id=document_id,
            filename=file_path.name,
            path=str(file_path),
            file_type=file_type,
            chunk_count=len(chunks),
            size_bytes=file_path.stat().st_size,
        )
