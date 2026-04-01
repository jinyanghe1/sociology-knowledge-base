#!/usr/bin/env python3
"""Knowledge Base CLI - 查询已索引的社会学知识库

Usage:
    python scripts/kb_query.py "你的问题"
    python scripts/kb_query.py "福柯的身体观" --top 5
"""

import argparse
import json
import sys
import urllib.request
import urllib.error

API_URL = "http://localhost:8000"


def query(question: str, top_k: int = 5) -> dict:
    """Query the knowledge base."""
    req = urllib.request.Request(
        f"{API_URL}/api/query",
        data=json.dumps({"question": question, "top_k": top_k}).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST"
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read())


def main():
    parser = argparse.ArgumentParser(description="查询社会学知识库")
    parser.add_argument("question", help="要查询的问题")
    parser.add_argument("--top", "-k", type=int, default=5, help="返回结果数量 (默认: 5)")
    args = parser.parse_args()

    try:
        result = query(args.question, args.top)
        sources = result.get("sources", [])

        print(f"\n📚 知识库查询结果")
        print(f"问题: {result.get('question', args.question)}")
        print(f"找到 {len(sources)} 个相关片段:\n")

        for i, src in enumerate(sources, 1):
            score = src.get("score", 0)
            content = src.get("content", "")[:400].replace("\n", " ").strip()
            print(f"[{i}] 相似度: {score:.3f}")
            print(f"    {content}...")
            print()

    except urllib.error.URLError as e:
        print(f"❌ 连接失败: {e}", file=sys.stderr)
        print("💡 提示: 确保后端服务正在运行 (./scripts/start.sh)", file=sys.stderr)
        sys.exit(1)
    except json.JSONDecodeError:
        print("❌ 响应解析失败", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
