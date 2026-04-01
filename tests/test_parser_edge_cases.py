"""解析器边界情况测试 - 验证审查发现的解析问题

测试目标:
1. 大文件内存问题 (parser.py)
2. 编码检测缺失 (parser.py)
3. 分块策略问题 (parser.py)

注意: 这些测试使用模拟数据，验证问题存在。
"""

import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


class TestLargeFileHandling:
    """测试大文件处理问题"""
    
    def test_full_read_memory_issue(self):
        """测试一次性读取导致的内存问题"""
        
        # 模拟当前实现
        def parse_text_vulnerable(file_path: str, chunk_size: int = 8192):
            """有问题的实现 - 一次性读取"""
            with open(file_path, "r", encoding="utf-8", errors='ignore') as f:
                text = f.read()  # 一次性读取整个文件！
            return text
        
        # 模拟安全实现
        def parse_text_safe(file_path: str, chunk_size: int = 8192):
            """安全的实现 - 流式读取"""
            chunks = []
            with open(file_path, "r", encoding="utf-8", errors='ignore') as f:
                while True:
                    chunk = f.read(chunk_size)
                    if not chunk:
                        break
                    chunks.append(chunk)
            return ''.join(chunks)
        
        # 创建测试文件（模拟大文件）
        test_sizes = [
            ("1MB", 1024 * 1024),
            ("10MB", 10 * 1024 * 1024),
            ("100MB", 100 * 1024 * 1024),
        ]
        
        print("\n大文件内存使用测试:")
        print("  文件大小    |  脆弱方式内存  |  安全方式内存  |  比例")
        print("  " + "-" * 55)
        
        for name, size in test_sizes:
            # 脆弱方式：一次性读取
            # 内存使用 ≈ 文件大小 * 2（原始文件 + 字符串）
            vulnerable_memory = size * 2
            
            # 安全方式：流式读取
            # 内存使用 ≈ chunk_size * 2
            safe_memory = 8192 * 2
            
            ratio = vulnerable_memory / safe_memory if safe_memory > 0 else 0
            
            print(f"  {name:10} | {vulnerable_memory / (1024*1024):10.1f} MB | "
                  f"{safe_memory / 1024:10.1f} KB | {ratio:8.0f}x")
        
        print("\n  ⚠️ 警告: 脆弱方式处理 100MB 文件需要约 200MB 内存")
        print("          处理 1GB 文件需要约 2GB 内存！")
    
    def test_file_size_thresholds(self):
        """测试文件大小阈值"""
        
        thresholds = {
            "安全": 10 * 1024 * 1024,      # 10MB
            "警告": 100 * 1024 * 1024,     # 100MB
            "危险": 1024 * 1024 * 1024,    # 1GB
        }
        
        print("\n文件大小阈值建议:")
        for level, size in thresholds.items():
            mb = size / (1024 * 1024)
            print(f"  {level}: {mb:.0f} MB")
        
        print("\n  建议: 超过 100MB 的文件使用流式处理")


