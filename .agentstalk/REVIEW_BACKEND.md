# 后端代码审查报告

**审查日期**: 2026-04-01  
**审查范围**: AI Knowledge Base 后端核心模块  
**审查维度**: 代码质量、性能、并发安全、API 设计、依赖管理、安全隐患

---

## 1. backend/main.py

### 严重级别汇总: **HIGH** 

#### 🔴 HIGH 级别问题

##### 1.1 全局状态共享与并发安全问题
```python
# 当前代码 (第 27-29 行)
chroma_manager = ChromaManager(persist_directory="./data/chroma")
parser = DocumentParser()
embedding_cache = get_embedding_cache()
```
**问题**: 模块级实例在多个 worker 进程间不共享状态，可能导致数据不一致。`document_store` 是内存字典，无线程锁保护。

**改进建议**:
```python
from threading import Lock
from functools import lru_cache

# 使用依赖注入替代全局实例
@lru_cache()
def get_chroma_manager() -> ChromaManager:
    return ChromaManager(persist_directory="./data/chroma")

# FastAPI 依赖注入
from fastapi import Depends

async def process_document(
    document_id: str,
    chroma: ChromaManager = Depends(get_chroma_manager)
):
    ...
```

##### 1.2 异常处理过于宽泛
```python
# 当前代码 (第 175-177 行)
except Exception as e:
    doc["status"] = DocumentStatus.ERROR
    raise HTTPException(status_code=500, detail=f"Processing failed: {str(e)}")
```
**问题**: 捕获所有异常可能隐藏关键错误，向客户端暴露内部错误信息，存在安全风险。

**改进建议**:
```python
from fastapi import HTTPException
import logging

logger = logging.getLogger(__name__)

try:
    # ... 处理逻辑
except HTTPException:
    raise  # 重新抛出已知的 HTTP 异常
except FileNotFoundError as e:
    logger.error(f"File not found: {e}")
    raise HTTPException(status_code=404, detail="Source file not found")
except ValueError as e:
    logger.warning(f"Validation error: {e}")
    raise HTTPException(status_code=400, detail=str(e))
except Exception as e:
    logger.exception(f"Unexpected error processing document {document_id}")
    raise HTTPException(status_code=500, detail="Internal server error")
```

##### 1.3 批处理缺少缓存机制
```python
# 当前代码 (第 201-204 行)
for chunk in chunks:
    embeddings.append(get_embedding(chunk["content"]))  # 无缓存
```
**问题**: `batch_process_documents` 未使用 embedding 缓存，而单个 `process_document` 使用了缓存。

**改进建议**:
```python
# 复用缓存逻辑
cached_embedding = embedding_cache.get(content, "nomic-embed-text")
if cached_embedding:
    embedding = cached_embedding
else:
    embedding = get_embedding(content)
    embedding_cache.put(content, "nomic-embed-text", embedding)
```

#### 🟡 MEDIUM 级别问题

##### 1.4 CORS 配置过于宽松
```python
# 当前代码 (第 53-59 行)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 允许所有来源
    allow_credentials=True,  # 与 allow_origins=["*"] 冲突
    allow_methods=["*"],
    allow_headers=["*"],
)
```
**问题**: `allow_origins=["*"]` 与 `allow_credentials=True` 组合存在安全风险。

**改进建议**:
```python
from fastapi.middleware.cors import CORSMiddleware
import os

ALLOWED_ORIGINS = os.getenv("ALLOWED_ORIGINS", "http://localhost:3000").split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
)
```

##### 1.5 调用私有方法
```python
# 当前代码 (第 232 行)
chroma_manager._clear_cache()  # 不应该直接调用私有方法
```

**改进建议**: 添加公共接口或使用正确的封装方式。

#### 🟢 LOW 级别问题

##### 1.6 硬编码配置
```python
persist_directory="./data/chroma"  # 应使用配置管理
```

---

## 2. backend/api/documents.py

### 严重级别汇总: **CRITICAL** ⚠️

