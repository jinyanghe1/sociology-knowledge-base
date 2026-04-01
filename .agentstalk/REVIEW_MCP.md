# MCP Server 架构审查报告

**审查文件:** `/Users/hejinyang/Desktop/社会学考研资料/mcp_server/server.py`  
**审查日期:** 2026-04-01  
**代码行数:** 386 行  
**审查人:** MCP 架构专家

---

## 一、执行摘要

本次审查发现 **2 个 CRITICAL 级别问题**、**3 个 HIGH 级别问题**、**5 个 MEDIUM 级别问题**和若干改进建议。主要风险集中在**线程安全**、**事务性**和**错误处理**方面。

---

## 二、详细审查结果

### 2.1 状态管理

#### 🔴 [CRITICAL] 全局状态 _doc_meta 无并发控制

**位置:** 第 40 行

**问题描述:**
```python
_doc_meta: dict[str, dict] = {}
```

全局字典 `_doc_meta` 被多个 Tool 函数并发访问（读写），但没有任何锁机制保护。当 MCP Server 通过 SSE/HTTP 模式运行时，多个请求可能同时修改此字典，导致：

1. **数据竞争 (Race Condition):** 两个请求同时更新同一文档元数据
2. **字典损坏:** Python dict 在并发修改时可能导致内部结构损坏
3. **丢失更新:** `_save_meta()` 写入的可能是过期的内存状态

**受影响函数:**
- `_index_single_file()` - 第 115-126 行 (写)
- `delete_document()` - 第 329-330 行 (写)
- `list_documents()` - 第 262 行 (读)
- `get_document_info()` - 第 275 行 (读)
- `list_workspaces()` - 第 344-348 行 (读)
- `get_stats()` - 第 360-362 行 (读)

**改进建议:**
```python
import threading

# 在模块级别添加锁
_doc_meta_lock = threading.RLock()
_doc_meta: dict[str, dict] = {}

# 所有访问点使用锁保护
def _index_single_file(path: Path, workspace: str = "default") -> dict[str, Any]:
    # ... 前面的代码 ...
    
    with _doc_meta_lock:
        _doc_meta[doc_id] = {
            "id": doc_id,
            "filename": path.name,
            # ... 其他字段
        }
        _save_meta()
    
    return {...}

# 读操作同样需要锁以保证一致性
def list_documents() -> list[dict]:
    with _doc_meta_lock:
        return list(_doc_meta.values())
```

---

#### 🔴 [CRITICAL] JSON 持久化缺乏原子性和异常处理

**位置:** 第 52-56 行 `_save_meta()`

**问题描述:**
```python
def _save_meta() -> None:
    META_FILE.write_text(
        json.dumps(_doc_meta, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
```

**问题:**
1. **非原子写入:** 如果写入过程中进程崩溃，JSON 文件可能处于半写状态（损坏）
2. **无磁盘空间检查:** 磁盘满时抛出异常，但内存状态已更新，导致不一致
3. **无权限错误处理:** 权限不足时抛出 OSError，上层无法优雅处理
4. **无备份机制:** 一旦文件损坏，所有元数据丢失

**改进建议:**
```python
import tempfile
import shutil

def _save_meta() -> None:
    """原子性保存元数据，带错误处理和备份。"""
    try:
        # 1. 写入临时文件
        with tempfile.NamedTemporaryFile(
            mode='w', 
            encoding='utf-8', 
            dir=META_FILE.parent,
            delete=False,
            suffix='.tmp'
        ) as f:
            json.dump(_doc_meta, f, ensure_ascii=False, indent=2, default=str)
            temp_path = f.name
        
        # 2. 备份原文件（如果存在）
        if META_FILE.exists():
            backup_path = META_FILE.with_suffix('.json.bak')
            shutil.copy2(META_FILE, backup_path)
        
        # 3. 原子替换
        shutil.move(temp_path, META_FILE)
        
    except (OSError, IOError) as e:
        # 清理临时文件
        if 'temp_path' in locals() and Path(temp_path).exists():
            Path(temp_path).unlink(missing_ok=True)
        raise RuntimeError(f"Failed to save metadata: {e}") from e
```

---

#### 🟡 [MEDIUM] _load_meta() 静默吞掉异常

**位置:** 第 43-49 行

**问题描述:**
```python
def _load_meta() -> None:
    global _doc_meta
    if META_FILE.exists():
        try:
            _doc_meta = json.loads(META_FILE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            _doc_meta = {}
```

JSON 文件损坏时静默重置为空字典，导致**数据静默丢失**。应至少记录警告日志。

