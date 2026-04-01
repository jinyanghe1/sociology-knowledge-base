#!/bin/bash
# AI Knowledge Base - 一键停止脚本
# Usage: ./scripts/stop.sh

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
BACKEND_PID_FILE="$PROJECT_DIR/.agentstalk/backend.pid"
FRONTEND_PID_FILE="$PROJECT_DIR/.agentstalk/frontend.pid"
MCP_PID_FILE="$PROJECT_DIR/.agentstalk/mcp.pid"

echo -e "${BLUE}🛑 AI Knowledge Base 停止脚本${NC}"
echo "========================================"

stop_service() {
    local name=$1
    local pid_file=$2
    local port=$3

    if [ -f "$pid_file" ]; then
        PID=$(cat "$pid_file")
        if ps -p "$PID" > /dev/null 2>&1; then
            echo -e "${YELLOW}▶ 停止 $name (PID: $PID)...${NC}"
            kill "$PID" 2>/dev/null || true
            for i in {1..10}; do
                if ! ps -p "$PID" > /dev/null 2>&1; then
                    break
                fi
                sleep 0.3
            done
            if ps -p "$PID" > /dev/null 2>&1; then
                kill -9 "$PID" 2>/dev/null || true
            fi
            echo -e "${GREEN}✓ $name 已停止${NC}"
        else
            echo -e "${YELLOW}⚠ $name 进程不存在${NC}"
        fi
        rm -f "$pid_file"
    else
        echo -e "${YELLOW}⚠ $name PID 文件不存在${NC}"
    fi

    # Also kill by port
    if [ -n "$port" ]; then
        PORT_PIDS=$(lsof -ti:$port 2>/dev/null || true)
        if [ -n "$PORT_PIDS" ]; then
            echo -e "${YELLOW}▶ 清理端口 $port...${NC}"
            echo "$PORT_PIDS" | xargs kill -9 2>/dev/null || true
        fi
    fi
}

stop_service "后端服务" "$BACKEND_PID_FILE" 8000
stop_service "前端服务" "$FRONTEND_PID_FILE" 8501
stop_service "MCP Server" "$MCP_PID_FILE" ""

echo ""
echo -e "${GREEN}✅ 所有服务已停止${NC}"
echo "========================================"
