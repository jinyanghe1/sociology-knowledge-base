#!/bin/bash
# AI Knowledge Base - 状态检查脚本
# Usage: ./scripts/status.sh

BLUE='\033[0;34m'
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
BACKEND_PID_FILE="$PROJECT_DIR/.agentstalk/backend.pid"
FRONTEND_PID_FILE="$PROJECT_DIR/.agentstalk/frontend.pid"

echo -e "${BLUE}📊 AI Knowledge Base 状态检查${NC}"
echo "========================================"

check_service() {
    local name=$1
    local pid_file=$2
    local port=$3
    
    echo -e "${BLUE}$name:${NC}"
    
    # Check PID file
    if [ -f "$pid_file" ]; then
        PID=$(cat "$pid_file")
        if ps -p "$PID" > /dev/null 2>&1; then
            echo -e "  ${GREEN}● 运行中 (PID: $PID)${NC}"
        else
            echo -e "  ${RED}● 未运行 (PID 文件存在但进程不存在)${NC}"
        fi
    else
        echo -e "  ${RED}● 未运行 (无 PID 文件)${NC}"
    fi
    
    # Check port
    if lsof -Pi :$port -sTCP:LISTEN -t > /dev/null 2>&1; then
        echo -e "  ${GREEN}● 端口 $port 监听中${NC}"
    else
        echo -e "  ${RED}● 端口 $port 未监听${NC}"
    fi
}

check_service "后端服务" "$BACKEND_PID_FILE" 8000
check_service "前端服务" "$FRONTEND_PID_FILE" 8501

echo ""
echo -e "${BLUE}健康检查:${NC}"
if curl -s http://localhost:8000/health > /dev/null 2>&1; then
    echo -e "  ${GREEN}✓ 后端 API 响应正常${NC}"
else
    echo -e "  ${RED}✗ 后端 API 无响应${NC}"
fi

echo ""
echo -e "${BLUE}数据目录:${NC}"
echo "  上传目录: $PROJECT_DIR/uploads"
echo "  向量数据库: $PROJECT_DIR/data/chroma"
echo "  日志目录: $PROJECT_DIR/logs"

# Document count
if [ -d "$PROJECT_DIR/data/chroma" ]; then
    echo ""
    echo -e "${BLUE}文档统计:${NC}"
    DOC_COUNT=$(find "$PROJECT_DIR/uploads" -type f 2>/dev/null | wc -l)
    echo "  已上传文件: $DOC_COUNT"
fi

echo "========================================"
