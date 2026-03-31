# TODO - AI 知识库全栈开发

## Phase 1: 基础架构 + 文档解析
- [x] 创建项目结构
- [x] 创建 `.agentstalk/` 目录及通讯文件
- [x] 创建 `requirements.txt`
- [x] 创建 `backend/models/schemas.py`（Pydantic 模型）
- [x] 实现 `backend/vector_store/chroma_manager.py`
- [x] 实现 `backend/core_logic/parser.py`

## Phase 2: FastAPI 后端
- [x] 实现 `backend/api/documents.py`
- [x] 实现 `backend/api/query.py`
- [x] 实现 `backend/main.py`

## Phase 3: LangGraph Agent
- [x] 实现 `backend/core_logic/agent.py`

## Phase 4: Streamlit 前端
- [x] 实现 `frontend/app.py`
- [x] 实现 `frontend/pages/documents.py`
- [x] 实现 `frontend/pages/chat.py`

## 功能增强 (已完成)
- [x] 一键启动/停止脚本 (start.sh / stop.sh / status.sh)
- [x] 前端一键 Shutdown 按钮 (保存→关页面→停止服务)
- [x] 文件夹批量上传支持
- [x] 扩展文件类型支持 (PPT, DOC, DOCX)
- [x] 检索性能优化 (索引/缓存/并发)

## Verification
- [ ] 启动后端测试
- [ ] 启动前端测试
- [ ] RAG 召回测试
- [ ] Agentic Notes 思考流测试
