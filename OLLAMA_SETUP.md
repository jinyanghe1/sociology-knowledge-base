# Ollama 配置指南

## 概述

MCP Server 支持两种 embedding 模式：
- **推荐**: Ollama + `nomic-embed-text` - 真实语义向量，检索质量高
- **Fallback**: Hash-based - 无需 Ollama，仅用于测试开发

## 安装 Ollama

### macOS
```bash
brew install ollama
```

### Linux
```bash
curl -fsSL https://ollama.com/install.sh | sh
```

### Windows
下载安装包: https://ollama.com/download

## 启动 Ollama 服务

```bash
# 启动服务 (保持终端运行)
ollama serve

# 或者后台运行
ollama serve &
```

## 下载 Embedding 模型

```bash
# 下载推荐模型 (约 270MB)
ollama pull nomic-embed-text

# 可选: 下载 LLM 模型用于本地推理
ollama pull deepseek-r1:1.5b
```

## 验证安装

```bash
# 检查 Ollama 状态
ollama list

# 测试 embedding
curl http://localhost:11434/api/embeddings -d '{
  "model": "nomic-embed-text",
  "prompt": "Hello world"
}'
```

## MCP Server 自动检测

MCP Server 启动时会自动检测 Ollama：
- ✅ **Ollama 可用**: 使用 `nomic-embed-text` 生成真实 embedding
- ⚠️ **Ollama 不可用**: 自动回退到 hash-based embedding（仅开发测试）

## 配置检查清单

- [ ] Ollama 已安装
- [ ] `ollama serve` 正在运行
- [ ] `nomic-embed-text` 模型已下载
- [ ] `ollama list` 能看到模型

## 故障排除

### "Ollama unavailable" 警告
```bash
# 检查服务是否运行
curl http://localhost:11434/api/tags

# 如果没运行，启动它
ollama serve
```

### 模型下载失败
```bash
# 手动下载
ollama pull nomic-embed-text

# 检查网络/代理设置
```

### 内存不足
```bash
# nomic-embed-text 需要约 500MB 内存
# 如果内存不足，使用轻量级替代模型:
ollama pull mxbai-embed-large  # 或更小的模型
```

## 性能对比

| 模式 | 向量质量 | 启动速度 | 适用场景 |
|------|---------|---------|---------|
| Ollama | ⭐⭐⭐ 高 | 慢 (需启动服务) | 生产环境 |
| Hash | ⭐ 低 | 快 (无依赖) | 开发测试 |

## 生产环境建议

1. **必须安装 Ollama** - hash-based 仅用于开发
2. **开机自启** - 配置 Ollama 服务开机启动
3. **监控** - 监控 Ollama 服务健康状态
