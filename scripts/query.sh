#!/bin/bash
# AI Knowledge Base CLI - 命令行查询
# Usage: ./scripts/query.sh "你的问题"

set -e

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
API_URL="${API_URL:-http://localhost:8000}"

if [ -z "$1" ]; then
    echo "Usage: ./scripts/query.sh \"你的问题\" [top_k]"
    echo ""
    echo "Example:"
    echo "  ./scripts/query.sh \"福柯的身体观\""
    echo "  ./scripts/query.sh \"后现代社会学\" 3"
    exit 1
fi

QUESTION="$1"
TOP_K="${2:-5}"

curl -s -X POST "$API_URL/api/query" \
    -H "Content-Type: application/json" \
    -d "{\"question\": \"$QUESTION\", \"top_k\": $TOP_K}"