class TestEncodingDetection:
    """测试编码检测问题"""
    
    def test_encoding_scenarios(self):
        """测试各种编码场景"""
        
        test_cases = [
            ("UTF-8 无 BOM", "utf-8", b"Hello World \u4e2d\u6587"),
            ("UTF-8 带 BOM", "utf-8-sig", b'\xef\xbb\xbfHello World'),
            ("UTF-16 LE", "utf-16-le", b'\xff\xfeH\x00e\x00l\x00l\x00o\x00'),
            ("UTF-16 BE", "utf-16-be", b'\xfe\xff\x00H\x00e\x00l\x00l\x00o\x00'),
            ("GBK 中文", "gbk", "中文测试".encode("gbk")),
            ("Latin-1", "latin-1", b"caf\xe9"),  # café
        ]
        
        print("\n编码场景测试:")
        print("  场景               | 硬编码 UTF-8 结果")
        print("  " + "-" * 45)
        
        for name, actual_encoding, content in test_cases:
            # 模拟硬编码 UTF-8 读取
            try:
                decoded = content.decode("utf-8")
                status = "成功"
            except UnicodeDecodeError:
                decoded = content.decode("utf-8", errors="ignore")
                status = "失败（丢失数据）"
            
            correct = actual_encoding in ["utf-8", "utf-8-sig"]
            marker = "✓" if correct else "✗"
            
            print(f"  {name:18} | {marker} {status}")
        
        print("\n  ⚠️ 警告: 硬编码 UTF-8 会导致多种编码的文件乱码！")
    
    def test_bom_handling(self):
        """测试 BOM 处理"""
        
        bom_cases = [
            ("UTF-8", b'\xef\xbb\xbf'),
            ("UTF-16 LE", b'\xff\xfe'),
            ("UTF-16 BE", b'\xfe\xff'),
            ("UTF-32 LE", b'\xff\xfe\x00\x00'),
            ("UTF-32 BE", b'\x00\x00\xfe\xff'),
        ]
        
        print("\nBOM (字节顺序标记) 测试:")
        for name, bom in bom_cases:
            print(f"  {name}: {bom.hex()}")
        
        print("\n  建议: 读取文件前4字节检测 BOM，自动选择正确编码")
    
    def test_encoding_detection_solution(self):
        """测试编码检测解决方案"""
        
        def detect_encoding_mock(file_content: bytes) -> str:
            """模拟编码检测"""
            # 检查 BOM
            if file_content.startswith(b'\xef\xbb\xbf'):
                return 'utf-8-sig'
            elif file_content.startswith(b'\xff\xfe'):
                return 'utf-16-le'
            elif file_content.startswith(b'\xfe\xff'):
                return 'utf-16-be'
            
            # 模拟 chardet 检测
            # 实际实现应使用 chardet 库
            try:
                file_content.decode('utf-8')
                return 'utf-8'
            except UnicodeDecodeError:
                pass
            
            try:
                file_content.decode('gbk')
                return 'gbk'
            except UnicodeDecodeError:
                pass
            
            return 'latin-1'  # 保底编码
        
        test_contents = [
            ("UTF-8 英文", b"Hello World", "utf-8"),
            ("UTF-8 中文", "中文".encode("utf-8"), "utf-8"),
            ("UTF-8 BOM", b'\xef\xbb\xbfHello', "utf-8-sig"),
            ("GBK 中文", "中文".encode("gbk"), "gbk"),
        ]
        
        print("\n编码检测解决方案测试:")
        for name, content, expected in test_contents:
            detected = detect_encoding_mock(content)
            match = "✓" if detected == expected else "✗"
            print(f"  {match} {name}: 检测到 {detected} (期望 {expected})")


