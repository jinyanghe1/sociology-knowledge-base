# 社会学知识库 RAG 优化工作流

> 目标一：优化检索返回结果质量
> 目标二：将 FILES/ 目录全部文件纳入索引
> 目标三：封装为 MCP Server，供 Agent 调用

---

## 现状速览

| 指标 | 数值 |
|------|------|
| 已索引文件 | 374 / 894 |
| 已入库 Chunks | 10,970 |
| Ollama 状态 | 未运行（当前用哈希回退） |
| Embedding 模型 | nomic-embed-text（768维，英文优化） |
| LLM 模型 | deepseek-r1:1.5b（太小） |
| 缺失解析 | .doc ×147、.ppt ×101、.pptx ×27、.pdf ×233 |

---

## 阶段一：环境准备（一次性）

### 1.1 安装缺失依赖

```bash
# 进入项目目录
cd /Users/hejinyang/Desktop/社会学考研资料

# 解析 .doc / .ppt 所需的系统依赖
brew install antiword    # .doc 文件解析
brew install tesseract   # OCR 引擎

# Python 依赖
pip install textract
```

### 1.2 升级 Ollama 模型

```bash
# 停止现有服务（如在运行）
# 然后下载新模型

# 中文优化的 Embedding 模型（替换 nomic-embed-text）
ollama pull mxbai-embed-large
# 规格：1024维，中文语义理解显著优于 nomic

# 更强的中文 Embedding（可选，效果更好但更慢）
# ollama pull shuangbai/bge-large-chinese-nmt

# 升级 LLM（替换 deepseek-r1:1.5b）
ollama pull deepseek-r1:7b
# 推理质量大幅提升，macOS M3 Pro+ 可流畅运行

# 启动 Ollama 服务
ollama serve
```

### 1.3 验证 Ollama 可用

```bash
# 检查模型列表
ollama list

# 测试 embedding 生成
curl http://localhost:11434/api/embeddings -d '{
  "model": "mxbai-embed-large",
  "prompt": "福柯的身体政治学"
}'

# 测试 LLM 推理
curl http://localhost:11434/api/generate -d '{
  "model": "deepseek-r1:7b",
  "prompt": "简述社会学的想象力"
}'
```

---

## 阶段二：代码改造

### 2.1 替换 Embedding 模型

**文件**：`backend/core_logic/embedding.py`

修改两处：

```python
# 修改1：默认模型改为 mxbai-embed-large
def get_embedding(text: str, model: str = "mxbai-embed-large") -> List[float]:
    if _check_ollama():
        import ollama
        response = ollama.embeddings(model=model, prompt=text[:8000])
        return response["embedding"]
    return _hash_embedding(text)

# 修改2：向量维度改为 1024
EMBED_DIM = 1024   # 原来是 768
```

⚠️ **注意**：维度变更后，需要**重建索引**（清空 ChromaDB 重新导入），因为 768 维和 1024 维的向量无法直接比较。

### 2.2 替换 LLM 模型

**文件**：`backend/core_logic/embedding.py`

```python
# generate_answer 中的默认模型
def generate_answer(question: str, context_chunks: List[str],
                    model: str = "deepseek-r1:7b") -> str:  # 原来是 1.5b
    ...

# generate_text 中的默认模型
def generate_text(prompt: str, model: str = "deepseek-r1:7b") -> str:
    ...
```

### 2.3 可选：优化 Chunk 大小

**文件**：`backend/core_logic/parser.py`

社会学文本论述较长，建议增大 chunk 以保留完整语义：

```python
class DocumentParser:
    CHUNK_SIZE = 3000     # 原来是 1500，约 1000 中文 tokens
    CHUNK_OVERLAP = 300   # 原来是 200
    MIN_CHUNK_SIZE = 200  # 原来是 100
```

> ⚠️ 如果修改 chunk size，同样需要重建索引。

### 2.4 可选：添加 Rerank 管道

当 top_k 较大时（如 10-20），在向量检索后加一层重排序能显著提升相关性：

```python
# backend/api/query.py 改造
@router.post("", response_model=QueryResponse)
async def query_documents(request: QueryRequest):
    # 第一步：向量检索，取更多结果（如 top 20）
    results = chroma_manager.query(
        query_embedding=query_embedding,
        n_results=20,  # 原来直接用 top_k
        where=where_filter
    )

    # 第二步：用 bge-reranker 重排序
    # （腾讯云 / 本地均可，依赖 rerank 模型）

    # 第三步：返回 top_k 个结果
```

