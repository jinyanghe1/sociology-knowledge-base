# 前端代码审查报告

**审查日期**: 2026-04-01  
**审查范围**: `/Users/hejinyang/Desktop/社会学考研资料/frontend/`  
**审查文件**:
- `app.py` (409行) - Streamlit 主应用
- `pages/documents.py` (89行) - 文档管理页面
- `pages/chat.py` (99行) - 聊天页面

**项目背景**: 前端基于 Streamlit 构建，项目计划迁移到 MCP Server 架构，当前代码为历史维护状态。

---

## 执行摘要

| 维度 | 严重问题 | 高危问题 | 中危问题 | 低危问题 | 信息 |
|------|---------|---------|---------|---------|------|
| UI/UX | 0 | 1 | 3 | 2 | 2 |
| 状态管理 | 1 | 2 | 3 | 1 | 1 |
| API 调用 | 0 | 3 | 4 | 2 | 1 |
| 性能 | 0 | 1 | 3 | 2 | 2 |
| 代码组织 | 0 | 1 | 4 | 3 | 2 |
| 可访问性 | 0 | 0 | 3 | 4 | 3 |
| **总计** | **1** | **8** | **20** | **14** | **11** |

**关键风险**: 
1. **session_state 键名冲突** - 多页面架构下多个文件初始化相同键，可能导致数据丢失
2. **无文件大小限制** - 大文件上传可能导致内存溢出和服务崩溃
3. **API 调用缺乏统一错误处理** - 部分错误被静默处理，用户体验差

---

## 1. UI/UX 问题

### 1.1 🔴 HIGH - 批量上传错误信息截断，用户无法获知完整失败列表

**位置**: `app.py:210`

```python
if results["failed"]:
    st.error(f"❌ 失败 {len(results['failed'])} 个文件: {', '.join(results['failed'][:3])}")
```

**问题**: 失败文件列表只显示前3个，当批量上传大量文件失败时，用户无法知道全部失败的文件。

**建议**: 
```python
if results["failed"]:
    failed_count = len(results["failed"])
    failed_preview = ', '.join(results["failed"][:3])
    if failed_count > 3:
        failed_preview += f" 等共 {failed_count} 个文件"
    st.error(f"❌ 失败 {failed_count} 个文件: {failed_preview}")
    with st.expander("查看完整失败列表"):
        for f in results["failed"]:
            st.text(f"• {f}")
```

---

### 1.2 🟡 MEDIUM - 文档预览硬编码限制10个，无分页或搜索

**位置**: `app.py:235`

```python
for doc in documents[:10]:  # Limit preview to 10 docs
```

**问题**: 
- 文档数量超过10个时用户只能看到前10个
- 没有搜索功能
- 没有分页机制
- 无法预览文档内容

**建议**: 添加分页或搜索功能：
```python
search_term = st.text_input("🔍 搜索文档", placeholder="输入文档名...")
filtered_docs = [d for d in documents if search_term.lower() in d['filename'].lower()] if search_term else documents

# 分页
page_size = 10
page_count = (len(filtered_docs) + page_size - 1) // page_size
if page_count > 1:
    page = st.selectbox("页码", range(1, page_count + 1)) - 1
else:
    page = 0
    
for doc in filtered_docs[page * page_size:(page + 1) * page_size]:
    # ...
```

---

### 1.3 🟡 MEDIUM - 删除按钮无确认对话框，易误操作

**位置**: `pages/documents.py:77`

```python
if st.button("🗑️", key=f"del_{doc['id']}"):
    del_response = requests.delete(...)
```

**问题**: 删除操作没有二次确认，点击即删除，容易造成误操作丢失数据。