#### 🔴 CRITICAL 级别问题

##### 2.1 路径遍历漏洞
```python
# 当前代码 (第 85, 127 行)
file_path = UPLOAD_DIR / f"{doc_id}_{file.filename}"
```
**问题**: 直接使用用户上传的 `file.filename` 拼接路径，存在路径遍历攻击风险（如 `../../../etc/passwd`）。

**改进建议**:
```python
import re
from pathlib import Path
from fastapi import HTTPException

def sanitize_filename(filename: str) -> str:
    """清理文件名，防止路径遍历。"""
    # 移除路径分隔符和危险字符
    filename = re.sub(r'[\\/:*?"<>|]', "_", filename)
    # 限制长度
    filename = filename[:255]
    # 确保不以点开头（隐藏文件）
    filename = filename.lstrip(".")
    if not filename:
        raise HTTPException(status_code=400, detail="Invalid filename")
    return filename

# 使用
safe_filename = sanitize_filename(file.filename)
file_path = UPLOAD_DIR / f"{doc_id}_{safe_filename}"
```

##### 2.2 缺少文件大小限制
```python
# 当前代码 (第 88-91 行)
with open(file_path, "wb") as buffer:
    shutil.copyfileobj(file.file, buffer)  # 无大小限制
```
**问题**: 可能导致磁盘空间耗尽攻击（DoS）。

**改进建议**:
```python
from fastapi import UploadFile, HTTPException
import shutil

MAX_FILE_SIZE = 100 * 1024 * 1024  # 100MB

def save_upload_file(upload_file: UploadFile, destination: Path, max_size: int = MAX_FILE_SIZE):
    """保存上传文件，带大小限制。"""
    total_size = 0
    with open(destination, "wb") as buffer:
        while chunk := upload_file.file.read(8192):
            total_size += len(chunk)
            if total_size > max_size:
                destination.unlink(missing_ok=True)
                raise HTTPException(status_code=413, detail=f"File too large (max {max_size} bytes)")
            buffer.write(chunk)
    return total_size
```

#### 🔴 HIGH 级别问题

##### 2.3 向量数据未同步删除
```python
# 当前代码 (第 190-202 行)
@router.delete("/{document_id}")
async def delete_document_endpoint(document_id: str):
    doc = document_store[document_id]
    file_path = Path(doc["file_path"])
    if file_path.exists():
        file_path.unlink()
    delete_from_store(document_id)  # 仅从内存删除
    return {"message": "Document deleted successfully"}
```
**问题**: 删除文档时未从向量数据库中删除对应的 chunks，导致数据孤儿和查询污染。

**改进建议**:
```python
from backend.vector_store.chroma_manager import ChromaManager

@router.delete("/{document_id}")
async def delete_document_endpoint(
    document_id: str,
    chroma: ChromaManager = Depends(get_chroma_manager)
):
    if document_id not in document_store:
        raise HTTPException(status_code=404, detail="Document not found")
    
    doc = document_store[document_id]
    
    try:
        # 1. 从向量数据库删除
        chroma.delete_by_document_id(document_id)
        
        # 2. 删除物理文件
        file_path = Path(doc["file_path"])
        if file_path.exists():
            file_path.unlink()
        
        # 3. 从内存存储删除
        delete_from_store(document_id)
        
        return {"message": "Document deleted successfully"}
    except Exception as e:
        logger.error(f"Failed to delete document {document_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to delete document")
```

#### 🟡 MEDIUM 级别问题

##### 2.4 模块导入时创建目录
```python
# 当前代码 (第 27 行)
UPLOAD_DIR = Path("./uploads")
UPLOAD_DIR.mkdir(exist_ok=True)  # 导入时执行 I/O
```
**问题**: 模块导入时执行 I/O 操作可能导致启动失败。

**改进建议**:
```python
UPLOAD_DIR = Path("./uploads")

# 在应用启动时创建
def ensure_upload_dir():
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

# 在 main.py 的 lifespan 中调用
```