---

## 阶段三：全量索引（重建）

### 3.1 清空旧索引

```bash
cd /Users/hejinyang/Desktop/社会学考研资料

# 方案A：保留数据库文件（推荐，测试新 pipeline）
mv data/chroma data/chroma_backup_$(date +%Y%m%d)

# 方案B：完全删除
# rm -rf data/chroma
```

### 3.2 编写批量索引脚本

新建文件：`scripts/batch_index.py`

```python
#!/usr/bin/env python3
"""全量批量索引脚本 - 扫描 FILES/ 目录所有文件并入库"""

import sys
import os
from pathlib import Path
from backend.core_logic.parser import DocumentParser
from backend.core_logic.embedding import get_embedding
from backend.vector_store.chroma_manager import ChromaManager
from backend.core_logic.store import create_document, update_document_status
from backend.models.schemas import DocumentStatus, FileType

KB_ROOT = Path("/Users/hejinyang/Desktop/社会学考研资料")
FILES_DIR = KB_ROOT / "FILES"
PERSIST_DIR = KB_ROOT / "data/chroma"

SUPPORTED_EXTS = {
    '.pdf', '.doc', '.docx',
    '.ppt', '.pptx',
    '.md', '.markdown', '.txt',
    '.html', '.htm'
}

def scan_files():
    """扫描 FILES/ 目录，返回所有待处理文件"""
    files = []
    for root, _, filenames in os.walk(FILES_DIR):
        for f in filenames:
            ext = Path(f).suffix.lower()
            if ext in SUPPORTED_EXTS:
                files.append(Path(root) / f)
    return files


def index_file(file_path: Path, chroma_mgr, parser) -> dict:
    """索引单个文件，返回结果"""
    rel_path = str(file_path.relative_to(KB_ROOT))
    try:
        chunks = parser.parse(str(file_path))

        if not chunks:
            return {"status": "skipped", "reason": "no content", "file": str(file_path)}

        # 批量生成 embedding
        texts = [c["content"] for c in chunks]
        embeddings = [get_embedding(t) for t in texts]

        # 写入 ChromaDB
        ids = [c["id"] for c in chunks]
        docs = [c["content"] for c in chunks]
        metas = []
        for c in chunks:
            m = c.get("metadata", {})
            m["source"] = str(file_path)
            m["document_id"] = str(file_path)
            metas.append(m)

        result = chroma_mgr.add_documents(ids, embeddings, docs, metas)

        return {
            "status": "success",
            "file": str(file_path),
            "chunks": len(chunks),
            "added": result["added_count"]
        }
    except Exception as e:
        return {"status": "error", "file": str(file_path), "error": str(e)}


def main():
    files = scan_files()
    print(f"扫描完成，共找到 {len(files)} 个文件")

    parser = DocumentParser()
    chroma_mgr = ChromaManager(persist_directory=str(PERSIST_DIR))

    success = 0
    errors = []
    skipped = []

    for i, f in enumerate(files, 1):
        result = index_file(f, chroma_mgr, parser)
        status = result["status"]

        if status == "success":
            success += 1
            print(f"[{i}/{len(files)}] ✅ {result['file']} → {result['chunks']} chunks")
        elif status == "skipped":
            skipped.append(result)
            print(f"[{i}/{len(files)}] ⏭ {result['file']} → 无内容")
        else:
            errors.append(result)
            print(f"[{i}/{len(files)}] ❌ {result['file']} → {result.get('error', 'unknown')}")

    # 汇总报告
    print(f"\n{'='*50}")
    print(f"索引完成")
    print(f"  成功: {success}")
    print(f"  跳过: {len(skipped)}")
    print(f"  失败: {len(errors)}")
    print(f"  当前总量: {chroma_mgr.count()} chunks")

    if errors:
        print(f"\n失败文件:")
        for e in errors:
            print(f"  - {e['file']}: {e['error']}")

    # 保存失败记录
    if errors:
        import json
        with open(KB_ROOT / "logs/batch_index_errors.json", "w", encoding="utf-8") as f:
            json.dump(errors, f, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()
```

### 3.3 运行索引

```bash
cd /Users/hejinyang/Desktop/社会学考研资料

# 后台运行（文件多时需要时间）
python3 scripts/batch_index.py

# 预计耗时（取决于 Ollama 速度和文件数量）：
#   - 543 PDF + 147 DOC + 58 DOCX + 101 PPT + 37 PPTX ≈ 886 文件
#   - Ollama mxbai-embed-large: 约 0.1-0.3s/次 embedding
#   - 估算总耗时：10-30 分钟
```

