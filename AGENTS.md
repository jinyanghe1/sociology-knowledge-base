# AI 知识库全栈开发协同指令

1. 项目愿景与功能清单 (MVP 阶段)
目标是打造一个本地运行的、类 NotebookLM 的精简知识库。功能核心在于**“理解”**而非简单的“存储”。

本地文档解析： 支持 PDF、Markdown 及纯文本的自动扫描与向量化。

RAG 问答引擎： 基础的检索增强生成，支持针对特定文档或全库提问。

Agentic Notes： 允许用户触发“思考流”，例如：“帮我总结这三篇文档的矛盾点”或“基于现有资料写一份大纲”。

极简 UI： 左右分栏布局（左侧文档列表/预览，右侧对话框）。

1. 技术路径 (Tech Stack)
后端： Python + FastAPI

向量数据库： ChromaDB 或 LanceDB (本地嵌入，无需部署)

LLM 框架： LangGraph 或 CrewAI (用于管理多 Agent 工作流)

本地推演： Ollama (支持 DeepSeek 或 Llama3)

前端： Streamlit 或 Next.js (取决于追求开发速度还是交互体验)

1. 多 Agent 协作规范
为了防止开发冲突，所有参与 Agent 必须遵守以下准则：

文件锁定机制： 禁止两个 Agent 同时修改同一个 .py 或 .tsx 文件。

模块化原则： 按照 API、Core_Logic、Vector_Store、UI 严格拆分目录。

原子化提交： 每次功能实现后，必须先运行静态语法检查，确认无误后再合并。

禁止重复轮子： 在实现新函数前，必须先检索 utils/ 目录下是否已有类似实现。

1. 通讯协议：$(cwd)/.agentstalk/*
所有 Agent 必须通过读取和写入 .agentstalk/ 目录下的文件同步进度，严禁私自更改架构。

TODO.md： 总任务清单。申领任务时需加锁（例如：Backend-Agent is working on Item #3）。

SCHEMA.json： 存储全局数据结构、API 接口定义。变更此文件需所有 Agent 重新确认。

MESSAGES.log： 跨 Agent 沟通记录（如：前端 Agent 留言给后端 Agent ：“请在 /query 接口增加 similarity_score 字段”）。

SNAPSHOT.txt： 当前已完成的模块路径及功能摘要。
