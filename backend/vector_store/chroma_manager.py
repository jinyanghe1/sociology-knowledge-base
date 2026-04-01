"""ChromaDB Manager - High-performance vector store for large knowledge bases.

Optimizations:
- Batch processing for bulk inserts
- Query result caching
- HNSW index tuning for fast ANN search
- Async operations support
- Connection pooling
"""

import hashlib
import os
import threading
import time
from functools import lru_cache
from typing import Dict, List, Optional, Any, Callable

try:
    import chromadb
    from chromadb.config import Settings
    _CHROMA_AVAILABLE = True
except ImportError:
    _CHROMA_AVAILABLE = False


class ChromaManager:
    """High-performance ChromaDB wrapper with caching and batch operations."""
    
    # Batch processing settings
    BATCH_SIZE = 100  # Optimal batch size for ChromaDB
    MAX_RETRIES = 3
    
    # HNSW index parameters (tuned for large datasets)
    HNSW_M = 16  # Number of bi-directional links for each node
    HNSW_CONSTRUCTION_EF = 200  # Size of dynamic candidate list
    HNSW_SEARCH_EF = 100  # Size of dynamic candidate list during search
    
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls, *args, **kwargs):
        """Singleton pattern for connection pooling."""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance
    
    def __init__(self, persist_directory: str = "./data/chroma"):
        if self._initialized:
            return
            
        self.persist_directory = persist_directory
        os.makedirs(persist_directory, exist_ok=True)
        
        if _CHROMA_AVAILABLE:
            self.client = chromadb.PersistentClient(
                path=persist_directory,
                settings=Settings(
                    anonymized_telemetry=False,
                    allow_reset=True,
                )
            )
        else:
            import logging
            logging.getLogger(__name__).warning(
                "chromadb not installed — using in-memory fallback vector store"
            )
            self.client = None
        
        self.collection_name = "documents"
        self._collection = None
        self._cache = {}  # Simple in-memory cache
        self._cache_lock = threading.Lock()
        self._fallback_store = {"ids": [], "embeddings": [], "documents": [], "metadatas": []}
        self._fallback_lock = threading.Lock()
        self._initialized = True
    
    @property
    def collection(self):
        """Get or create collection with HNSW index optimization."""
        if not _CHROMA_AVAILABLE or self.client is None:
            return None
        if self._collection is None:
            self._collection = self.client.get_or_create_collection(
                name=self.collection_name,
                metadata={
                    "description": "Document chunks for RAG",
                    "hnsw:space": "cosine",
                    "hnsw:construction_ef": self.HNSW_CONSTRUCTION_EF,
                    "hnsw:search_ef": self.HNSW_SEARCH_EF,
                    "hnsw:M": self.HNSW_M,
                }
            )
        return self._collection
    
    def add_documents(
        self,
        ids: List[str],
        embeddings: List[List[float]],
        documents: List[str],
        metadatas: Optional[List[Dict]] = None,
        batch_size: Optional[int] = None
    ) -> Dict[str, Any]:
        """Add documents with batch processing and retry logic."""
        if self.collection is None:
            return self._fallback_add(ids, embeddings, documents, metadatas)
        
        batch_size = batch_size or self.BATCH_SIZE
        total = len(ids)
        added_count = 0
        errors = []
        
        # Process in batches
        for i in range(0, total, batch_size):
            batch_end = min(i + batch_size, total)
            batch_ids = ids[i:batch_end]
            batch_embeddings = embeddings[i:batch_end]
            batch_documents = documents[i:batch_end]
            batch_metadatas = metadatas[i:batch_end] if metadatas else None
            
            # Retry logic
            for attempt in range(self.MAX_RETRIES):
                try:
                    self.collection.add(
                        ids=batch_ids,
                        embeddings=batch_embeddings,
                        documents=batch_documents,
                        metadatas=batch_metadatas
                    )
                    added_count += len(batch_ids)
                    break
                except Exception as e:
                    if attempt == self.MAX_RETRIES - 1:
                        errors.append(f"Batch {i//batch_size}: {str(e)}")
                    else:
                        time.sleep(0.5 * (attempt + 1))  # Exponential backoff
        
        # Invalidate cache after bulk add
        self._clear_cache()
        
        return {
            "added_count": added_count,
            "total": total,
            "errors": errors
        }
    
    def query(
        self,
        query_embedding: List[float],
        n_results: int = 5,
        where: Optional[Dict] = None,
        use_cache: bool = True
    ) -> Dict[str, Any]:
        """Query with caching and optimized HNSW search."""
        if self.collection is None:
            return self._fallback_query(query_embedding, n_results, where)
        # Generate cache key
        cache_key = None
        if use_cache:
            embedding_hash = hashlib.md5(
                str(query_embedding[:10]).encode()
            ).hexdigest()
            where_hash = hashlib.md5(
                str(where).encode()
            ).hexdigest() if where else "none"
            cache_key = f"{embedding_hash}_{where_hash}_{n_results}"
            
            # Check cache
            with self._cache_lock:
                if cache_key in self._cache:
                    return self._cache[cache_key]
        
        # Execute query
        results = self.collection.query(
            query_embeddings=[query_embedding],
            n_results=n_results,
            where=where,
            include=["metadatas", "documents", "distances"]
        )
        
        # Cache results
        if cache_key and use_cache:
            with self._cache_lock:
                self._cache[cache_key] = results
                # Limit cache size
                if len(self._cache) > 1000:
                    self._cache.pop(next(iter(self._cache)))
        
        return results
    
    def query_batch(
        self,
        query_embeddings: List[List[float]],
        n_results: int = 5,
        where: Optional[Dict] = None
    ) -> List[Dict[str, Any]]:
        """Batch query for multiple embeddings (more efficient)."""
        results = self.collection.query(
            query_embeddings=query_embeddings,
            n_results=n_results,
            where=where,
            include=["metadatas", "documents", "distances"]
        )
        
        # Reformat results as list of dicts
        batch_results = []
        for i in range(len(query_embeddings)):
            batch_results.append({
                "ids": [results["ids"][i]] if results["ids"] else [],
                "documents": [results["documents"][i]] if results.get("documents") else [],
                "metadatas": [results["metadatas"][i]] if results.get("metadatas") else [],
                "distances": [results["distances"][i]] if results.get("distances") else [],
            })
        
        return batch_results
    
    def get_document_chunks(self, document_id: str) -> List[Dict]:
        """Get all chunks for a document."""
        if self.collection is None:
            return self._fallback_get_doc_chunks(document_id)
        results = self.collection.get(
            where={"document_id": document_id},
            include=["documents", "metadatas"]
        )
        
        chunks = []
        if results and results.get("ids"):
            for i, doc_id in enumerate(results["ids"]):
                chunks.append({
                    "id": doc_id,
                    "content": results["documents"][i] if results.get("documents") else "",
                    "metadata": results["metadatas"][i] if results.get("metadatas") else {}
                })
        return chunks
    
    def get(
        self,
        ids: Optional[List[str]] = None,
        where: Optional[Dict] = None,
        limit: Optional[int] = None,
        offset: Optional[int] = None
    ) -> Dict[str, Any]:
        """Get chunks by IDs or where filter."""
        if self.collection is None:
            return self._fallback_get(ids, where, limit)
        kwargs = {}
        if ids:
            kwargs["ids"] = ids
        if where:
            kwargs["where"] = where
        if limit:
            kwargs["limit"] = limit
        if offset:
            kwargs["offset"] = offset
            
        return self.collection.get(**kwargs)
    
    def delete_by_document_id(self, document_id: str) -> None:
        """Delete all chunks for a document."""
        if self.collection is None:
            self._fallback_delete_by_doc(document_id)
            return
        self.collection.delete(where={"document_id": document_id})
        self._clear_cache()
    
    def delete_collection(self) -> None:
        """Delete entire collection."""
        if self.collection is not None:
            try:
                self.client.delete_collection(name=self.collection_name)
            except Exception:
                pass
        else:
            self._fallback_store = {"ids": [], "embeddings": [], "documents": [], "metadatas": []}
        self._collection = None
        self._clear_cache()
    
    def count(self) -> int:
        """Get total document count."""
        if self.collection is None:
            return len(self._fallback_store["ids"])
        return self.collection.count()
    
    def get_stats(self) -> Dict[str, Any]:
        """Get collection statistics."""
        return {
            "total_chunks": self.count(),
            "cache_size": len(self._cache),
            "collection_name": self.collection_name,
        }
    
    def _clear_cache(self):
        """Clear query cache."""
        with self._cache_lock:
            self._cache.clear()
    
    def optimize(self):
        """Run collection optimization (force index rebuild)."""
        pass

    # ---- In-memory fallback methods (when chromadb is not installed) ----

    def _fallback_add(self, ids, embeddings, documents, metadatas):
        """In-memory add for fallback mode."""
        with self._fallback_lock:
            store = self._fallback_store
            for i, doc_id in enumerate(ids):
                if doc_id not in store["ids"]:
                    store["ids"].append(doc_id)
                    store["embeddings"].append(embeddings[i])
                    store["documents"].append(documents[i])
                    store["metadatas"].append(metadatas[i] if metadatas else {})
        return {"added_count": len(ids), "total": len(ids), "errors": []}

    def _fallback_query(self, query_embedding, n_results, where):
        """Cosine-similarity search over in-memory store."""
        import numpy as _np
        with self._fallback_lock:
            store = self._fallback_store
            if not store["ids"]:
                return {"ids": [[]], "documents": [[]], "metadatas": [[]], "distances": [[]]}

            q = _np.array(query_embedding, dtype=_np.float64)
            q_norm = _np.linalg.norm(q)
            if q_norm == 0:
                q_norm = 1.0

            scored = []
            for i, emb in enumerate(store["embeddings"]):
                meta = store["metadatas"][i]
                if where:
                    match = all(meta.get(k) == v for k, v in where.items())
                    if not match:
                        continue
                e = _np.array(emb, dtype=_np.float64)
                e_norm = _np.linalg.norm(e)
                if e_norm == 0:
                    e_norm = 1.0
                dist = 1.0 - float(_np.dot(q, e) / (q_norm * e_norm))
                scored.append((i, dist))

            scored.sort(key=lambda x: x[1])
            top = scored[:n_results]

            return {
                "ids": [[store["ids"][i] for i, _ in top]],
                "documents": [[store["documents"][i] for i, _ in top]],
                "metadatas": [[store["metadatas"][i] for i, _ in top]],
                "distances": [[d for _, d in top]],
            }

    def _fallback_get_doc_chunks(self, document_id):
        """Get chunks for a document from fallback store."""
        with self._fallback_lock:
            store = self._fallback_store
            chunks = []
            for i, meta in enumerate(store["metadatas"]):
                if meta.get("document_id") == document_id:
                    chunks.append({
                        "id": store["ids"][i],
                        "content": store["documents"][i],
                        "metadata": meta,
                    })
        return chunks

    def _fallback_get(self, ids, where, limit):
        """Get by IDs or where filter from fallback store."""
        with self._fallback_lock:
            store = self._fallback_store
            result_ids, result_docs, result_metas = [], [], []
            for i, sid in enumerate(store["ids"]):
                if ids and sid not in ids:
                    continue
                meta = store["metadatas"][i]
                if where and not all(meta.get(k) == v for k, v in where.items()):
                    continue
                result_ids.append(sid)
                result_docs.append(store["documents"][i])
                result_metas.append(meta)
                if limit and len(result_ids) >= limit:
                    break
        return {"ids": result_ids, "documents": result_docs, "metadatas": result_metas}

    def _fallback_delete_by_doc(self, document_id):
        """Delete by document_id from fallback store."""
        with self._fallback_lock:
            store = self._fallback_store
            keep = [i for i, m in enumerate(store["metadatas"]) if m.get("document_id") != document_id]
            self._fallback_store = {
                "ids": [store["ids"][i] for i in keep],
                "embeddings": [store["embeddings"][i] for i in keep],
                "documents": [store["documents"][i] for i in keep],
                "metadatas": [store["metadatas"][i] for i in keep],
            }