### 3.4 验证索引结果

```bash
# 检查总 chunk 数
curl http://localhost:8000/api/query/count

# 或用 Python 直接查
python3 -c "
from backend.vector_store.chroma_manager import ChromaManager
cm = ChromaManager(persist_directory='./data/chroma')
print(f'总 chunks: {cm.count()}')
"
```

预期：约 30,000-50,000 chunks（取决于 chunk size 设置）

---

## 阶段四：封装为 MCP Server

### 4.1 创建 MCP Server

新建文件：`mcp_server/sociology_kb/server.py`

```python
#!/usr/bin/env python3
"""
社会学知识库 MCP Server

功能：
  - query: 语义检索，返回相关文档片段
  - add_document: 上传并索引单个文件
  - get_document_chunks: 获取某文档的所有 chunks
  - list_indexed: 列出已索引的文件

Agent 调用示例：
  - "在社会学知识库里查一下布尔迪厄的文化资本理论"
  - "把附件里的 PDF 索引进去"
"""

import sys
import json
from pathlib import Path
from typing import Optional, List

# 添加项目路径
KB_ROOT = Path("/Users/hejinyang/Desktop/社会学考研资料")
sys.path.insert(0, str(KB_ROOT))

from backend.core_logic.embedding import get_embedding, generate_answer
from backend.vector_store.chroma_manager import ChromaManager
from backend.core_logic.parser import DocumentParser

chroma_mgr = ChromaManager(persist_directory=str(KB_ROOT / "data/chroma"))
parser = DocumentParser()


def handle_query(question: str, top_k: int = 5) -> dict:
    """语义检索"""
    embedding = get_embedding(question)
    results = chroma_manager.query(embedding, n_results=top_k)

    sources = []
    chunks = []
    if results.get("ids"):
        for i, chunk_id in enumerate(results["ids"][0]):
            content = results["documents"][0][i]
            score = results["distances"][0][i]
            source = results["metadatas"][0][i].get("source", "unknown")
            sources.append({
                "chunk_id": chunk_id,
                "source": source,
                "content": content,
                "score": round(score, 4)
            })
            chunks.append(content)

    answer = generate_answer(question, chunks)
    return {"answer": answer, "sources": sources}


def handle_add_document(file_path: str) -> dict:
    """索引单个文件"""
    path = Path(file_path)
    if not path.exists():
        return {"status": "error", "message": f"文件不存在: {file_path}"}

    try:
        chunks = parser.parse(str(path))
        if not chunks:
            return {"status": "skipped", "message": "无有效内容"}

        texts = [c["content"] for c in chunks]
        embeddings = [get_embedding(t) for t in texts]

        ids = [c["id"] for c in chunks]
        docs = [c["content"] for c in chunks]
        metas = []
        for c in chunks:
            m = c.get("metadata", {})
            m["source"] = str(path)
            m["document_id"] = str(path)
            metas.append(m)

        result = chroma_mgr.add_documents(ids, embeddings, docs, metas)
        return {
            "status": "success",
            "file": str(path),
            "chunks": len(chunks),
            "added": result["added_count"]
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}


def handle_list_indexed(limit: int = 100) -> dict:
    """列出已索引文件"""
    result = chroma_mgr.get(limit=limit, include=["metadatas"])
    files = set()
    if result.get("metadatas"):
        for m in result["metadatas"]:
            files.add(m.get("source", "unknown"))
    return {"files": sorted(files), "total_chunks": chroma_mgr.count()}


# MCP 协议入口（基于 stdio 通信）
if __name__ == "__main__":
    import sys
    import os

    # 设置输出为 UTF-8
    sys.stdout.reconfigure(encoding='utf-8')

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            request = json.loads(line)
            tool = request.get("tool")
            params = request.get("params", {})

            if tool == "query":
                result = handle_query(**params)
            elif tool == "add_document":
                result = handle_add_document(**params)
            elif tool == "list_indexed":
                result = handle_list_indexed(**params)
            else:
                result = {"error": f"Unknown tool: {tool}"}

            print(json.dumps({"result": result}, ensure_ascii=False))

        except Exception as e:
            print(json.dumps({"error": str(e)}, ensure_ascii=False))
```

### 4.2 配置 MCP 入口

