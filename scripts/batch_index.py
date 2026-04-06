#!/usr/bin/env python3
"""全量批量索引脚本 - 扫描 FILES/ 目录所有文件并入库

Usage:
    python3 scripts/batch_index.py              # 全量索引
    python3 scripts/batch_index.py --dry-run    # 仅扫描，不索引
    python3 scripts/batch_index.py --resume     # 断点续传（跳过已索引文件）
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path

# Ensure project root is importable
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from backend.core_logic.parser import DocumentParser
from backend.core_logic.embedding import get_embedding
from backend.vector_store.chroma_manager import ChromaManager

FILES_DIR = PROJECT_ROOT / "FILES"
PERSIST_DIR = PROJECT_ROOT / "data" / "chroma"
LOG_DIR = PROJECT_ROOT / "logs"
ERROR_LOG = LOG_DIR / "batch_index_errors.json"

SUPPORTED_EXTS = set(DocumentParser.SUPPORTED_EXTENSIONS.keys())


def scan_files(base_dir: Path) -> list:
    """Scan directory for all supported files."""
    files = []
    for root, _, filenames in os.walk(base_dir):
        for f in filenames:
            if f.startswith("."):
                continue
            ext = Path(f).suffix.lower()
            if ext in SUPPORTED_EXTS:
                files.append(Path(root) / f)
    return sorted(files)


def get_indexed_sources(chroma_mgr: ChromaManager) -> set:
    """Get set of already-indexed source paths (for resume mode)."""
    try:
        total = chroma_mgr.count()
        if total == 0:
            return set()
        result = chroma_mgr.collection.get(
            limit=min(total, 50000),
            include=["metadatas"]
        )
        sources = set()
        if result and result.get("metadatas"):
            for m in result["metadatas"]:
                src = m.get("source", "")
                if src:
                    sources.add(src)
        return sources
    except Exception:
        return set()


def index_file(file_path: Path, chroma_mgr: ChromaManager, parser: DocumentParser) -> dict:
    """Index a single file: parse → embed → store."""
    try:
        chunks = parser.parse(str(file_path))
        if not chunks:
            return {"status": "skipped", "reason": "no content", "file": str(file_path)}

        embeddings = []
        contents = []
        metadatas = []
        chunk_ids = []

        for chunk in chunks:
            content = chunk["content"]
            emb = get_embedding(content)
            embeddings.append(emb)
            contents.append(content)
            chunk_ids.append(chunk["id"])
            meta = chunk.get("metadata", {})
            meta["source"] = str(file_path)
            meta["document_id"] = str(file_path)
            meta["filename"] = file_path.name
            meta["file_type"] = file_path.suffix.lower()
            metadatas.append(meta)

        result = chroma_mgr.add_documents(
            ids=chunk_ids,
            embeddings=embeddings,
            documents=contents,
            metadatas=metadatas,
        )

        return {
            "status": "success",
            "file": str(file_path),
            "chunks": len(chunks),
            "added": result.get("added_count", len(chunks)),
        }
    except Exception as e:
        return {"status": "error", "file": str(file_path), "error": str(e)}


def main():
    ap = argparse.ArgumentParser(description="全量批量索引 FILES/ 目录")
    ap.add_argument("--dry-run", action="store_true", help="仅扫描，不索引")
    ap.add_argument("--resume", action="store_true", help="断点续传，跳过已索引文件")
    ap.add_argument("--dir", type=str, default=str(FILES_DIR), help="要扫描的目录")
    args = ap.parse_args()

    scan_dir = Path(args.dir)
    if not scan_dir.is_dir():
        print(f"❌ 目录不存在: {scan_dir}")
        sys.exit(1)

    LOG_DIR.mkdir(parents=True, exist_ok=True)

    files = scan_files(scan_dir)
    print(f"📂 扫描完成，共找到 {len(files)} 个支持的文件")

    # Show file type distribution
    ext_counts = {}
    for f in files:
        ext = f.suffix.lower()
        ext_counts[ext] = ext_counts.get(ext, 0) + 1
    for ext, count in sorted(ext_counts.items(), key=lambda x: -x[1]):
        print(f"   {ext}: {count}")

    if args.dry_run:
        print("\n🔍 Dry-run 模式，不执行索引。")
        return

    # Initialize components
    chroma_mgr = ChromaManager(persist_directory=str(PERSIST_DIR))
    parser_inst = DocumentParser()

    # Resume mode: skip already indexed files
    skip_set = set()
    if args.resume:
        skip_set = get_indexed_sources(chroma_mgr)
        print(f"♻️  Resume 模式：已索引 {len(skip_set)} 个文件，将跳过")

    success = 0
    errors = []
    skipped = []
    start_time = time.time()

    for i, f in enumerate(files, 1):
        if args.resume and str(f) in skip_set:
            skipped.append({"status": "skipped", "reason": "already indexed", "file": str(f)})
            continue

        result = index_file(f, chroma_mgr, parser_inst)
        status = result["status"]

        if status == "success":
            success += 1
            print(f"[{i}/{len(files)}] ✅ {f.name} → {result['chunks']} chunks")
        elif status == "skipped":
            skipped.append(result)
            print(f"[{i}/{len(files)}] ⏭  {f.name} → {result.get('reason', '无内容')}")
        else:
            errors.append(result)
            print(f"[{i}/{len(files)}] ❌ {f.name} → {result.get('error', 'unknown')[:80]}")

    elapsed = time.time() - start_time

    # Summary
    print(f"\n{'=' * 50}")
    print(f"索引完成 ({elapsed:.1f}s)")
    print(f"  成功: {success}")
    print(f"  跳过: {len(skipped)}")
    print(f"  失败: {len(errors)}")
    print(f"  当前总 chunks: {chroma_mgr.count()}")

    if errors:
        print(f"\n失败文件 ({len(errors)}):")
        for e in errors[:20]:
            print(f"  - {Path(e['file']).name}: {e.get('error', '')[:60]}")
        if len(errors) > 20:
            print(f"  ... 还有 {len(errors) - 20} 个失败文件")

        with open(ERROR_LOG, "w", encoding="utf-8") as fh:
            json.dump(errors, fh, ensure_ascii=False, indent=2)
        print(f"\n📄 失败详情已保存到: {ERROR_LOG}")


if __name__ == "__main__":
    main()