**建议**: 使用 `st.dialog` 或 session_state 标记确认状态：
```python
confirm_key = f"confirm_del_{doc['id']}"
if confirm_key not in st.session_state:
    st.session_state[confirm_key] = False

if not st.session_state[confirm_key]:
    if st.button("🗑️", key=f"del_{doc['id']}"):
        st.session_state[confirm_key] = True
        st.rerun()
else:
    st.warning(f"确认删除 {doc['filename']}？")
    col1, col2 = st.columns(2)
    if col1.button("确认", key=f"confirm_{doc['id']}"):
        # 执行删除
        st.session_state[confirm_key] = False
    if col2.button("取消", key=f"cancel_{doc['id']}"):
        st.session_state[confirm_key] = False
        st.rerun()
```

---

### 1.4 🟡 MEDIUM - 文档处理状态无实时反馈

**位置**: `pages/documents.py:35-44`

```python
with st.spinner("处理文档中..."):
    process_response = requests.post(...)
    if process_response.status_code == 200:
        st.success("✅ 文档处理完成")
```

**问题**: 
- 文档处理可能是异步操作，单次请求无法反映真实处理进度
- 没有轮询机制查看处理状态
- 大文档处理可能需要很长时间，用户不知道是否卡住

**建议**: 添加状态轮询机制或 WebSocket 实时推送。

---

### 1.5 🟢 LOW - 关闭系统交互分散，确认对话框位置不一致

**位置**: `app.py:246-282`

**问题**: 
- "保存数据"按钮没有实际功能，只是显示成功提示
- 关闭确认对话框在 main 区域显示，但触发按钮在 sidebar

---

### 1.6 🟢 LOW - 不支持聊天记录导出/导入

**位置**: 全局

**问题**: `messages` 存储在 session_state 中，页面刷新即丢失，且无法导出历史记录。

---

### 1.7 🔵 INFO - 界面布局在不同屏幕尺寸下可能错位

**位置**: `app.py:161-283`

**问题**: 使用 `st.sidebar` + 主内容区域布局，在窄屏设备上 sidebar 会折叠，可能影响使用体验。

---

## 2. 状态管理问题

### 2.1 🔴 CRITICAL - 多页面 session_state 键名冲突

**位置**: `app.py:41-50`, `pages/chat.py:12-16`

```python
# app.py
def init_session_state():
    if "messages" not in st.session_state:
        st.session_state.messages = []
    if "selected_docs" not in st.session_state:
        st.session_state.selected_docs = []

# pages/chat.py
def show():
    if "messages" not in st.session_state:
        st.session_state.messages = []
    if "reasoning_steps" not in st.session_state:
        st.session_state.reasoning_steps = []
```

**问题**: 
- `app.py` 和 `pages/chat.py` 都初始化 `messages`，逻辑重复且可能冲突
- 如果用户从 chat 页面进入，messages 状态可能不一致
- Streamlit 的多页面架构中，所有页面共享同一个 session_state

**建议**: 使用命名空间前缀区分不同页面：
```python
# 统一状态管理模块 state_manager.py
PAGE_KEYS = {
    "main": ["messages", "selected_docs", "current_doc"],
    "chat": ["chat_messages", "reasoning_steps"],
    "documents": ["doc_filter", "doc_page"]
}

def init_state(page: str):
    defaults = {
        f"{page}_{key}": default 
        for key, default in PAGE_DEFAULTS[page].items()
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value
```

---

### 2.2 🔴 HIGH - 会话状态未持久化，刷新页面数据丢失

**位置**: `app.py:43-44`, `pages/chat.py:12-16`

```python
if "messages" not in st.session_state:
    st.session_state.messages = []
```

**问题**: 
- 所有聊天历史、选择文档、思考流都存储在内存中
- 页面刷新后全部丢失
- 没有 localStorage/cookies 持久化

**建议**: 使用 `st.session_state` + `st.cache_data` 或本地存储：
```python
import json
import os

STATE_FILE = ".chat_history.json"

def load_persistent_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, 'r') as f:
            saved = json.load(f)
            for key, value in saved.items():
                if key not in st.session_state:
                    st.session_state[key] = value

def save_persistent_state():
    state_to_save = {
        "messages": st.session_state.get("messages", []),
        "selected_docs": st.session_state.get("selected_docs", [])
    }
    with open(STATE_FILE, 'w') as f:
        json.dump(state_to_save, f)
```