**改进建议:**
```python
import logging

logger = logging.getLogger(__name__)

def _load_meta() -> None:
    global _doc_meta
    if META_FILE.exists():
        try:
            _doc_meta = json.loads(META_FILE.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            logger.error(f"Metadata file corrupted: {e}. Attempting recovery from backup...")
            # 尝试从备份恢复
            backup_path = META_FILE.with_suffix('.json.bak')
            if backup_path.exists():
                try:
                    _doc_meta = json.loads(backup_path.read_text(encoding="utf-8"))
                    logger.info("Metadata recovered from backup")
                    return
                except Exception:
                    pass
            _doc_meta = {}
        except OSError as e:
            logger.error(f"Cannot read metadata file: {e}")
            raise
```

---

#### 🟡 [MEDIUM] JSON 持久化性能问题

**位置:** 第 52-56 行

**问题描述:**
每次元数据变更都全量写入 JSON 文件。当文档数量达到 10,000+ 时：
- 文件大小可能达到数 MB
- 每次索引一个文档都触发全量写入
- 性能瓶颈明显

**改进建议:**
```python
# 方案 1: 批量写入 + 防抖
import time
from threading import Timer

_pending_save = False
_save_timer: Optional[Timer] = None

def _save_meta(debounce: float = 1.0) -> None:
    """防抖写入，避免频繁磁盘操作。"""
    global _pending_save, _save_timer
    _pending_save = True
    
    if _save_timer:
        _save_timer.cancel()
    
    def do_save():
        global _pending_save
        # 执行原子写入（见上文）
        _atomic_save()
        _pending_save = False
    
    _save_timer = Timer(debounce, do_save)
    _save_timer.start()

# 方案 2: 使用 SQLite 替代 JSON（推荐）
# 对于大量文档，SQLite 提供更高效的增量更新
```

---

### 2.2 事务性

#### 🟠 [HIGH] 文档索引非原子操作

**位置:** `_index_single_file()` 第 72-135 行

**问题描述:**
文档索引涉及多个步骤，但任一步骤失败时不会回滚已完成的操作：

```python
def _index_single_file(...) -> dict[str, Any]:
    # Step 1: 复制文件 (第 87-88 行)
    dest.write_bytes(path.read_bytes())  # 文件已复制
    
    # Step 2: 解析 (第 90-92 行)
    chunks = parser.parse(...)  # 可能失败
    
    # Step 3: 生成嵌入 (第 94-106 行)
    for chunk in chunks:
        embeddings.append(get_embedding(content))  # 可能失败
    
    # Step 4: 写入 ChromaDB (第 108-113 行)
    result = chroma.add_documents(...)  # 可能失败
    
    # Step 5: 更新元数据 (第 115-126 行)
    _doc_meta[doc_id] = {...}  # 可能失败
    _save_meta()
```

**失败场景:**
- 嵌入生成失败：已复制的文件残留
- ChromaDB 写入失败：文件已复制，嵌入已生成但浪费，元数据未更新
- `_save_meta()` 失败：ChromaDB 有数据但元数据丢失，产生孤儿数据

**改进建议:**
```python
def _index_single_file(path: Path, workspace: str = "default") -> dict[str, Any]:
    doc_id = str(uuid.uuid4())
    dest = UPLOADS_DIR / f"{doc_id}_{path.name}"
    
    try:
        # Step 1: 验证
        if not path.exists():
            return {"error": f"File not found: {path}"}
        parser_type = DocumentParser.get_file_type(str(path))
        if parser_type is None:
            return {"error": f"Unsupported file type: {path.suffix}"}
        
        # Step 2: 解析（验证内容）
        chunks = parser.parse(str(path), parser_type)
        if not chunks:
            return {"error": f"No content extracted from {path.name}"}
        
        # Step 3: 复制文件（原子操作）
        dest.write_bytes(path.read_bytes())
        
        # Step 4: 生成嵌入
        try:
            embeddings, contents, metadatas, chunk_ids = [], [], [], []
            for chunk in chunks:
                content = chunk["content"]
                embeddings.append(get_embedding(content))
                contents.append(content)
                metadatas.append({...})
                chunk_ids.append(chunk["id"])
        except Exception as e:
            # 回滚：删除已复制文件
            dest.unlink(missing_ok=True)
            return {"error": f"Embedding generation failed: {e}"}
        
        # Step 5: 写入 ChromaDB
        try:
            result = chroma.add_documents(
                ids=chunk_ids,
                embeddings=embeddings,
                documents=contents,
                metadatas=metadatas,
            )
        except Exception as e:
            # 回滚：删除已复制文件
            dest.unlink(missing_ok=True)
            return {"error": f"Vector store insertion failed: {e}"}
        
        # Step 6: 更新元数据（带锁和事务）
        with _doc_meta_lock:
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
                "chunk_ids": chunk_ids,  # 保存 chunk IDs 用于回滚
            }
            try:
                _save_meta()
            except Exception as e:
                # 回滚：删除向量数据和文件
                chroma.delete_by_document_id(doc_id)
                dest.unlink(missing_ok=True)
                del _doc_meta[doc_id]
                return {"error": f"Metadata save failed: {e}"}
        
        return {"success": True, ...}
        
    except Exception as e:
        # 最终防线：清理所有残留
        dest.unlink(missing_ok=True)
        if doc_id in _doc_meta:
            with _doc_meta_lock:
                if doc_id in _doc_meta:
                    del _doc_meta[doc_id]
        return {"error": f"Unexpected error: {e}"}
```