#### 🟢 LOW 级别问题

##### 2.5 代码重复
多个地方重复创建 `DocumentResponse`，可提取为辅助函数。

---

## 3. backend/api/query.py

### 严重级别汇总: **HIGH** ⚠️

#### 🔴 HIGH 级别问题

##### 3.1 过滤器逻辑不完整
```python
# 当前代码 (第 28-31 行)
where_filter = None
if request.document_ids:
    if len(request.document_ids) == 1:
        where_filter = {"document_id": request.document_ids[0]}
```
**问题**: 当提供多个 `document_ids` 时，只处理单个 ID 的情况，其余情况被忽略。

**改进建议**:
```python
where_filter = None
if request.document_ids:
    if len(request.document_ids) == 1:
        where_filter = {"document_id": request.document_ids[0]}
    else:
        # ChromaDB OR 语法
        where_filter = {"$or": [{"document_id": doc_id} for doc_id in request.document_ids]}
```

##### 3.2 二次过滤效率问题
```python
# 当前代码 (第 46-49 行)
for i, chunk_id in enumerate(results["ids"][0]):
    doc_id = results["metadatas"][0][i].get("document_id", "")
    if request.document_ids and doc_id not in request.document_ids:
        continue  # 软件层过滤，浪费 DB 查询资源
```
**问题**: 如果数据库层已经过滤，这里不应再过滤；如果数据库层没过滤，应该使用数据库能力。

**改进建议**: 完全依赖数据库层的 where 过滤。

#### 🟡 MEDIUM 级别问题

##### 3.3 距离分数未转换
```python
# 当前代码 (第 52 行)
score = results["distances"][0][i] if results.get("distances") else 0.0
```
**问题**: ChromaDB 返回的是 L2 距离，应该转换为相似度分数（如 0-1 范围）以便用户理解。

**改进建议**:
```python
def l2_distance_to_similarity(distance: float) -> float:
    """将 L2 距离转换为相似度分数（0-1）。"""
    # 使用负指数转换
    return round(1 / (1 + distance), 4)

score = l2_distance_to_similarity(results["distances"][0][i])
```

##### 3.4 缺少超时控制
`generate_answer` 调用没有超时控制，可能导致请求挂起。

---

## 4. backend/api/agents.py

### 严重级别汇总: **MEDIUM** 

#### 🟡 MEDIUM 级别问题

##### 4.1 异常处理过于宽泛
```python
# 当前代码 (第 24-29 行)
try:
    agent = get_agentic_notes_agent(chroma_manager)
    result = agent.execute(request)
    return result
except Exception as e:
    raise HTTPException(status_code=500, detail=f"Agent task failed: {str(e)}")
```
**问题**: 未区分可恢复错误和不可恢复错误。

**改进建议**:
```python
from fastapi import HTTPException, status

class AgentTaskError(Exception):
    """Agent 任务错误基类"""
    pass

class DocumentNotFoundError(AgentTaskError):
    """文档未找到"""
    pass

try:
    result = agent.execute(request)
    return result
except DocumentNotFoundError as e:
    raise HTTPException(status_code=404, detail=str(e))
except AgentTaskError as e:
    raise HTTPException(status_code=400, detail=str(e))
except Exception as e:
    logger.exception("Agent task failed")
    raise HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="Internal server error"
    )
```

##### 4.2 缺少请求超时和限流
Agent 任务可能耗时较长，应该设置超时和限流机制。

**改进建议**:
```python
from fastapi import BackgroundTasks
from datetime import datetime, timedelta

@router.post("/task", response_model=AgentTaskResponse)
async def execute_agent_task(
    request: AgentTaskRequest,
    background_tasks: BackgroundTasks
):
    # 对于长时间任务，使用后台任务
    if request.async_execution:
        task_id = create_async_task(request)
        background_tasks.add_task(run_agent_task, task_id)
        return {"task_id": task_id, "status": "pending"}
    
    # 同步执行，带超时
    try:
        result = await asyncio.wait_for(
            run_agent_task(request),
            timeout=30  # 30秒超时
        )
        return result
    except asyncio.TimeoutError:
        raise HTTPException(status_code=504, detail="Task timeout")
```