---

### 2.3 🔴 HIGH - selected_docs 状态耦合度高，sidebar 设置影响主界面

**位置**: `app.py:224-231`, `app.py:296-351`

```python
# sidebar 中设置
selected = st.multiselect(...)
st.session_state.selected_docs = selected

# chat 界面使用
if st.session_state.selected_docs:
    result = send_agent_task("summarize", st.session_state.selected_docs)
```

**问题**: 
- sidebar 和主界面通过 session_state 隐式耦合
- 没有明确的 props/state 传递机制
- 代码可读性和维护性差

**建议**: 使用明确的参数传递：
```python
def render_sidebar() -> List[str]:
    """返回选中的文档ID列表"""
    # ...
    return selected

def render_chat_interface(selected_docs: List[str]):
    """接收选中的文档作为参数"""
    # ...
    if selected_docs:
        result = send_agent_task("summarize", selected_docs)
```

---

### 2.4 🟡 MEDIUM - shutdown_requested 状态只在 app.py 中使用，其他页面无感知

**位置**: `app.py:49-50`, `app.py:396-397`

**问题**: 如果用户在 chat 或 documents 页面，无法触发关闭流程。

---

### 2.5 🟡 MEDIUM - session_state 初始化不完整，可能引发 KeyError

**位置**: `app.py:41-50`

**问题**: `init_session_state()` 只初始化了4个键，但代码中使用了更多键：
- `doc_uploader` (由 Streamlit 管理)
- `batch_uploader` (由 Streamlit 管理) 
- `doc_selector` (由 Streamlit 管理)
- `outline_topic`

虽然 Streamlit 组件会自动管理，但业务逻辑状态应该明确初始化。

---

### 2.6 🟡 MEDIUM - current_doc 状态声明但未使用

**位置**: `app.py:47-48`

```python
if "current_doc" not in st.session_state:
    st.session_state.current_doc = None
```

**问题**: 声明了 `current_doc` 但整个代码中没有使用。

---

### 2.7 🟢 LOW - 使用 time.sleep(1) 强制刷新，用户体验不佳

**位置**: `app.py:181-182`, `app.py:211-212`

```python
st.success(f"✅ 已上传: {result.get('filename', 'unknown')}")
time.sleep(1)
st.rerun()
```

**问题**: 固定等待1秒，实际上传可能已完成，用户被迫等待。

**建议**: 使用 st.spinner 提供即时反馈，或检查状态后刷新。

---

## 3. API 调用问题

### 3.1 🔴 HIGH - 文件上传无大小限制，可能导致内存溢出

**位置**: `app.py:83-97`, `pages/documents.py:22-29`

```python
def upload_document(file):
    file_bytes = file.getvalue() if hasattr(file, 'getvalue') else b''
    files = {"file": (file_name, file_bytes)}
    response = requests.post(..., files=files, timeout=60)
```

**问题**: 
- 没有文件大小验证
- 大文件直接读取到内存，可能耗尽服务器资源
- 后端也可能因此崩溃

**建议**: 添加上传前大小检查：
```python
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB

def upload_document(file):
    file_bytes = file.getvalue() if hasattr(file, 'getvalue') else b''
    
    if len(file_bytes) > MAX_FILE_SIZE:
        st.error(f"文件过大 ({len(file_bytes) / 1024 / 1024:.1f}MB)，最大支持 {MAX_FILE_SIZE / 1024 / 1024}MB")
        return None
    
    # 继续上传...
```

---

### 3.2 🔴 HIGH - API_BASE_URL 硬编码，环境切换困难

**位置**: `app.py:38`, `pages/documents.py:6`, `pages/chat.py:6`