---

#### 🟠 [HIGH] delete_document 非原子操作

**位置:** 第 309-333 行

**问题描述:**
```python
def delete_document(document_id: str) -> dict:
    if document_id not in _doc_meta:
        return {"error": "Document not found"}
    
    try:
        doc = _doc_meta[document_id]
        fp = Path(doc.get("file_path", ""))
        if fp.exists():
            fp.unlink()  # Step 1
        
        chroma.delete_by_document_id(document_id)  # Step 2
        del _doc_meta[document_id]  # Step 3
        _save_meta()  # Step 4
        
    except Exception as e:
        return {"error": f"Deletion failed: {e}"}
```

**问题:**
- Step 1 成功后 Step 2 失败：文件已删但向量数据残留
- Step 2 成功后 Step 3/4 失败：向量和文件已删但元数据残留

**改进建议:**
```python
def delete_document(document_id: str) -> dict:
    with _doc_meta_lock:
        if document_id not in _doc_meta:
            return {"error": "Document not found"}
        
        doc = _doc_meta[document_id]
        errors = []
        
        # 1. 先删除元数据（使文档"逻辑删除"）
        del _doc_meta[document_id]
        try:
            _save_meta()
        except Exception as e:
            # 回滚元数据
            _doc_meta[document_id] = doc
            return {"error": f"Failed to update metadata: {e}"}
        
        # 2. 物理删除（失败可后台重试）
        try:
            chroma.delete_by_document_id(document_id)
        except Exception as e:
            errors.append(f"Vector deletion failed: {e}")
        
        try:
            fp = Path(doc.get("file_path", ""))
            if fp.exists():
                fp.unlink()
        except Exception as e:
            errors.append(f"File deletion failed: {e}")
        
        if errors:
            return {
                "success": True,
                "warning": "Document marked as deleted but cleanup incomplete",
                "errors": errors
            }
        
        return {"success": True, "message": f"Document {document_id} deleted"}
```

---

### 2.3 错误处理

#### 🟠 [HIGH] Tool 返回类型不一致

**位置:** 多个 Tool 函数

**问题描述:**
```python
@mcp.tool()
def rag_search(...) -> list[dict]:  # 返回 list
    ...
    except Exception as e:
        return [{"error": f"Search failed: {e}"}]  # 错误也是 list

@mcp.tool()
def index_document(...) -> dict:  # 返回 dict
    ...
    return {"error": "..."}  # 错误也是 dict

@mcp.tool()
def list_documents() -> list[dict]:  # 返回 list
    return list(_doc_meta.values())  # 但错误时是...
    # 没有错误处理，可能抛出异常
```

**问题:**
- 成功时返回 list，错误时也返回 list（rag_search）
- 但 MCP 客户端难以区分成功/失败
- 某些 Tool 没有 try-except，异常会直接抛出导致连接断开

**改进建议:**
遵循 MCP 规范的错误处理：
```python
from mcp.types import ErrorData, INTERNAL_ERROR

@mcp.tool()
def rag_search(query: str, top_k: int = 5, workspace: str = None) -> list[dict]:
    """..."""
    try:
        # ... 业务逻辑 ...
        return hits
    except Exception as e:
        # 使用 MCP 标准错误格式
        logger.exception("RAG search failed")
        raise RuntimeError(f"Search failed: {e}")
```

或者统一返回格式：
```python
{
    "success": True/False,
    "data": <actual_result>,
    "error": <error_message_if_failed>
}
```

---

#### 🟡 [MEDIUM] _index_single_file 错误信息不够友好

**位置:** 第 79-84 行

