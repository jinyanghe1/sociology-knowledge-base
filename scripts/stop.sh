#!/bin/bash
# AI Knowledge Base - 一键停止脚本
# Usage: ./scripts/stop.sh

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
BACKEND_PID_FILE="$PROJECT_DIR/.agentstalk/backend.pid"
FRONTEND_PID_FILE="$PROJECT_DIR/.agentstalk/frontend.pid"

echo -e "${BLUE}🛑 AI Knowledge Base 停止脚本${NC}"
echo "========================================"

stop_service() {
    local name=$1
    local pid_file=$2
    
    if [ -f "$pid_file" ]; then
        PID=$(cat "$pid_file")
        if ps -p "$PID" > /dev/null 2>&1; then
            echo -e "${YELLOW}▶ 停止 $name (PID: $PID)...${NC}"
            kill "$PID" 2>/dev/null || true
            
            # Wait for process to stop
            for i in {1..10}; do
                if ! ps -p "$PID" > /dev/null 2>&1; then
                    break
                fi
                sleep 0.5
            done
            
            # Force kill if still running
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
}

# Find and kill any remaining processes on ports
echo -e "${YELLOW}▶ 检查端口占用...${NC}"

# Kill processes on port 8000 (backend)
BACKEND_PIDS=$(lsof -ti:8000 2>/dev/null || netstat -vanp tcp 2>/dev/null | grep 8000 | awk '{print $9}' | cut -d'/' -f1 | grep -v "-" || true)
if [ -n "$BACKEND_PIDS" ]; then
    echo -e "${YELLOW}▶ 清理后端端口 8000...${NC}"
    echo "$BACKEND_PIDS" | xargs kill -9 2>/dev/null || true
fi

# Kill processes on port 8501 (frontend)
FRONTEND_PIDS=$(lsof -ti:8501 2>/dev/null || netstat -vanp tcp 2>/dev/null | grep 8501 | awk '{print $9}' | cut -d'/' -f1 | grep -v "-" || true)
if [ -n "$FRONTEND_PIDS" ]; then
    echo -e "${YELLOW}▶ 清理前端端口 8501...${NC}"
    echo "$FRONTEND_PIDS" | xargs kill -9 2>/dev/null || true
fi

# Stop by PID files
stop_service "后端服务" "$BACKEND_PID_FILE"
stop_service "前端服务" "$FRONTEND_PID_FILE"

echo ""
echo -e "${GREEN}✅ 所有服务已停止${NC}"
echo "========================================"