```python
# app.py
API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000")

# pages/documents.py, pages/chat.py  
API_BASE_URL = "http://localhost:8000"  # 硬编码！
```

**问题**: 
- pages 目录下的文件硬编码 API 地址
- 无法通过环境变量配置
- 生产环境部署时需要修改多处代码

**建议**: 统一配置文件：
```python
# frontend/config.py
import os

API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000")
DEFAULT_TIMEOUT = int(os.getenv("API_TIMEOUT", "30"))
MAX_UPLOAD_SIZE = int(os.getenv("MAX_UPLOAD_SIZE", "52428800"))

# 各文件引用
from config import API_BASE_URL
```

---

### 3.3 🔴 HIGH - fetch_documents 错误静默处理，用户无法获知后端故障

**位置**: `app.py:73-81`

```python
def fetch_documents() -> List[dict]:
    try:
        response = requests.get(f"{API_BASE_URL}/api/documents", timeout=10)
        response.raise_for_status()
        return response.json()
    except requests.RequestException:
        return []  # 静默返回空列表
```

**问题**: 
- 后端故障时返回空列表
- 用户看到"暂无文档"，无法区分是真无文档还是后端故障
- 没有错误日志记录

**建议**: 
```python
def fetch_documents() -> tuple[List[dict], Optional[str]]:
    try:
        response = requests.get(f"{API_BASE_URL}/api/documents", timeout=10)
        response.raise_for_status()
        return response.json(), None
    except requests.ConnectionError:
        return [], "无法连接到后端服务，请检查服务是否启动"
    except requests.Timeout:
        return [], "获取文档列表超时，请稍后重试"
    except requests.RequestException as e:
        return [], f"获取文档失败: {str(e)}"

# 调用处
documents, error = fetch_documents()
if error:
    st.error(error)
```

---

### 3.4 🟡 MEDIUM - 批量上传无事务回滚，部分失败状态不一致

**位置**: `app.py:100-121`

**问题**: 
- 批量上传是逐个文件上传
- 部分失败时，成功的文件已入库
- 用户需要手动删除已上传的文件
- 没有批量删除或回滚机制

**建议**: 添加批量上传 API，支持原子性操作；或提供批量删除功能。

---

### 3.5 🟡 MEDIUM - API 调用缺乏统一封装，重复代码多

**位置**: 全局

**问题**: 每个 API 调用都单独处理：
- 超时设置不一致 (10s, 30s, 60s, 120s)
- 错误处理方式不同
- URL 拼接重复

**建议**: 统一 API 客户端：
```python
class APIClient:
    def __init__(self, base_url: str, default_timeout: int = 30):
        self.base_url = base_url
        self.default_timeout = default_timeout
    
    def _request(self, method: str, endpoint: str, **kwargs) -> tuple[Optional[dict], Optional[str]]:
        url = f"{self.base_url}{endpoint}"
        timeout = kwargs.pop('timeout', self.default_timeout)
        try:
            response = requests.request(method, url, timeout=timeout, **kwargs)
            response.raise_for_status()
            return response.json(), None
        except requests.Timeout:
            return None, "请求超时，请稍后重试"
        except requests.RequestException as e:
            return None, f"请求失败: {str(e)}"
    
    def get_documents(self) -> tuple[List[dict], Optional[str]]:
        return self._request("GET", "/api/documents", timeout=10)
    
    def upload_document(self, file: bytes, filename: str) -> tuple[Optional[dict], Optional[str]]:
        files = {"file": (filename, file)}
        return self._request("POST", "/api/documents", files=files, timeout=60)
```

---

### 3.6 🟡 MEDIUM - 没有请求重试机制，网络抖动导致失败

**位置**: 全局

**问题**: 所有 API 调用都是单次尝试，网络不稳定时容易失败。