**问题描述:**
```python
if not path.exists():
    return {"error": f"File not found: {path}"}

parser_type = DocumentParser.get_file_type(str(path))
if parser_type is None:
    return {"error": f"Unsupported file type: {path.suffix}"}
```

**改进建议:**
```python
if not path.exists():
    return {
        "error": "FILE_NOT_FOUND",
        "message": f"File not found: {path}",
        "suggestion": "Please check the file path and ensure the file exists."
    }

parser_type = DocumentParser.get_file_type(str(path))
if parser_type is None:
    supported = DocumentParser.supported_extensions()  # 需要添加此方法
    return {
        "error": "UNSUPPORTED_FILE_TYPE",
        "message": f"Unsupported file type: {path.suffix}",
        "suggestion": f"Supported formats: {', '.join(supported)}"
    }
```

---

### 2.4 MCP 协议合规性

#### 🟢 [LOW] Tools 参数类型定义完整

**位置:** 所有 Tool 装饰器

**评价:** 参数类型定义完整，符合 Python 类型注解规范。

#### 🟡 [MEDIUM] rag_search 返回的 score 语义不明确

**位置:** 第 181 行

**问题描述:**
```python
"score": results["distances"][0][i] if results.get("distances") else 0.0,
```

ChromaDB 的 `distances` 是**距离**（越小越相似），但用户可能误以为是**相似度分数**（越大越相似）。这会导致严重的使用误解。

**改进建议:**
```python
def _distance_to_similarity(distance: float) -> float:
    """将 ChromaDB 距离转换为归一化相似度分数 (0-1)。
    
    ChromaDB 默认使用 squared L2 距离，需要转换为相似度。
    """
    if distance is None:
        return 0.0
    # 使用指数衰减转换: similarity = exp(-distance)
    # 或者简单归一化（假设最大距离为 2.0）
    import math
    return round(math.exp(-float(distance)), 4)

# 在返回结果中明确标注
hits.append({
    "chunk_id": cid,
    "content": results["documents"][0][i],
    "document_id": meta.get("document_id", ""),
    "score": _distance_to_similarity(
        results["distances"][0][i] if results.get("distances") else None
    ),
    "score_type": "similarity",  # 明确标注是相似度
    # ... 其他字段
})
```

---

#### 🟡 [MEDIUM] index_folder 批量错误处理策略不明确

**位置:** 第 205-252 行

**问题描述:**
```python
for f in sorted(files):
    r = _index_single_file(f, workspace=workspace)
    results.append(r)
    if r.get("success"):
        ok += 1
        total_chunks += r.get("chunk_count", 0)
```

**问题:**
- 单个文件失败不会停止批量处理（正确）
- 但返回结果中难以快速识别哪些文件失败了
- 没有失败重试机制

**改进建议:**
```python
def index_folder(folder_path: str, recursive: bool = True, workspace: str = None,
                 stop_on_error: bool = False) -> dict:
    """..."""
    # ... 前面的代码 ...
    
    results: list[dict] = []
    failed_files: list[dict] = []
    ok = 0
    
    for f in sorted(files):
        r = _index_single_file(f, workspace=workspace)
        
        if r.get("success"):
            ok += 1
            total_chunks += r.get("chunk_count", 0)
            results.append({
                "file": f.name,
                "status": "success",
                "document_id": r.get("document_id"),
                "chunks": r.get("chunk_count")
            })
        else:
            failed_files.append({
                "file": f.name,
                "status": "failed",
                "error": r.get("error"),
                "suggestion": r.get("suggestion")
            })
            if stop_on_error:
                break
    
    return {
        "success": ok > 0,
        "workspace": workspace,
        "files_found": len(files),
        "files_indexed": ok,
        "files_failed": len(failed_files),
        "total_chunks": total_chunks,
        "successful": results,
        "failed": failed_files,
    }
```

---

### 2.5 资源隔离

#### 🟢 [LOW] Workspace 实现基本正确

**位置:** 第 205-252 行

**评价:** 
- `workspace` 参数设计合理
- 默认使用文件夹名称作为 workspace
- `rag_search` 支持 workspace 过滤

**建议:**
```python
# 增加 workspace 名称验证，避免特殊字符导致问题
import re

def _validate_workspace(name: str) -> str:
    """验证 workspace 名称合法性。"""
    if not name:
        return "default"
    # 只允许字母数字、下划线、连字符
    if not re.match(r'^[\w\-]+$', name):
        raise ValueError(f"Invalid workspace name: {name}. Use only letters, numbers, underscores, and hyphens.")
    return name.lower()  # 统一小写避免大小写问题
```

