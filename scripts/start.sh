#!/bin/bash
# AI Knowledge Base - 一键启动脚本
# Usage: ./scripts/start.sh

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
VENV_DIR="$PROJECT_DIR/.venv"
BACKEND_PID_FILE="$PROJECT_DIR/.agentstalk/backend.pid"
FRONTEND_PID_FILE="$PROJECT_DIR/.agentstalk/frontend.pid"
MCP_PID_FILE="$PROJECT_DIR/.agentstalk/mcp.pid"

echo -e "${BLUE}🚀 AI Knowledge Base 启动脚本${NC}"
echo "========================================"

# Check/create virtual environment
if [ ! -d "$VENV_DIR" ]; then
    echo -e "${YELLOW}▶ 创建虚拟环境...${NC}"
    python3 -m venv "$VENV_DIR"
fi

source "$VENV_DIR/bin/activate"
echo -e "${GREEN}✓ Python: $(python --version)${NC}"

# Install dependencies if needed
echo -e "${YELLOW}▶ 检查依赖...${NC}"
PIP_PKG_COUNT=$(python -m pip list 2>/dev/null | wc -l)
if [ "$PIP_PKG_COUNT" -lt 20 ]; then
    echo -e "${YELLOW}▶ 安装依赖 (首次运行)...${NC}"
    python -m pip install -r "$PROJECT_DIR/requirements.txt" -q
fi
echo -e "${GREEN}✓ 依赖就绪 (${PIP_PKG_COUNT} packages)${NC}"

# Create directories
mkdir -p "$PROJECT_DIR/uploads" "$PROJECT_DIR/data/chroma" "$PROJECT_DIR/logs" "$PROJECT_DIR/.agentstalk"

# Cleanup old PID files
rm -f "$BACKEND_PID_FILE" "$FRONTEND_PID_FILE" "$MCP_PID_FILE"

# Start Backend
echo -e "${YELLOW}▶ 启动后端 (FastAPI :8000)...${NC}"
cd "$PROJECT_DIR"
python -m uvicorn backend.main:app \
    --host 0.0.0.0 \
    --port 8000 \
    --reload \
    --log-level info > "$PROJECT_DIR/logs/backend.log" 2>&1 &
BACKEND_PID=$!
echo $BACKEND_PID > "$BACKEND_PID_FILE"
echo -e "${GREEN}✓ 后端 PID: $BACKEND_PID${NC}"

# Wait for backend
echo -e "${YELLOW}▶ 等待后端就绪...${NC}"
for i in {1..30}; do
    if curl -s http://localhost:8000/health > /dev/null 2>&1; then
        echo -e "${GREEN}✓ 后端已就绪${NC}"
        break
    fi
    sleep 0.5
    if [ $i -eq 30 ]; then
        echo -e "${RED}✗ 后端启动超时，查看日志: tail -f logs/backend.log${NC}"
    fi
done

# Start Frontend
echo -e "${YELLOW}▶ 启动前端 (Streamlit :8501)...${NC}"
python -m streamlit run "$PROJECT_DIR/frontend/app.py" \
    --server.port 8501 \
    --server.address 0.0.0.0 \
    --browser.gatherUsageStats false \
    --server.headless true > "$PROJECT_DIR/logs/frontend.log" 2>&1 &
FRONTEND_PID=$!
echo $FRONTEND_PID > "$FRONTEND_PID_FILE"
echo -e "${GREEN}✓ 前端 PID: $FRONTEND_PID${NC}"

# Start MCP Server
echo -e "${YELLOW}▶ 启动 MCP Server (stdio)...${NC}"
cd "$PROJECT_DIR"
python -m mcp_server.server --transport stdio > "$PROJECT_DIR/logs/mcp.log" 2>&1 &
MCP_PID=$!
echo $MCP_PID > "$MCP_PID_FILE"
echo -e "${GREEN}✓ MCP Server PID: $MCP_PID${NC}"

sleep 2

echo ""
echo "========================================"
echo -e "${GREEN}🎉 服务启动完成!${NC}"
echo ""
echo -e "  ${BLUE}📚 前端界面:${NC} http://localhost:8501"
echo -e "  ${BLUE}🔌 API 文档:${NC} http://localhost:8000/docs"
echo -e "  ${BLUE}💓 健康检查:${NC} http://localhost:8000/health"
echo ""
echo -e "${YELLOW}📋 管理命令:${NC}"
echo "  ./scripts/stop.sh      - 停止服务"
echo "  ./scripts/status.sh    - 查看状态"
echo "  tail -f logs/backend.log   - 后端日志"
echo "  tail -f logs/frontend.log - 前端日志"
echo "========================================"