---

## 5. backend/core_logic/agent.py

### 严重级别汇总: **MEDIUM** 

#### 🟡 MEDIUM 级别问题

##### 5.1 全局 ChromaManager 实例
```python
# 当前代码 (第 26 行)
chroma_manager = ChromaManager()
```
**问题**: 与 main.py 中的实例独立，配置可能不一致。

**改进建议**: 使用依赖注入或单例工厂模式。

##### 5.2 逻辑判断缺陷
```python
# 当前代码 (第 117-121 行)
def should_use_structured(state: AgentState) -> str:
    reasoning = "".join(state["reasoning_steps"])
    if "MULTI_STEP" in reasoning:
        return "structured"
    return "simple"
```
**问题**: 依赖字符串匹配，如果 `analysis` 包含 "MULTI_STEP" 但实际建议 "SIMPLE_RAG" 会误判。

**改进建议**:
```python
def should_use_structured(state: AgentState) -> str:
    # 从分析结果中解析决定，而不是简单的字符串匹配
    analysis = state.get("analysis_result", "")
    # 假设 LLM 返回格式: DECISION: SIMPLE_RAG 或 DECISION: MULTI_STEP
    if "MULTI_STEP" in analysis.split("DECISION:")[-1].split("\n")[0]:
        return "structured"
    return "simple"
```

##### 5.3 缺少异步支持
所有操作都是同步的，可能阻塞事件循环。

**改进建议**:
```python
import asyncio
from functools import partial

async def retrieve_context_async(state: AgentState) -> AgentState:
    loop = asyncio.get_event_loop()
    # 在线程池中执行同步调用
    return await loop.run_in_executor(None, retrieve_context, state)
```

---

## 6. backend/core_logic/agentic_notes.py

### 严重级别汇总: **HIGH** ⚠️

#### 🔴 HIGH 级别问题

##### 6.1 硬编码 Token 限制
```python
# 当前代码 (第 116, 141, 165 行)
{chunks_text[:8000]}  # 硬截断，可能破坏语义
{doc_text[:2000]}
```
**问题**: 硬截断文本可能导致语义不完整，且 8000 字符可能超出实际 token 限制。

**改进建议**:
```python
import tiktoken

def truncate_to_tokens(text: str, max_tokens: int = 4000, model: str = "gpt-3.5-turbo") -> str:
    """智能截断到指定 token 数。"""
    try:
        encoding = tiktoken.encoding_for_model(model)
        tokens = encoding.encode(text)
        if len(tokens) <= max_tokens:
            return text
        return encoding.decode(tokens[:max_tokens])
    except Exception:
        # 降级到字符截断
        return text[:max_tokens * 4]  # 近似估算

# 使用
truncated_text = truncate_to_tokens(chunks_text, max_tokens=4000)
```

##### 6.2 提示词注入风险
```python
# 当前代码 (第 163 行)
topic = state.get("metadata", {}).get("topic", "研究主题")
prompt = f"""基于以下文档内容，为"{topic}"生成一份结构化大纲..."""
```
**问题**: `topic` 直接插入提示词，可能被恶意利用进行提示词注入。

**改进建议**:
```python
import html

def sanitize_prompt_input(text: str, max_length: int = 200) -> str:
    """清理提示词输入。"""
    # 限制长度
    text = text[:max_length]
    # 转义特殊字符
    text = html.escape(text)
    # 移除可能的提示词注入标记
    text = text.replace("{", "{{").replace("}", "}}")
    return text

topic = sanitize_prompt_input(state.get("metadata", {}).get("topic", "研究主题"))
```

#### 🟡 MEDIUM 级别问题