**建议**: 使用 `urllib3` 或自定义装饰器实现重试：
```python
from functools import wraps
import time

def retry_on_failure(max_retries=3, delay=1):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            last_error = None
            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except requests.RequestException as e:
                    last_error = e
                    if attempt < max_retries - 1:
                        time.sleep(delay * (attempt + 1))
            raise last_error
        return wrapper
    return decorator
```

---

### 3.7 🟡 MEDIUM - send_query 和 chat.py 中的查询 API 不一致

**位置**: `app.py:124-140`, `pages/chat.py:64-72`

```python
# app.py
payload = {
    "question": question,
    "mode": "rag",  # 固定为 rag
    "top_k": 5,
    "document_ids": document_ids,
}

# pages/chat.py  
payload = {
    "question": prompt,
    "mode": mode,  # 用户选择
    "top_k": top_k  # 用户选择
}
```

**问题**: 
- app.py 中固定 mode="rag"，无法使用 agentic 模式
- pages/chat.py 支持 mode 选择
- 两个界面功能不一致，用户困惑

---

### 3.8 🟢 LOW - 响应数据处理缺乏字段验证

**位置**: `app.py:76-78`

```python
response = requests.get(f"{API_BASE_URL}/api/documents", timeout=10)
response.raise_for_status()
return response.json()
```

**问题**: 直接返回 JSON，没有验证必需字段是否存在。

**建议**: 使用 Pydantic 验证响应结构。

---

### 3.9 🟢 LOW - documents.py 中 API 调用没有超时设置

**位置**: `pages/documents.py:26-28`, `36-38`, `78-79`

```python
response = requests.post(f"{API_BASE_URL}/api/documents", files=files)
# 没有 timeout 参数！
```

**问题**: 没有超时设置，可能无限期挂起。

---

### 3.10 🔵 INFO - API 响应没有缓存，重复请求浪费资源

**位置**: 全局

**问题**: `fetch_documents()` 在每次 rerender 时都被调用，频繁刷新文档列表。

---

## 4. 性能问题

### 4.1 🔴 HIGH - st.rerun() 滥用导致频繁完整重新渲染

**位置**: `app.py:182`, `212`, `308`, `326`, `347`, `pages/chat.py:86`

**问题**: 
- 大量使用 `st.rerun()` 刷新页面
- Streamlit 每次 rerender 都会重新执行整个脚本
- 文档列表等数据会被重复获取

**建议**: 
- 使用 `st.session_state` 缓存状态
- 使用 `st.cache_data` 缓存 API 响应
- 减少不必要的 rererun

---

### 4.2 🟡 MEDIUM - 文档列表无缓存，每次交互重新获取

**位置**: `app.py:218`

```python
documents = fetch_documents()
```

**问题**: 每次用户交互都会重新获取文档列表。

**建议**: 
```python
@st.cache_data(ttl=30)  # 缓存30秒
def fetch_documents_cached() -> List[dict]:
    return fetch_documents()
```

---

### 4.3 🟡 MEDIUM - 聊天历史无限增长，内存占用持续增加

**位置**: `app.py:44`, `pages/chat.py:13`

```python
if "messages" not in st.session_state:
    st.session_state.messages = []
```

**问题**: 
- messages 列表只增不减
- 长期会话可能积累大量消息
- session_state 存储在内存中，可能导致内存泄漏

**建议**: 
```python
MAX_MESSAGES = 100

def add_message(role: str, content: str):
    st.session_state.messages.append({"role": role, "content": content})
    # 保留最近 N 条
    if len(st.session_state.messages) > MAX_MESSAGES:
        st.session_state.messages = st.session_state.messages[-MAX_MESSAGES:]
```

---

### 4.4 🟡 MEDIUM - ZIP 文件解压直接读入内存，大文件可能 OOM

**位置**: `app.py:197-201`

