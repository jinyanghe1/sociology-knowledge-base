# 架构简化研究 - MCP 路线

## 当前架构问题

- FastAPI + Streamlit + ChromaDB + LangGraph + Ollama
- 5+ 技术栈，依赖冲突频发
- 部署复杂，多进程管理

## 简化架构方案

```
用户提问
    ↓
MCP Server (Python)
  ├── tool: rag_search(query) → ChromaDB 语义检索
  ├── tool: index_document(path) → 解析+向量化
  └── tool: list_documents() → 文档管理
    ↓
MCP Client (Claude Desktop / Cursor / kimi)
    ↓
云端 LLM 推理 (Claude/kimi) + 本地检索结果
    ↓
输出回答 (包含来源标注)
```

## 技术可行性分析

### MCP (Model Context Protocol) 是什么？

- **定位**: AI 应用的 "USB-C" 接口标准 (open protocol)
- **支持客户端**: Claude Desktop, ChatGPT, Cursor, VS Code, Claude Code 等
- **官方 SDK**: TypeScript, Python (Tier 1), C#, Go, Java, Rust 等

### Python MCP SDK (FastMCP)

```python
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("Knowledge Base", json_response=True)

@mcp.tool()
def rag_search(query: str, top_k: int = 5) -> list:
    """RAG 语义检索"""
    ...

@mcp.tool()
def index_document(path: str) -> dict:
    """解析并索引文档"""
    ...

if __name__ == "__main__":
    mcp.run(transport="streamable-http")
```

### 优势

| 维度 | 原方案 | MCP 方案 |
|------|--------|----------|
| 部署 | FastAPI + Streamlit + 多进程 | 单一 MCP Server |
| 依赖 | Ollama + LangGraph + FastAPI + Streamlit | 仅 MCP SDK + ChromaDB |
| 客户端 | 自建 UI | Claude Desktop / Cursor 等 |
| 推理能力 | 本地 Ollama (受限) | 云端 Claude/kimi (强大) |
| 维护 | 5+ 技术栈 | 1 个 MCP Server |

### 局限性

1. **需要网络**: 云端 LLM (Claude/kimi) 需要联网
2. **离线不可用**: 无 Ollama 作为备用
3. **数据同步**: 用户上传流程需适配

## 实现路径

### Phase 1: MCP Server 实现
- 安装 `mcp` Python SDK
- 实现 `rag_search(query)` tool
- 实现 `index_document(path)` tool
- 实现 `list_documents()` tool
- 配置 ChromaDB 向量存储

### Phase 2: Claude Desktop 配置
- 安装 Claude Desktop
- 配置 MCP Server 连接 (JSON 配置)
- 测试 RAG 检索流程

### Phase 3: 文档管理 (可选)
- 如果需要，可保留 FastAPI 接口做文档上传
- 或通过 Claude 对话直接指定文件路径

## 依赖对比

```
# 原方案 requirements.txt
fastapi, uvicorn, streamlit, chromadb, ollama, langchain, langgraph, pydantic, ...

# MCP 方案
mcp (Python SDK), chromadb, pdfplumber, python-docx, python-pptx, beautifulsoup4
```

## 结论

**可行性: ✅ 高**
- MCP 是成熟标准，Python SDK 完善
- 架构大幅简化，依赖减少 80%+
- 复用 Claude Desktop 等成熟客户端，无需自建 UI

**推荐实施:**
1. 废弃 FastAPI/Streamlit 层
2. 新建 `mcp_server/` 目录实现 MCP Server
3. 保留 `backend/vector_store/` 和 `backend/core_logic/parser.py`
4. 通过 Claude Desktop 作为前端交互

## 参考资料

- MCP 官方文档: https://modelcontextprotocol.io/
- Python SDK: https://py.sdk.modelcontextprotocol.io/
- 官方示例服务器: https://github.com/modelcontextprotocol/servers