##### 6.3 单例模式线程安全问题
```python
# 当前代码 (第 209-218 行)
_agentic_instance: Optional[AgenticNotesAgent] = None

def get_agentic_notes_agent(chroma_manager: Optional[ChromaManager] = None) -> AgenticNotesAgent:
    global _agentic_instance
    if _agentic_instance is None:
        _agentic_instance = AgenticNotesAgent(chroma_manager)
    return _agentic_instance
```
**问题**: 非线程安全的单例模式，可能创建多个实例。

**改进建议**:
```python
import threading

_agentic_instance: Optional[AgenticNotesAgent] = None
_instance_lock = threading.Lock()

def get_agentic_notes_agent(chroma_manager: Optional[ChromaManager] = None) -> AgenticNotesAgent:
    global _agentic_instance
    if _agentic_instance is None:
        with _instance_lock:
            # 双重检查
            if _agentic_instance is None:
                _agentic_instance = AgenticNotesAgent(chroma_manager)
    return _agentic_instance
```

---

## 7. backend/core_logic/store.py

### 严重级别汇总: **CRITICAL** ⚠️

#### 🔴 CRITICAL 级别问题

##### 7.1 内存存储无持久化
```python
# 当前代码 (第 11 行)
document_store: Dict[str, dict] = {}
```
**问题**: 应用重启后所有文档元数据丢失，仅保留向量数据库中的 chunks，导致数据不一致。

**改进建议**:
```python
import json
import atexit
from pathlib import Path

STORE_FILE = Path("./data/document_store.json")

class PersistentDocumentStore:
    """持久化文档存储"""
    
    def __init__(self, storage_path: Path = STORE_FILE):
        self._storage_path = storage_path
        self._store: Dict[str, dict] = {}
        self._lock = threading.RLock()
        self._load()
        atexit.register(self._save)
    
    def _load(self):
        if self._storage_path.exists():
            with open(self._storage_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                # 反序列化 datetime 和 enum
                self._store = self._deserialize(data)
    
    def _save(self):
        with self._lock:
            with open(self._storage_path, 'w', encoding='utf-8') as f:
                json.dump(self._serialize(self._store), f, ensure_ascii=False, indent=2)
    
    def create(self, doc_id: str, **kwargs) -> dict:
        with self._lock:
            self._store[doc_id] = {...}
            self._save()
            return self._store[doc_id]

# 全局实例
document_store = PersistentDocumentStore()
```

##### 7.2 无并发控制
```python
# 当前代码 - 所有操作都没有锁保护
def create_document(...) -> dict:
    document_store[doc_id] = {...}  # 非线程安全
```

**改进建议**: 使用 `threading.RLock` 保护所有操作。

---

## 总结

| 文件 | 严重级别 | 关键问题 |
|------|----------|----------|
| main.py | HIGH | 全局状态、异常处理 |
| documents.py | **CRITICAL** | 路径遍历、无文件大小限制、向量数据未同步删除 |
| query.py | HIGH | 过滤器逻辑不完整 |
| agents.py | MEDIUM | 异常处理宽泛 |
| agent.py | MEDIUM | 全局实例、异步支持 |
| agentic_notes.py | HIGH | 硬编码限制、提示词注入风险 |
| store.py | **CRITICAL** | 无持久化、无并发控制 |

## 优先修复建议

1. **立即修复** (CRITICAL):
   - documents.py: 修复路径遍历漏洞
   - documents.py: 添加文件大小限制
   - store.py: 实现持久化存储
   - documents.py: 删除时同步清理向量数据库

2. **高优先级** (HIGH):
   - query.py: 修复多 document_ids 过滤逻辑
   - agentic_notes.py: 实现智能 token 截断
   - main.py: 优化全局状态管理

3. **中优先级** (MEDIUM):
   - 所有文件: 完善异常处理
   - agent.py/agentic_notes.py: 添加异步支持
   - 整体: 使用依赖注入替代全局实例

---

*报告生成时间: 2026-04-01*  
*审查工具: Kimi Code CLI*
