#!/usr/bin/env python3
"""测试运行脚本 - 一键运行所有审查测试

使用方法:
    python tests/run_all_tests.py
    
选项:
    --security    仅运行安全测试
    --concurrency 仅运行并发测试
    --parser      仅运行解析器测试
    --mcp         仅运行 MCP 事务测试
    --all         运行所有测试（默认）
"""

import sys
import argparse
from pathlib import Path

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent))


def run_security_tests():
    """运行安全测试"""
    print("\n" + "="*70)
    print("安全漏洞测试")
    print("="*70)
    
    from test_security import (
        TestPathTraversal,
        TestFileSizeLimit,
        TestPromptInjection,
        TestDocumentStoreSecurity,
    )
    
    test_classes = [
        TestPathTraversal(),
        TestFileSizeLimit(),
        TestPromptInjection(),
        TestDocumentStoreSecurity(),
    ]
    
    return run_test_classes(test_classes)


def run_concurrency_tests():
    """运行并发测试"""
    print("\n" + "="*70)
    print("并发问题测试")
    print("="*70)
    
    from test_concurrency import (
        TestEmbeddingCacheConcurrency,
        TestDocMetaConcurrency,
        TestFallbackStoreConcurrency,
        TestCacheKeyCollision,
    )
    
    test_classes = [
        TestEmbeddingCacheConcurrency(),
        TestDocMetaConcurrency(),
        TestFallbackStoreConcurrency(),
        TestCacheKeyCollision(),
    ]
    
    return run_test_classes(test_classes)


def run_parser_tests():
    """运行解析器测试"""
    print("\n" + "="*70)
    print("解析器边界情况测试")
    print("="*70)
    
    from test_parser_edge_cases import (
        TestLargeFileHandling,
        TestEncodingDetection,
        TestChunkingStrategy,
        TestPDFLayoutIssues,
    )
    
    test_classes = [
        TestLargeFileHandling(),
        TestEncodingDetection(),
        TestChunkingStrategy(),
        TestPDFLayoutIssues(),
    ]
    
    return run_test_classes(test_classes)


def run_mcp_tests():
    """运行 MCP 事务测试"""
    print("\n" + "="*70)
    print("MCP 事务测试")
    print("="*70)
    
    from test_mcp_transactions import (
        TestIndexingTransaction,
        TestDeletionTransaction,
        TestJSONPersistence,
        TestConcurrentModification,
    )
    
    test_classes = [
        TestIndexingTransaction(),
        TestDeletionTransaction(),
        TestJSONPersistence(),
        TestConcurrentModification(),
    ]
    
    return run_test_classes(test_classes)


def run_test_classes(test_classes):
    """运行测试类列表"""
    total_tests = 0
    passed_tests = 0
    failed_tests = 0
    
    for test_class in test_classes:
        print(f"\n{'-'*70}")
        print(f"测试类: {test_class.__class__.__name__}")
        print('-'*70)
        
        for method_name in dir(test_class):
            if method_name.startswith("test_"):
                total_tests += 1
                print(f"\n  [{total_tests}] {method_name}")
                try:
                    getattr(test_class, method_name)()
                    print("    ✓ 通过")
                    passed_tests += 1
                except AssertionError as e:
                    print(f"    ✗ 断言失败: {e}")
                    failed_tests += 1
                except Exception as e:
                    print(f"    ✗ 错误: {e}")
                    failed_tests += 1
    
    return total_tests, passed_tests, failed_tests


def print_summary(results):
    """打印测试摘要"""
    total = sum(r[0] for r in results.values())
    passed = sum(r[1] for r in results.values())
    failed = sum(r[2] for r in results.values())
    
    print("\n" + "="*70)
    print("测试摘要")
    print("="*70)
    
    for name, (t, p, f) in results.items():
        status = "✓" if f == 0 else "✗"
        print(f"  {status} {name:20} | 总计: {t:3} | 通过: {p:3} | 失败: {f:3}")
    
    print("-"*70)
    print(f"  总计: {total:3} | 通过: {passed:3} | 失败: {failed:3}")
    
    if failed == 0:
        print("\n  ✓ 所有测试通过！")
    else:
        print(f"\n  ✗ {failed} 个测试失败，请查看详细报告")
    
    print("="*70)
    
    return failed == 0


def main():
    parser = argparse.ArgumentParser(description="运行 AI Knowledge Base 审查测试")
    parser.add_argument("--security", action="store_true", help="仅运行安全测试")
    parser.add_argument("--concurrency", action="store_true", help="仅运行并发测试")
    parser.add_argument("--parser", action="store_true", help="仅运行解析器测试")
    parser.add_argument("--mcp", action="store_true", help="仅运行 MCP 测试")
    parser.add_argument("--all", action="store_true", help="运行所有测试（默认）")
    
    args = parser.parse_args()
    
    # 如果没有指定，默认运行所有
    if not any([args.security, args.concurrency, args.parser, args.mcp]):
        args.all = True
    
    results = {}
    
    print("="*70)
    print("AI Knowledge Base - 架构审查测试套件")
    print("="*70)
    print("\n说明: 这些测试验证代码审查发现的问题，不修复问题")
    print("      生产代码零修改，仅生成测试报告")
    
    if args.all or args.security:
        results["安全测试"] = run_security_tests()
    
    if args.all or args.concurrency:
        results["并发测试"] = run_concurrency_tests()
    
    if args.all or args.parser:
        results["解析器测试"] = run_parser_tests()
    
    if args.all or args.mcp:
        results["MCP事务测试"] = run_mcp_tests()
    
    success = print_summary(results)
    
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