```python
if file.name.endswith('.zip'):
    with zipfile.ZipFile(BytesIO(file.getvalue())) as z:
        for zip_file in z.namelist():
            if zip_file.endswith(('.pdf', '.doc', ...)):
                all_files.append(FileWrapper(zip_file, z.read(zip_file)))
```

**问题**: 
- `z.read(zip_file)` 将整个文件读入内存
- 大 ZIP 包内的大文件可能导致内存溢出
- 没有解压大小限制

**建议**: 流式处理或限制总大小：
```python
MAX_ZIP_CONTENT_SIZE = 100 * 1024 * 1024  # 100MB 解压限制
total_size = 0

for zip_file in z.namelist():
    info = z.getinfo(zip_file)
    total_size += info.file_size
    if total_size > MAX_ZIP_CONTENT_SIZE:
        st.error("ZIP 内容超过最大限制")
        return
```

---

### 4.5 🟢 LOW - FileWrapper 类没有实现完整的文件接口

**位置**: `app.py:20-27`

```python
class FileWrapper:
    def __init__(self, name: str, data: bytes):
        self.name = name
        self._data = data
    
    def getvalue(self) -> bytes:
        return self._data
```

**问题**: 
- 只实现了 `name` 和 `getvalue()`
- 如果后端需要其他文件属性（如 size, type）会报错
- 没有类型检查

**建议**: 继承或实现完整的文件协议。

---

### 4.6 🟢 LOW - 没有使用 generator 处理大列表

**位置**: `pages/documents.py:58`

```python
for doc in documents:
    # 渲染每个文档
```

**问题**: 文档数量很大时一次性渲染所有。

**建议**: 使用分页或虚拟滚动。

---

## 5. 代码组织问题

### 5.1 🔴 HIGH - 多页面架构重复定义 API_BASE_URL

**位置**: `app.py:38`, `pages/documents.py:6`, `pages/chat.py:6`

**问题**: API 地址分散在多个文件，维护困难。

**建议**: 统一配置文件，参见 3.2。

---

### 5.2 🟡 MEDIUM - FileWrapper 类定义在 app.py，其他页面可能重复定义

**位置**: `app.py:20-27`

**问题**: 
- 工具类定义在主应用文件
- 其他页面需要使用时要重复定义或导入困难
- 职责不分离

**建议**: 移到 `frontend/utils/file_utils.py`。

---

### 5.3 🟡 MEDIUM - 文件类型验证逻辑分散且不统一

**位置**: `app.py:173`, `188-189`, `199`, `pages/documents.py:18`

```python
# app.py 多处不同的类型列表
type=["pdf", "doc", "docx", "ppt", "pptx", "md", "txt"]
type=["pdf", "doc", "docx", "ppt", "pptx", "md", "txt", "zip"]

# pages/documents.py  
type=["pdf", "doc", "docx", "ppt", "pptx", "md", "markdown", "txt"]
```

**问题**: 
- 支持的文件类型列表不一致
- `md` vs `markdown` 命名不统一
- 维护困难

**建议**: 统一定义常量：
```python
# config.py
SUPPORTED_TYPES = ["pdf", "doc", "docx", "ppt", "pptx", "md", "txt"]
BATCH_SUPPORTED_TYPES = SUPPORTED_TYPES + ["zip"]
```

---

### 5.4 🟡 MEDIUM - pages/ 目录下的文件入口不统一

**位置**: `pages/documents.py`, `pages/chat.py`

**问题**: 
- 两个文件都定义了 `show()` 函数作为入口
- 但 app.py 中没有调用它们
- Streamlit 多页面机制需要特定结构

**建议**: 遵循 Streamlit 多页面规范或使用统一的页面路由。

---

### 5.5 🟡 MEDIUM - Magic string/number 过多

**位置**: 全局

```python
documents[:10]  # 10 是什么？
timeout=30      # 30秒是怎么定的？
time.sleep(1)   # 1秒是否足够？
MAX_MESSAGES = 100  # 不存在，但应该存在
```

