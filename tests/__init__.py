"""AI Knowledge Base 测试套件

本测试套件用于验证代码审查发现的问题，不修改生产代码。

测试文件说明:
- test_security.py: 安全漏洞测试（路径遍历、文件大小限制、提示词注入）
- test_concurrency.py: 并发问题测试（线程安全、竞态条件、缓存冲突）
- test_parser_edge_cases.py: 解析器边界情况测试（大文件、编码、分块）
- test_mcp_transactions.py: MCP 事务测试（原子性、回滚、持久化）

运行方式:
    cd /Users/hejinyang/Desktop/社会学考研资料
    python -m pytest tests/ -v
    # 或
    python tests/test_security.py
    python tests/test_concurrency.py
    python tests/test_parser_edge_cases.py
    python tests/test_mcp_transactions.py

注意:
- 这些测试仅验证问题存在，不修复问题
- 并发测试可能需要多次运行才能触发问题
- 部分测试使用模拟数据，不涉及真实文件系统操作
"""

__version__ = "1.0.0"
__author__ = "Architecture Review Team"