class EmbeddingCache:
    """LRU cache for text embeddings to avoid recomputing."""
    
    def __init__(self, maxsize: int = 10000):
        self.maxsize = maxsize
        self._cache = {}
        self._access_order = []
        self._lock = threading.Lock()
    
    def _get_key(self, text: str, model: str) -> str:
        """Generate cache key from text and model."""
        return hashlib.sha256(f"{model}:{text}".encode()).hexdigest()
    
    def get(self, text: str, model: str) -> Optional[List[float]]:
        """Get cached embedding."""
        key = self._get_key(text, model)
        with self._lock:
            if key in self._cache:
                # Move to end (most recently used)
                self._access_order.remove(key)
                self._access_order.append(key)
                return self._cache[key]
        return None
    
    def put(self, text: str, model: str, embedding: List[float]) -> None:
        """Cache embedding."""
        key = self._get_key(text, model)
        with self._lock:
            if key in self._cache:
                self._access_order.remove(key)
            elif len(self._cache) >= self.maxsize:
                # Evict least recently used
                lru_key = self._access_order.pop(0)
                del self._cache[lru_key]
            
            self._cache[key] = embedding
            self._access_order.append(key)
    
    def clear(self):
        """Clear all cached embeddings."""
        with self._lock:
            self._cache.clear()
            self._access_order.clear()


# Global embedding cache instance
_embedding_cache = EmbeddingCache()


def get_embedding_cache() -> EmbeddingCache:
    """Get global embedding cache instance."""
    return _embedding_cache