---

### 2.6 可扩展性

#### 🟡 [MEDIUM] 工具注册与实现耦合

**位置:** 全局

**问题描述:**
所有 Tool 都使用装饰器直接注册，随着工具数量增加：
- 文件会变得非常长
- 难以单元测试
- 工具之间可能有隐式依赖

**改进建议:**
采用分层架构：
```
mcp_server/
├── __init__.py
├── server.py          # MCP 服务器入口和注册
├── tools/
│   ├── __init__.py
│   ├── search.py      # rag_search
│   ├── index.py       # index_document, index_folder
│   ├── manage.py      # list_documents, delete_document, etc.
│   └── base.py        # 共享基类和工具
├── models/
│   ├── __init__.py
│   └── document.py    # 数据模型
└── utils/
    ├── __init__.py
    └── persistence.py # JSON/SQLite 持久化
```

---

#### 🟢 [INFO] 缺少健康检查工具

**建议添加:**
```python
@mcp.tool()
def health_check() -> dict:
    """Check system health and component status."""
    status = {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "components": {}
    }
    
    # 检查 ChromaDB
    try:
        chroma_count = chroma.count()
        status["components"]["vector_store"] = {
            "status": "ok",
            "document_count": chroma_count
        }
    except Exception as e:
        status["components"]["vector_store"] = {"status": "error", "message": str(e)}
        status["status"] = "degraded"
    
    # 检查 Ollama
    try:
        test_embedding = get_embedding("test")
        status["components"]["embedding_service"] = {
            "status": "ok",
            "embedding_dim": len(test_embedding)
        }
    except Exception as e:
        status["components"]["embedding_service"] = {"status": "error", "message": str(e)}
        status["status"] = "degraded"
    
    # 检查磁盘空间
    import shutil
    stat = shutil.disk_usage(DATA_DIR)
    free_gb = stat.free / (1024**3)
    status["storage"] = {
        "free_gb": round(free_gb, 2),
        "warning": free_gb < 1.0  # 少于 1GB 警告
    }
    
    return status
```

---

## 三、问题汇总

| 级别 | 数量 | 问题类别 |
|------|------|----------|
| 🔴 CRITICAL | 2 | 全局状态无并发控制、JSON 持久化无原子性 |
| 🟠 HIGH | 3 | 文档索引非原子、删除非原子、错误处理不一致 |
| 🟡 MEDIUM | 5 | 异常静默处理、JSON 性能、score 语义、批量错误、代码组织 |
| 🟢 LOW | 2 | workspace 验证、健康检查缺失 |

---

## 四、优先修复建议

### 立即修复（本周内）
1. **添加全局锁保护 `_doc_meta`**
2. **修复 `_save_meta()` 为原子写入**
3. **修正 `rag_search` 的 score 语义**

### 短期修复（2周内）
4. **实现索引操作的事务回滚**
5. **统一错误返回格式**
6. **添加 JSON 备份/恢复机制**

### 中期优化（1个月内）
7. **用 SQLite 替代 JSON 存储**
8. **代码模块化重构**
9. **添加健康检查工具**

---

## 五、代码审查附录

### A. 依赖项检查

代码依赖的外部组件：
- `mcp.server.fastmcp` - MCP SDK
- `backend.vector_store.chroma_manager` - 向量存储
- `backend.core_logic.parser` - 文档解析
- `backend.core_logic.embedding` - 嵌入服务

**风险:** 这些依赖项的异常处理未在审查范围内，如果它们抛出非预期异常，可能导致整个 MCP Server 崩溃。

### B. 配置管理

当前配置硬编码在模块级别：
```python
DATA_DIR = BASE_DIR / "mcp_data"
UPLOADS_DIR = DATA_DIR / "uploads"
```

**建议:** 支持环境变量覆盖：
```python
DATA_DIR = Path(os.environ.get("MCP_DATA_DIR", BASE_DIR / "mcp_data"))
```

### C. 日志记录

当前代码几乎没有日志记录，建议：
```python
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)
```

---

## 六、结论

该 MCP Server 实现功能完整，但在**生产环境部署**前必须解决 CRITICAL 和 HIGH 级别问题，特别是：

1. **线程安全** - 当前实现不适合多并发场景
2. **数据一致性** - 操作失败时可能产生孤儿数据
3. **错误传播** - 异常处理不够健壮

建议在修复上述问题后，添加单元测试和集成测试，确保系统稳定性。

---

*报告生成时间: 2026-04-01*  
*审查工具: Manual Code Review*