class TestChunkingStrategy:
    """测试分块策略问题"""
    
    def test_naive_overlap_issue(self):
        """测试简单字符串切片的重叠问题"""
        
        text = "This is a complete sentence about machine learning."
        overlap_size = 20
        
        # 脆弱实现：简单字符串切片
        naive_overlap = text[-overlap_size:]
        
        print("\n分块重叠策略测试:")
        print(f"  原文: {text}")
        print(f"  重叠大小: {overlap_size} 字符")
        print(f"  简单切片: '{naive_overlap}'")
        
        # 检查是否在单词中间切断
        first_space = naive_overlap.find(' ')
        last_space = naive_overlap.rfind(' ')
        
        if first_space == -1 or (last_space > 0 and naive_overlap[last_space+1:]):
            print("  ⚠️ 警告: 简单切片可能切断单词！")
            print(f"     当前切片以 '{naive_overlap.split()[0]}' 开头，可能不完整")
    
    def test_smart_overlap_solution(self):
        """测试智能重叠解决方案"""
        
        def get_overlap_text(text: str, overlap_size: int) -> str:
            """智能重叠：在句子边界处切割"""
            if len(text) <= overlap_size:
                return text
            
            target_pos = len(text) - overlap_size
            
            # 优先在句号、问号、感叹号后切割
            sentence_endings = '.。!?！?'
            for i in range(target_pos, len(text)):
                if text[i] in sentence_endings:
                    # 找到句子结束后的空格或换行
                    for j in range(i + 1, min(i + 3, len(text))):
                        if text[j] in ' \n':
                            return text[j + 1:].lstrip()
            
            # 其次在换行处切割
            newline_pos = text.rfind('\n', target_pos)
            if newline_pos != -1:
                return text[newline_pos + 1:]
            
            # 最后在空格处切割
            space_pos = text.rfind(' ', target_pos)
            if space_pos != -1:
                return text[space_pos + 1:]
            
            # 兜底：硬性切割
            return text[-overlap_size:]
        
        test_cases = [
            "First sentence ends here. Second sentence about AI.",
            "Line one\nLine two about ML\nLine three",
            "A very long word without breaks supercalifragilistic",
        ]
        
        print("\n智能重叠解决方案测试:")
        for text in test_cases:
            overlap = get_overlap_text(text, 20)
            print(f"  原文: {text[:40]}...")
            print(f"  重叠: '{overlap}'")
            
            # 检查是否以空格开头（不好的情况）
            if overlap.startswith(' '):
                print("     ⚠️ 以空格开头")
            else:
                print("     ✓ 在合适位置切割")
    
    def test_chunk_boundary_preservation(self):
        """测试分块边界保留"""
        
        paragraphs = [
            "Paragraph one about neural networks.",
            "Paragraph two about deep learning.",
            "Paragraph three about machine learning.",
        ]
        
        chunk_size = 50
        overlap = 20
        
        print("\n分块边界保留测试:")
        print(f"  段落数: {len(paragraphs)}")
        print(f"  目标块大小: {chunk_size}")
        print(f"  重叠: {overlap}")
        
        # 当前实现：简单拼接
        text = "\n".join(paragraphs)
        chunks = []
        current = ""
        
        for para in paragraphs:
            if len(current) + len(para) > chunk_size and current:
                chunks.append(current)
                current = para
            else:
                if current:
                    current += "\n"
                current += para
        
        if current:
            chunks.append(current)
        
        print(f"  生成块数: {len(chunks)}")
        for i, chunk in enumerate(chunks):
            print(f"    块 {i+1}: {chunk[:50]}...")


class TestPDFLayoutIssues:
    """测试 PDF 布局问题"""
    
    def test_multicolumn_layout(self):
        """测试多栏布局问题"""
        
        # 模拟双栏 PDF 的文本提取结果
        # 当前实现会交错提取左右栏
        multicolumn_text = """
左栏第一段内容关于机左栏第二段内容关于深
器学习的基础知识。度学习的应用场景。

左栏第三段继续内容。左栏第四段结束。
        """
        
        print("\nPDF 多栏布局测试:")
        print("  模拟双栏 PDF 提取结果:")
        for line in multicolumn_text.strip().split('\n')[:5]:
            print(f"    {line}")
        
        print("\n  ⚠️ 警告: 简单提取会导致左右栏文本交错，语义混乱！")
        print("  建议: 使用 pdfplumber 的 words 提取 + 布局分析")
    
    def test_table_extraction(self):
        """测试表格提取问题"""
        
        # 模拟表格数据
        table_data = [
            ["Name", "Age", "City"],
            ["Alice", "25", "Beijing"],
            ["Bob", "30", "Shanghai"],
        ]
        
        # 当前实现：表格变成混乱文本
        naive_extraction = " ".join([" ".join(row) for row in table_data])
        
        # 期望实现：保留表格结构
        structured_extraction = "\n".join([" | ".join(row) for row in table_data])
        
        print("\nPDF 表格提取测试:")
        print("  原始表格:")
        for row in table_data:
            print(f"    {row}")
        
        print(f"\n  当前实现结果: '{naive_extraction}'")
        print(f"  期望实现结果:\n{structured_extraction}")


if __name__ == "__main__":
    print("=" * 60)
    print("解析器边界情况测试套件")
    print("=" * 60)
    
    test_classes = [
        TestLargeFileHandling(),
        TestEncodingDetection(),
        TestChunkingStrategy(),
        TestPDFLayoutIssues(),
    ]
    
    for test_class in test_classes:
        print(f"\n{'='*60}")
        print(f"测试类: {test_class.__class__.__name__}")
        print('='*60)
        
        for method_name in dir(test_class):
            if method_name.startswith("test_"):
                print(f"\n--- {method_name} ---")
                try:
                    getattr(test_class, method_name)()
                except Exception as e:
                    print(f"✗ 错误: {e}")
    
    print("\n" + "=" * 60)
    print("测试完成")
    print("=" * 60)