**问题**: 大量硬编码值，可读性和可维护性差。

**建议**: 提取为命名常量。

---

### 5.6 🟢 LOW - 错误信息中英文混杂

**位置**: 全局

```python
st.error(f"上传失败 {getattr(file, 'name', str(file))}: {e}")
st.error(f"查询失败: {e}")
st.error("获取文档列表失败")
```

**问题**: 部分错误信息是中文，部分是英文（异常信息）。

**建议**: 统一错误信息语言，或根据用户偏好动态切换。

---

### 5.7 🟢 LOW - 缺少类型注解和文档字符串

**位置**: `app.py` 部分函数

**问题**: 部分函数没有完整的 docstring 和类型注解。

---

### 5.8 🔵 INFO - 项目结构不符合 Streamlit 最佳实践

**位置**: 目录结构

**问题**: 
- `app.py` 在 frontend 根目录
- `pages/` 在 frontend 下
- 但 Streamlit 通常要求 `pages/` 与主脚本同级或特定结构

---

## 6. 可访问性问题

### 6.1 🟡 MEDIUM - 错误提示缺乏上下文，用户不知如何修复

**位置**: `app.py:79-80`

```python
except requests.RequestException:
    return []
```

**问题**: 错误被吞掉，用户看到空列表但不知道原因。

**建议**: 提供清晰的错误信息和修复建议。

---

### 6.2 🟡 MEDIUM - 上传进度指示不完整

**位置**: `app.py:103-120`

```python
progress_bar = st.progress(0)
status_text = st.empty()
for i, file in enumerate(files):
    progress = (i + 1) / total
    progress_bar.progress(progress)
```

**问题**: 
- 只有文件级别的进度
- 没有上传速度、剩余时间估计
- 大文件上传时用户不知道进度

**建议**: 添加上传速度和 ETA 显示。

---

### 6.3 🟡 MEDIUM - 空状态缺乏引导

**位置**: `app.py:220-221`

```python
if not documents:
    st.info("暂无文档，请上传")
```

**问题**: 
- 只有文字提示，没有操作按钮
- 没有示例文档或快速开始引导

**建议**: 添加快速操作按钮：
```python
if not documents:
    st.info("📭 暂无文档")
    st.write("开始使用：")
    if st.button("📤 上传文档"):
        st.switch_page("pages/documents.py")
    if st.button("📖 查看示例"):
        load_sample_documents()
```

---

### 6.4 🟢 LOW - 按钮使用 emoji，可能无法访问

**位置**: `app.py:253`, `256`, `pages/documents.py:77`

```python
if st.button("🛑 停止服务", ...)
if st.button("🗑️", key=f"del_{doc['id']}")
```

**问题**: 
- 仅使用 emoji 作为按钮标识
- 屏幕阅读器可能无法正确朗读
- 视觉障碍用户可能无法理解

**建议**: 使用文字 + emoji：
```python
if st.button("停止服务 🛑", ...)
if st.button("删除 🗑️", key=f"del_{doc['id']}")
```

---

### 6.5 🟢 LOW - 颜色对比度未验证

**位置**: 全局

**问题**: Streamlit 默认主题的颜色对比度可能不符合 WCAG 标准。

---

### 6.6 🟢 LOW - 键盘导航支持有限

**位置**: 全局

**问题**: Streamlit 组件通常支持键盘导航，但复杂的交互（如批量选择）可能不够友好。

---

### 6.7 🟢 LOW - 没有加载骨架屏，空白等待体验差

**位置**: `app.py:177`, `pages/documents.py:35`

**问题**: 使用 `st.spinner`，但内容区域空白。

---

### 6.8 🔵 INFO - 没有暗黑模式支持

**位置**: 全局

**问题**: 只使用 Streamlit 默认主题，没有暗黑模式切换。

---

### 6.9 🔵 INFO - 没有响应式布局适配

**位置**: 全局

