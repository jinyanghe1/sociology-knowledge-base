#!/bin/bash
# AI Knowledge Base - 一键启动脚本
# Usage: ./scripts/start.sh

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
BACKEND_PID_FILE="$PROJECT_DIR/.agentstalk/backend.pid"
FRONTEND_PID_FILE="$PROJECT_DIR/.agentstalk/frontend.pid"

echo -e "${BLUE}🚀 AI Knowledge Base 启动脚本${NC}"
echo "========================================"

# Check Python
echo -e "${YELLOW}▶ 检查 Python 环境...${NC}"
if ! command -v python3 &> /dev/null; then
    echo -e "${RED}✗ Python3 未安装${NC}"
    exit 1
fi
echo -e "${GREEN}✓ Python3: $(python3 --version)${NC}"

# Check/Create virtual environment
VENV_DIR="$PROJECT_DIR/.venv"
if [ ! -d "$VENV_DIR" ]; then
    echo -e "${YELLOW}▶ 创建虚拟环境...${NC}"
    python3 -m venv "$VENV_DIR"
fi

source "$VENV_DIR/bin/activate"
echo -e "${GREEN}✓ 虚拟环境已激活${NC}"

# Install dependencies
echo -e "${YELLOW}▶ 安装依赖...${NC}"
pip install -q -r "$PROJECT_DIR/requirements.txt"
echo -e "${GREEN}✓ 依赖安装完成${NC}"

# Cleanup old PID files
rm -f "$BACKEND_PID_FILE" "$FRONTEND_PID_FILE"

# Create necessary directories
mkdir -p "$PROJECT_DIR/uploads" "$PROJECT_DIR/data/chroma" "$PROJECT_DIR/.agentstalk"

# Start Backend
echo -e "${YELLOW}▶ 启动后端服务 (FastAPI)...${NC}"
cd "$PROJECT_DIR"
python3 -m uvicorn backend.main:app \
    --host 0.0.0.0 \
    --port 8000 \
    --reload \
    --log-level info > "$PROJECT_DIR/logs/backend.log" 2>&1 &
BACKEND_PID=$!
echo $BACKEND_PID > "$BACKEND_PID_FILE"
echo -e "${GREEN}✓ 后端已启动 (PID: $BACKEND_PID, Port: 8000)${NC}"

# Wait for backend to be ready
echo -e "${YELLOW}▶ 等待后端就绪...${NC}"
for i in {1..30}; do
    if curl -s http://localhost:8000/health > /dev/null 2>&1; then
        echo -e "${GREEN}✓ 后端服务已就绪${NC}"
        break
    fi
    sleep 0.5
    if [ $i -eq 30 ]; then
        echo -e "${RED}✗ 后端启动超时${NC}"
        exit 1
    fi
done

# Start Frontend
echo -e "${YELLOW}▶ 启动前端服务 (Streamlit)...${NC}"
cd "$PROJECT_DIR"
streamlit run frontend/app.py \
    --server.port 8501 \
    --server.address 0.0.0.0 \
    --browser.serverAddress localhost \
    --server.headless false > "$PROJECT_DIR/logs/frontend.log" 2>&1 &
FRONTEND_PID=$!
echo $FRONTEND_PID > "$FRONTEND_PID_FILE"
echo -e "${GREEN}✓ 前端已启动 (PID: $FRONTEND_PID, Port: 8501)${NC}"

# Wait for frontend
echo -e "${YELLOW}▶ 等待前端就绪...${NC}"
sleep 3

echo ""
echo "========================================"
echo -e "${GREEN}🎉 服务启动完成!${NC}"
echo ""
echo -e "  ${BLUE}📚 前端界面:${NC} http://localhost:8501"
echo -e "  ${BLUE}🔌 API 文档:${NC} http://localhost:8000/docs"
echo -e "  ${BLUE}💓 健康检查:${NC} http://localhost:8000/health"
echo ""
echo -e "${YELLOW}📋 管理命令:${NC}"
echo "  ./scripts/stop.sh     - 停止服务"
echo "  ./scripts/status.sh   - 查看状态"
echo "  tail -f logs/backend.log   - 查看后端日志"
echo "  tail -f logs/frontend.log  - 查看前端日志"
echo ""
echo -e "${YELLOW}⚠️  按 Ctrl+C 或运行 ./scripts/stop.sh 停止服务${NC}"
echo "========================================"

# Keep script running
trap 'echo -e "\n${YELLOW}收到中断信号，正在停止服务...${NC}"; ./scripts/stop.sh; exit 0' INT
wait
