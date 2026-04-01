# Claude Desktop MCP 配置

## 安装依赖

```bash
cd /Users/hejinyang/Desktop/社会学考研资料
pip install -r requirements-mcp.txt
```

## Claude Desktop 配置

打开 Claude Desktop 设置，添加以下配置：

### macOS 配置文件
路径: `~/Library/Application Support/Claude/claude_desktop_config.json`

```json
{
  "mcpServers": {
    "knowledge-base": {
      "command": "python",
      "args": [
        "-u",
        "/Users/hejinyang/Desktop/社会学考研资料/mcp_server/server.py"
      ],
      "env": {
        "PYTHONPATH": "/Users/hejinyang/Desktop/社会学考研资料"
      }
    }
  }
}
```

### 重启 Claude Desktop

配置完成后，重启 Claude Desktop 使配置生效。

## 可用工具 (9 个)

| 工具 | 功能 |
|------|------|
| `rag_search(query, top_k, workspace)` | 语义检索（支持 workspace 限定） |
| `index_document(file_path, workspace)` | 索引单个文档（可指定 workspace） |
| `index_folder(folder_path, recursive, workspace)` | 批量索引（自动按文件夹分组） |
| `list_documents()` | 列出所有已索引文档 |
| `list_workspaces()` | 列出所有 workspaces |
| `get_document_info(document_id)` | 查看文档详情 |
| `get_document_chunks(document_id)` | 查看文档分块内容 |
| `delete_document(document_id)` | 删除文档 |
| `get_stats()` | 知识库统计 |

### 示例对话

```
# 1. 索引文件夹（自动使用文件夹名作为 workspace）
用户: 帮我索引一下 /Users/hejinyang/Desktop/社会学考研资料/社会学核心理论/ 目录

# 2. 全库搜索
用户: 基于知识库，回答"社会学的主要理论流派有哪些？"

# 3. 限定 workspace 搜索（更精准）
用户: 在"社会学核心理论"workspace中搜索"涂尔干的社会分工论"

# 4. 查看 workspaces
用户: 列出所有可用的 workspaces

# 5. 列出所有文档
用户: 列出所有已索引的文档
```

## 支持的文档格式

PDF, DOCX, DOC, PPTX, PPT, Markdown, TXT, HTML

## 数据存储

- 文档副本: `mcp_data/uploads/`
- 向量索引: `mcp_data/chroma/`
- 文档元数据: `mcp_data/documents.json` (JSON 持久化，重启不丢失)

## 前置要求

### Ollama 配置（强烈推荐）

生产环境 **必须** 安装 Ollama，否则检索质量极低。

```bash
# 安装
brew install ollama    # macOS
curl -fsSL https://ollama.com/install.sh | sh  # Linux

# 启动服务
ollama serve

# 下载 embedding 模型
ollama pull nomic-embed-text
```

详见 [OLLAMA_SETUP.md](./OLLAMA_SETUP.md)

## Workspace（作用域限定）

使用 workspace 限定语义检索范围：

- `index_folder()` 自动使用文件夹名作为 workspace
- `rag_search(workspace="xxx")` 限定搜索范围
- `list_workspaces()` 查看所有工作区

```python
# 索引文件夹 → workspace = "社会学核心理论"
index_folder("/path/to/社会学核心理论/")

# 限定 workspace 搜索
rag_search("涂尔干理论", workspace="社会学核心理论")
```

## 注意事项

1. **首次使用**: 需要先索引文档才能进行 RAG 检索
2. **Ollama**: 生产环境必须安装，使用 `nomic-embed-text` 生成语义 embedding
3. **无 Ollama**: 自动回退到 hash-based embedding（仅用于开发测试，检索质量极低）
4. **Workspace**: 使用文件夹名自动分组，或使用 workspace 参数手动指定

## 故障排除

### 连接失败
- Claude Desktop 使用 stdio 传输，无需端口；确认配置文件 JSON 格式正确
- 测试 MCP Server 可单独运行: `python mcp_server/server.py`

### 找不到工具
- 重启 Claude Desktop
- 检查 `PYTHONPATH` 是否指向项目根目录