新建文件：`mcp_server/sociology_kb/__main__.py`

```python
"""MCP Server 入口点"""
from .server import handle_query, handle_add_document, handle_list_indexed

__all__ = ["handle_query", "handle_add_document", "handle_list_indexed"]
```

### 4.3 写入 WorkBuddy MCP 配置

在 `~/.workbuddy/mcp.json` 中追加：

```json
{
  "mcpServers": {
    "sociology-kb": {
      "command": "python3",
      "args": [
        "/Users/hejinyang/Desktop/社会学考研资料/mcp_server/sociology_kb/server.py"
      ],
      "env": {}
    }
  }
}
```

### 4.4 MCP 工具定义

新建文件：`mcp_server/sociology_kb/tools.json`

```json
{
  "tools": [
    {
      "name": "kb_query",
      "description": "在社会学知识库中语义检索相关文档片段",
      "inputSchema": {
        "type": "object",
        "properties": {
          "question": {
            "type": "string",
            "description": "检索问题，例如：布尔迪厄的文化资本"
          },
          "top_k": {
            "type": "integer",
            "description": "返回结果数量，默认5",
            "default": 5
          }
        },
        "required": ["question"]
      }
    },
    {
      "name": "kb_add_document",
      "description": "将单个文件索引到知识库",
      "inputSchema": {
        "type": "object",
        "properties": {
          "file_path": {
            "type": "string",
            "description": "文件绝对路径"
          }
        },
        "required": ["file_path"]
      }
    },
    {
      "name": "kb_list_indexed",
      "description": "列出已索引的文件",
      "inputSchema": {
        "type": "object",
        "properties": {
          "limit": {
            "type": "integer",
            "description": "返回数量上限",
            "default": 100
          }
        }
      }
    }
  ]
}
```

---

## 阶段五：验证与调优

### 5.1 检索质量测试

```bash
# 测试几个典型社会学概念检索
cd /Users/hejinyang/Desktop/社会学考研资料
python3 scripts/kb_query.py "布尔迪厄的文化资本理论"
python3 scripts/kb_query.py "韦伯的科层制"
python3 scripts/kb_query.py "社会学的想象力"
```

预期改进：
- 相关文档的 cosine 距离应明显降低（从 0.8+ → 0.3-0.5）
- 返回片段应包含完整论述而非碎片

### 5.2 Agent 调用验证

在 WorkBuddy 中测试：

```
帮我查一下社会学知识库里关于"功能主义"的内容
```

Agent 应能：
1. 调用 MCP kb_query 工具
2. 获取检索结果
3. 综合回答问题

### 5.3 调优指标

| 指标 | 当前 | 目标 | 检测方法 |
|------|------|------|---------|
| 索引覆盖率 | 42% | 100% | `python3 -c "..."` 对比文件数 |
| 检索相关性 | 低（Ollama 未运行） | cosine < 0.5 | 测试 query 返回 score |
| LLM 回答质量 | 差（1.5b太小） | 流畅准确 | 主观评测 |
| MCP 响应延迟 | — | < 2s | Agent 调用计时 |

---

## 执行顺序

```
① 环境准备（1次）
   └─ 安装 textract/antiword/tesseract
   └─ ollama pull mxbai-embed-large + deepseek-r1:7b
   └─ ollama serve

② 代码改造（5分钟）
   └─ embedding.py：换模型 + 改维度
   └─ embedding.py：换 LLM 模型
   └─ （可选）parser.py：调 chunk size

③ 重建索引（约 15-30 分钟）
   └─ 备份/清空旧 chroma
   └─ python3 scripts/batch_index.py
   └─ 验证 chunk 总数

④ MCP 封装（约 10 分钟）
   └─ 写 server.py
   └─ 写 tools.json
   └─ 配置 mcp.json
   └─ 重启 WorkBuddy

⑤ 验证调优
   └─ 测试 query 质量
   └─ Agent 调用验证
```

---

## 注意事项

- **向量维度变更**：embedding 维度从 768 改到 1024 后，必须清空 `data/chroma` 重新索引，混合维度的向量数据库无法正常工作
- **Ollama 内存占用**：mxbai-embed-large + deepseek-r1:7b 并发运行约需 8-12GB 内存，确保机器有足够余量
- **textract 依赖**：.doc / .ppt 文件依赖系统级库，首次安装可能遇到编译问题，提前处理
- **备份策略**：索引重建前务必备份 `data/chroma`，以便回退
