"""MCP Server - AI Knowledge Base RAG Tools.

Provides document indexing, semantic search, and management via MCP protocol.
Uses JSON persistence for document metadata (survives restarts).
Reuses backend parser + vector store; adds index_folder for batch operations.
"""

import json
import os
import sys
import threading
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

# Ensure project root is importable
sys.path.insert(0, str(Path(__file__).parent.parent))

from mcp.server.fastmcp import FastMCP

from backend.vector_store.chroma_manager import ChromaManager
from backend.core_logic.parser import DocumentParser
from backend.core_logic.embedding import get_embedding

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
BASE_DIR = Path(__file__).parent.parent
DATA_DIR = BASE_DIR / "mcp_data"
UPLOADS_DIR = DATA_DIR / "uploads"
CHROMA_DIR = DATA_DIR / "chroma"
META_FILE = DATA_DIR / "documents.json"

for d in (DATA_DIR, UPLOADS_DIR, CHROMA_DIR):
    d.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# Persistent document metadata (JSON-backed)
# ---------------------------------------------------------------------------
_doc_meta: dict[str, dict] = {}
_meta_lock = threading.RLock()


def _load_meta() -> None:
    global _doc_meta
    with _meta_lock:
        if META_FILE.exists():
            try:
                _doc_meta = json.loads(META_FILE.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                _doc_meta = {}


def _save_meta() -> None:
    with _meta_lock:
        temp_file = META_FILE.with_suffix(".tmp")
        temp_file.write_text(
            json.dumps(_doc_meta, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )
        os.replace(temp_file, META_FILE)


_load_meta()

# ---------------------------------------------------------------------------
# Synchronization
# ---------------------------------------------------------------------------
_doc_lock = threading.RLock()

# ---------------------------------------------------------------------------
# Shared components
# ---------------------------------------------------------------------------
mcp = FastMCP("AI Knowledge Base")
chroma = ChromaManager(persist_directory=str(CHROMA_DIR))
parser = DocumentParser()


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------
def _index_single_file(path: Path, workspace: str = "default") -> dict[str, Any]:
    """Parse, embed, and index one file. Returns a result dict.

    Args:
        path: Path to the file
        workspace: Workspace/folder scope for the document (default: "default")
    """
    # Validate path to prevent directory traversal
    if ".." in str(path) or path.is_absolute():
        return {"error": "Invalid path: traversal not allowed"}

    if not path.exists():
        return {"error": f"File not found: {path}"}

    # Sanitize filename to prevent path traversal
    safe_name = path.name.replace("..", "").replace("/", "_").replace("\\", "_")
    if not safe_name:
        return {"error": "Invalid filename"}

    parser_type = DocumentParser.get_file_type(str(path))
    if parser_type is None:
        return {"error": f"Unsupported file type: {path.suffix}"}

    doc_id = str(uuid.uuid4())

    # Use lock to make the 5-step operation atomic
    with _doc_lock:
        dest = UPLOADS_DIR / f"{doc_id}_{safe_name}"
        try:
            dest.write_bytes(path.read_bytes())

            chunks = parser.parse(str(dest), parser_type)
            if not chunks:
                return {"error": f"No content extracted from {path.name}"}

            embeddings, contents, metadatas, chunk_ids = [], [], [], []
            for chunk in chunks:
                content = chunk["content"]
                embeddings.append(get_embedding(content))
                contents.append(content)
                metadatas.append({
                    "document_id": doc_id,
                    "chunk_index": chunk.get("chunk_index", 0),
                    "source": str(path),
                    "workspace": workspace,
                    "filename": path.name,
                })
                chunk_ids.append(chunk["id"])

            result = chroma.add_documents(
                ids=chunk_ids,
                embeddings=embeddings,
                documents=contents,
                metadatas=metadatas,
            )

            _doc_meta[doc_id] = {
                "id": doc_id,
                "filename": path.name,
                "file_type": parser_type,
                "file_path": str(dest),
                "source_path": str(path),
                "workspace": workspace,
                "chunk_count": len(chunks),
                "status": "ready",
                "indexed_at": datetime.now().isoformat(),
            }
            _save_meta()

            return {
                "success": True,
                "document_id": doc_id,
                "filename": path.name,
                "workspace": workspace,
                "chunk_count": len(chunks),
                "indexed": result.get("added_count", len(chunks)),
            }
        finally:
            # Cleanup on failure to avoid orphan files
            if dest.exists():
                try:
                    dest.unlink()
                except OSError:
                    pass


# ---------------------------------------------------------------------------
# MCP Tools
# ---------------------------------------------------------------------------

@mcp.tool()
def rag_search(query: str, top_k: int = 5, workspace: str = None) -> list[dict]:
    """Search the knowledge base using semantic similarity.

    Args:
        query: Natural-language search query.
        top_k: Max results to return (default 5).
        workspace: Filter by workspace scope (default: search all workspaces).
                  Use list_workspaces() to see available workspaces.

    Returns:
        Ranked list of matching chunks with content, score, and metadata.
    """
    try:
        qvec = get_embedding(query)
        
        # Build filter if workspace specified
        where_filter = None
        if workspace:
            where_filter = {"workspace": workspace}
        
        results = chroma.query(
            query_embedding=qvec, 
            n_results=top_k,
            where=where_filter
        )

        hits: list[dict] = []
        if results["ids"] and results["ids"][0]:
            for i, cid in enumerate(results["ids"][0]):
                meta = results["metadatas"][0][i] if results.get("metadatas") else {}
                hits.append({
                    "chunk_id": cid,
                    "content": results["documents"][0][i],
                    "document_id": meta.get("document_id", ""),
                    "chunk_index": meta.get("chunk_index", 0),
                    "source": meta.get("source", ""),
                    "workspace": meta.get("workspace", "default"),
                    "filename": meta.get("filename", ""),
                    "score": results["distances"][0][i] if results.get("distances") else 0.0,
                })
        return hits
    except Exception as e:
        return [{"error": f"Search failed: {e}"}]


@mcp.tool()
def index_document(file_path: str, workspace: str = "default") -> dict:
    """Parse and index a single document into the knowledge base.

    Supports: PDF, DOCX, DOC, PPTX, PPT, MD, TXT, HTML.

    Args:
        file_path: Absolute or relative path to the document.
        workspace: Workspace scope for the document (default: "default").
                  Use this to group related documents for scoped search.

    Returns:
        Result with document_id and chunk_count on success.
    """
    return _index_single_file(Path(file_path), workspace=workspace)


@mcp.tool()
def index_folder(folder_path: str, recursive: bool = True, workspace: str = None) -> dict:
    """Index all supported documents in a folder.

    Args:
        folder_path: Path to the folder.
        recursive: Whether to scan subdirectories (default True).
        workspace: Workspace scope (default: folder name).
                  All documents in this folder will be tagged with this workspace.

    Returns:
        Summary with per-file results and totals.
    """
    root = Path(folder_path)
    if not root.is_dir():
        return {"error": f"Not a directory: {folder_path}"}

    # Use folder name as default workspace
    if workspace is None:
        workspace = root.name or "default"

    pattern = "**/*" if recursive else "*"
    files = [
        f for f in root.glob(pattern)
        if f.is_file() and DocumentParser.is_supported(str(f))
    ]

    if not files:
        return {"error": "No supported documents found in directory"}

    results: list[dict] = []
    ok = 0
    total_chunks = 0
    for f in sorted(files):
        r = _index_single_file(f, workspace=workspace)
        results.append(r)
        if r.get("success"):
            ok += 1
            total_chunks += r.get("chunk_count", 0)

    return {
        "success": ok > 0,
        "workspace": workspace,
        "files_found": len(files),
        "files_indexed": ok,
        "total_chunks": total_chunks,
        "details": results,
    }


@mcp.tool()
def list_documents() -> list[dict]:
    """List all indexed documents in the knowledge base.

    Returns:
        List of documents with id, filename, status, and chunk_count.
    """
    with _meta_lock:
        return list(_doc_meta.values())


@mcp.tool()
def get_document_info(document_id: str) -> dict:
    """Get detailed metadata for a specific document.

    Args:
        document_id: The document UUID.

    Returns:
        Document metadata dict or error.
    """
    with _meta_lock:
        doc = _doc_meta.get(document_id)
        if doc is None:
            return {"error": "Document not found"}
        return doc


@mcp.tool()
def get_document_chunks(document_id: str) -> list[dict]:
    """Retrieve all indexed chunks for a document.

    Useful for inspecting what was actually stored after indexing.

    Args:
        document_id: The document UUID.

    Returns:
        List of chunks with content and metadata.
    """
    with _meta_lock:
        if document_id not in _doc_meta:
            return [{"error": "Document not found"}]
    try:
        chunks = chroma.get_document_chunks(document_id)
        return [
            {
                "chunk_id": c["id"],
                "content": c["content"],
                "metadata": c["metadata"],
            }
            for c in chunks
        ]
    except Exception as e:
        return [{"error": f"Failed to retrieve chunks: {e}"}]


@mcp.tool()
def delete_document(document_id: str) -> dict:
    """Delete a document and its chunks from the knowledge base.

    Args:
        document_id: The document UUID.

    Returns:
        Success status.
    """
    with _meta_lock:
        if document_id not in _doc_meta:
            return {"error": "Document not found"}

        try:
            doc = _doc_meta[document_id]
            fp = Path(doc.get("file_path", ""))
            if fp.exists():
                fp.unlink()

            chroma.delete_by_document_id(document_id)
            del _doc_meta[document_id]
            _save_meta()
            return {"success": True, "message": f"Document {document_id} deleted"}
        except Exception as e:
            return {"error": f"Deletion failed: {e}"}


@mcp.tool()
def list_workspaces() -> list[str]:
    """List all available workspaces.

    Returns:
        List of workspace names. Use these with rag_search(workspace=...)
        to scope searches to specific folders.
    """
    with _meta_lock:
        workspaces = set()
        for doc in _doc_meta.values():
            ws = doc.get("workspace", "default")
            workspaces.add(ws)
        return sorted(list(workspaces))


@mcp.tool()
def get_stats() -> dict:
    """Get knowledge base statistics.

    Returns:
        Counts of documents, chunks, and vector store stats.
    """
    with _meta_lock:
        # Count documents per workspace
        workspace_counts = {}
        for doc in _doc_meta.values():
            ws = doc.get("workspace", "default")
            workspace_counts[ws] = workspace_counts.get(ws, 0) + 1

        return {
            "documents_count": len(_doc_meta),
            "chunks_count": chroma.count(),
            "workspaces": workspace_counts,
            **chroma.get_stats(),
        }


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(description="AI Knowledge Base MCP Server")
    ap.add_argument(
        "--transport",
        choices=["stdio", "sse", "streamable-http"],
        default="stdio",
        help="MCP transport (default: stdio for Claude Desktop)",
    )
    args = ap.parse_args()
    mcp.run(transport=args.transport)