**问题**: 布局主要针对桌面端，移动端体验可能不佳。

---

### 6.10 🔵 INFO - 缺少帮助提示和工具提示

**位置**: 部分组件

**问题**: 部分复杂功能缺少 `help` 参数说明。

---

## 7. 安全审查

### 7.1 🟡 MEDIUM - subprocess 调用存在命令注入风险

**位置**: `app.py:53-70`

```python
def shutdown_services():
    subprocess.Popen(["bash", stop_script], ...)
```

**问题**: 
- 虽然使用了列表传参，但 `stop_script` 来自路径拼接
- 如果路径被篡改可能执行恶意脚本

**建议**: 验证脚本路径：
```python
def shutdown_services():
    project_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    stop_script = os.path.join(project_dir, "scripts", "stop.sh")
    
    # 验证路径安全性
    real_script = os.path.realpath(stop_script)
    real_project = os.path.realpath(project_dir)
    if not real_script.startswith(real_project):
        st.error("非法脚本路径")
        return False
    
    if os.path.exists(stop_script):
        subprocess.Popen(["bash", stop_script], ...)
```

---

### 7.2 🟡 MEDIUM - ZIP 文件路径遍历风险

**位置**: `app.py:197-201`

```python
for zip_file in z.namelist():
    if zip_file.endswith(('.pdf', '.doc', '.docx', '.ppt', '.pptx', '.md', '.txt')):
        all_files.append(FileWrapper(zip_file, z.read(zip_file)))
```

**问题**: 
- 没有验证 ZIP 内文件路径
- 恶意 ZIP 可能包含 `../../../etc/passwd` 等路径

**建议**: 验证路径：
```python
for zip_file in z.namelist():
    # 防止路径遍历
    if os.path.isabs(zip_file) or '..' in zip_file:
        st.warning(f"跳过不安全路径: {zip_file}")
        continue
```

---

### 7.3 🟢 LOW - API 没有 CSRF 保护

**位置**: 全局

**问题**: Streamlit 作为前端，API 调用没有 CSRF token。

---

## 8. 改进建议汇总

### 立即修复（上线前必须）

1. **修复 session_state 键名冲突** - 使用命名空间前缀
2. **添加文件大小限制** - 防止内存溢出
3. **统一 API_BASE_URL 配置** - 提取到配置文件
4. **修复 fetch_documents 静默错误** - 提供错误反馈

### 短期改进（1-2 周内）

5. **实现 API 客户端封装** - 统一错误处理和重试
6. **添加文档列表缓存** - 减少 API 调用
7. **添加删除确认对话框** - 防止误操作
8. **优化批量上传错误显示** - 显示完整失败列表
9. **限制聊天历史长度** - 防止内存泄漏

### 中期改进（1 个月内）

10. **实现聊天记录持久化** - 导出/导入功能
11. **添加文档搜索和分页** - 处理大量文档
12. **优化 ZIP 文件处理** - 流式解压，限制大小
13. **完善可访问性** - 错误提示、键盘导航
14. **代码重构** - 提取工具类、统一常量

---

## 9. 结论

该 Streamlit 前端代码实现了基本功能，但存在以下主要问题：

1. **架构层面**: 多页面 session_state 管理混乱，需要统一状态管理方案
2. **稳定性**: 缺乏错误处理和重试机制，API 故障时用户体验差
3. **性能**: 频繁 rerender 和缺乏缓存可能导致性能问题
4. **安全**: 文件上传和 subprocess 调用需要加强安全验证

考虑到项目计划迁移到 MCP Server 架构，建议：
- **短期**: 修复 CRITICAL 和 HIGH 级别问题，确保基本可用
- **长期**: 新架构采用更成熟的前端框架（如 React + TypeScript），避免 Streamlit 的局限性

---

**审查人**: AI Code Reviewer  
**下次审查建议**: 修复 CRITICAL/HIGH 问题后进行复审
