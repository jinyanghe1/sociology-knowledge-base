"""Embedding utility with Ollama + deterministic fallback.

When Ollama is available, uses bge-m3 for real embeddings.
When unavailable, falls back to deterministic hash-based embeddings
so the app can still start and accept documents.
"""

import hashlib
import logging
from typing import List, Optional

import numpy as np

logger = logging.getLogger(__name__)

# Embedding dimension (bge-m3: 1024维, 多语言/中文优化, 8192 token context)
EMBED_DIM = 1024
DEFAULT_EMBED_MODEL = "bge-m3"

_ollama_available: Optional[bool] = None


def _check_ollama() -> bool:
    """Check if ollama is importable and responsive."""
    global _ollama_available
    if _ollama_available is not None:
        return _ollama_available
    try:
        import ollama
        ollama.list()
        _ollama_available = True
        logger.info("Ollama is available — using real embeddings")
    except Exception:
        _ollama_available = False
        logger.warning("Ollama unavailable — using deterministic hash embeddings")
    return _ollama_available


def get_embedding(text: str, model: str = DEFAULT_EMBED_MODEL) -> List[float]:
    """Generate embedding for text.

    Uses Ollama when available, otherwise deterministic hash vector.
    """
    if _check_ollama():
        import ollama
        response = ollama.embeddings(model=model, prompt=text[:8000])
        return response["embedding"]
    return _hash_embedding(text)


def generate_answer(question: str, context_chunks: List[str],
                    model: str = "deepseek-r1:1.5b") -> str:
    """[Deprecated] Generate an LLM answer. Use Agent-side RAG instead.
    
    Kept for backward compatibility. The recommended workflow is:
    Agent → MCP rag_search → Top-K Chunks → Agent (RAG reasoning) → User
    """
    if _check_ollama():
        import ollama
        context = "\n\n".join(context_chunks)
        prompt = (
            f"Based on the following context, answer the question.\n\n"
            f"Context:\n{context}\n\nQuestion: {question}\n\nAnswer:"
        )
        response = ollama.generate(model=model, prompt=prompt)
        return response["response"]

    # Fallback: return context summary
    joined = "\n---\n".join(c[:500] for c in context_chunks[:3])
    return (
        f"[Ollama 未连接 — 回退模式]\n\n"
        f"问题: {question}\n\n"
        f"相关文档片段:\n{joined}\n\n"
        f"请安装并启动 Ollama 以获得 AI 生成的回答。"
    )


def generate_text(prompt: str, model: str = "deepseek-r1:1.5b") -> str:
    """[Deprecated] Generate text from prompt. Use Agent-side generation instead."""
    if _check_ollama():
        import ollama
        response = ollama.generate(model=model, prompt=prompt)
        return response["response"]
    return f"[Ollama 未连接] 无法生成回答。请先启动 Ollama 服务。"


def _hash_embedding(text: str) -> List[float]:
    """Deterministic hash-based embedding (fallback).

    Produces a normalized vector of EMBED_DIM floats seeded by text hash.
    Not semantically meaningful, but allows the pipeline to run end-to-end.
    """
    seed = int(hashlib.sha256(text.encode("utf-8")).hexdigest(), 16) % (2**32)
    rng = np.random.RandomState(seed)
    vec = rng.randn(EMBED_DIM).astype(np.float64)
    norm = np.linalg.norm(vec)
    if norm > 0:
        vec = vec / norm
    return vec.tolist()
