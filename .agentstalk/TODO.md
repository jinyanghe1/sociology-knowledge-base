# TODO - AI 知识库 MCP 架构

## 架构路线: MCP Server (替代 FastAPI + Streamlit)

```
用户提问 → MCP Server (ChromaDB RAG) → Claude Desktop/kimi 推理 → 回答
```

## Phase M1: MCP Server 核心 ✅ 已完成
- [x] 创建 `mcp_server/` 目录结构
- [x] 安装 MCP Python SDK
- [x] 实现 `rag_search(query, top_k)` tool
- [x] 实现 `index_document(path)` tool
- [x] 实现 `index_folder(path, recursive)` tool (批量索引)
- [x] 实现 `list_documents()` tool
- [x] 实现 `get_document_info(id)` tool
- [x] 实现 `get_document_chunks(id)` tool
- [x] 实现 `delete_document(id)` tool
- [x] 实现 `get_stats()` tool
- [x] 共 8 个 MCP tools 注册成功

## Phase M2: 持久化 & 文档管理 ✅ 已完成
- [x] 复用 `backend/core_logic/parser.py` (PDF/DOCX/DOC/PPTX/PPT/MD/TXT/HTML)
- [x] 复用 `backend/vector_store/chroma_manager.py` (ChromaDB + fallback)
- [x] 复用 `backend/core_logic/embedding.py` (Ollama + hash fallback)
- [x] 文档元数据持久化到 JSON (`mcp_data/documents.json`)
- [x] 数据统一存储在 `mcp_data/` 目录

## Phase M3: Claude Desktop 配置 ✅ 已完成
- [x] 编写 `CLAUDE_DESKTOP_CONFIG.md` (含 8 个工具说明)
- [x] E2E 测试通过: index → search → info → chunks → delete
- [x] index_folder 批量索引测试通过
- [x] JSON 持久化测试通过 (重启不丢失)
- [ ] 用户 Claude Desktop 实际接入测试 (待用户操作)

## 新增文件
- `mcp_server/server.py` - MCP Server 主程序
- `requirements-mcp.txt` - MCP 方案精简依赖
- `CLAUDE_DESKTOP_CONFIG.md` - Claude Desktop 配置指南

## 启动方式
```bash
cd /Users/hejinyang/Desktop/社会学考研资料
pip install -r requirements-mcp.txt
python mcp_server/server.py
```

## 旧架构 (FastAPI 方案 - 可废弃)
- backend/, frontend/ 暂时保留
- 后续可删除
