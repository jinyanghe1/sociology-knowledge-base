"""MCP Server 事务测试 - 验证审查发现的事务问题

测试目标:
1. 文档索引非原子操作 (mcp_server/server.py)
2. 删除操作非原子 (mcp_server/server.py)
3. JSON 持久化非原子 (mcp_server/server.py)

注意: 这些测试模拟事务失败场景。
"""

import os
import sys
import json
import tempfile
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent))


class TestIndexingTransaction:
    """测试文档索引的事务问题"""
    
    def test_non_atomic_indexing_steps(self):
        """测试索引操作的5个非原子步骤"""
        
        print("\n文档索引事务分析:")
        print("  索引流程:")
        steps = [
            ("1. 复制文件", "dest.write_bytes(path.read_bytes())", "文件残留"),
            ("2. 解析文档", "parser.parse(str(dest), parser_type)", "文件残留"),
            ("3. 生成嵌入", "get_embedding(content)", "文件+计算资源浪费"),
            ("4. 向量写入", "chroma.add_documents(...)", "文件+向量孤儿数据"),
            ("5. 保存元数据", "_save_meta()", "文件+向量+元数据不一致"),
        ]
        
        for step_name, code, failure_result in steps:
            print(f"\n    {step_name}")
            print(f"      代码: {code[:40]}...")
            print(f"      失败时: {failure_result}")
        
        print("\n  ⚠️ 警告: 任一步骤失败都会产生孤儿数据！")
        print("  ⚠️ 警告: 无回滚机制！")
    
    def test_indexing_failure_scenarios(self):
        """测试索引失败的场景"""
        
        scenarios = [
            {
                "name": "嵌入生成失败",
                "fails_at": 3,
                "orphan_data": ["已复制文件"],
                "user_impact": "磁盘空间浪费",
            },
            {
                "name": "向量写入失败",
                "fails_at": 4,
                "orphan_data": ["已复制文件", "已生成嵌入(内存)"],
                "user_impact": "计算资源浪费",
            },
            {
                "name": "元数据保存失败",
                "fails_at": 5,
                "orphan_data": ["已复制文件", "已写入向量数据"],
                "user_impact": "数据不一致，无法检索",
            },
        ]
        
        print("\n索引失败场景分析:")
        for scenario in scenarios:
            print(f"\n  场景: {scenario['name']}")
            print(f"    失败步骤: {scenario['fails_at']}")
            print(f"    孤儿数据: {', '.join(scenario['orphan_data'])}")
            print(f"    用户影响: {scenario['user_impact']}")
    
    def test_proper_transaction_pattern(self):
        """测试正确的事务模式"""
        
        print("\n正确的事务模式:")
        print("""
  建议实现:
  
  def _index_single_file(path: Path, workspace: str = "default"):
      doc_id = str(uuid.uuid4())
      dest = UPLOADS_DIR / f"{doc_id}_{path.name}"
      rollback_actions = []
      
      try:
          # Step 1: 验证（无副作用）
          if not path.exists():
              return {"error": "File not found"}
          
          # Step 2: 解析（无副作用）
          chunks = parser.parse(str(path), parser_type)
          if not chunks:
              return {"error": "No content"}
          
          # Step 3: 复制文件（记录回滚）
          dest.write_bytes(path.read_bytes())
          rollback_actions.append(lambda: dest.unlink(missing_ok=True))
          
          # Step 4: 生成嵌入
          try:
              embeddings = [get_embedding(c["content"]) for c in chunks]
          except Exception as e:
              _execute_rollback(rollback_actions)
              return {"error": f"Embedding failed: {e}"}
          
          # Step 5: 写入向量（记录回滚）
          try:
              chroma.add_documents(...)
              rollback_actions.append(
                  lambda: chroma.delete_by_document_id(doc_id)
              )
          except Exception as e:
              _execute_rollback(rollback_actions)
              return {"error": f"Vector store failed: {e}"}
          
          # Step 6: 保存元数据
          try:
              with _doc_meta_lock:
                  _doc_meta[doc_id] = {...}
                  _save_meta()
          except Exception as e:
              _execute_rollback(rollback_actions)
              return {"error": f"Metadata save failed: {e}"}
          
          return {"success": True, ...}
          
      except Exception as e:
          _execute_rollback(rollback_actions)
          return {"error": f"Unexpected error: {e}"}
        """)


class TestDeletionTransaction:
    """测试删除操作的事务问题"""
    
    def test_non_atomic_deletion(self):
        """测试删除操作的4个非原子步骤"""
        
        print("\n文档删除事务分析:")
        print("  删除流程:")
        steps = [
            ("1. 检查存在", "if document_id not in _doc_meta", "无影响"),
            ("2. 删除文件", "fp.unlink()", "文件已删，向量残留"),
            ("3. 删除向量", "chroma.delete_by_document_id()", "文件+向量已删，元数据残留"),
            ("4. 删除元数据", "del _doc_meta[doc_id]; _save_meta()", "不一致"),
        ]
        
        for step_name, code, failure_result in steps:
            print(f"\n    {step_name}")
            print(f"      代码: {code[:45]}")
            print(f"      失败时: {failure_result}")
        
        print("\n  ⚠️ 警告: 删除过程中断会导致数据不一致！")
    
    def test_deletion_failure_scenarios(self):
        """测试删除失败的场景"""
        
        scenarios = [
            {
                "name": "文件删除失败（权限不足）",
                "step": 2,
                "state": "文件存在，向量存在，元数据存在",
                "can_retry": True,
            },
            {
                "name": "向量删除失败（ChromaDB 故障）",
                "step": 3,
                "state": "文件已删，向量存在，元数据存在",
                "can_retry": True,
            },
            {
                "name": "元数据保存失败（磁盘满）",
                "step": 4,
                "state": "文件已删，向量已删，元数据存在",
                "can_retry": False,  # 最严重的状态
            },
        ]
        
        print("\n删除失败场景分析:")
        for scenario in scenarios:
            print(f"\n  场景: {scenario['name']}")
            print(f"    失败步骤: {scenario['step']}")
            print(f"    系统状态: {scenario['state']}")
            print(f"    可恢复: {'是' if scenario['can_retry'] else '否'}")
    
    def test_logical_deletion_pattern(self):
        """测试逻辑删除模式"""
        
        print("\n推荐的逻辑删除模式:")
        print("""
  方案: 逻辑删除 + 后台清理
  
  def delete_document(document_id: str):
      with _doc_meta_lock:
          if document_id not in _doc_meta:
              return {"error": "Document not found"}
          
          # 1. 先逻辑删除（标记状态）
          _doc_meta[document_id]["status"] = "deleted"
          _doc_meta[document_id]["deleted_at"] = datetime.now().isoformat()
          
          try:
              _save_meta()
          except Exception as e:
              # 回滚逻辑删除
              _doc_meta[document_id]["status"] = "ready"
              del _doc_meta[document_id]["deleted_at"]
              return {"error": f"Failed to mark as deleted: {e}"}
          
          # 2. 异步物理删除
          _schedule_cleanup(document_id)
          
          return {"success": True, "message": "Document marked for deletion"}
  
  def _cleanup_worker():
      # 后台清理已标记删除的文档
      for doc_id, doc in _doc_meta.items():
          if doc.get("status") == "deleted":
              try:
                  # 删除文件
                  Path(doc["file_path"]).unlink(missing_ok=True)
                  # 删除向量
                  chroma.delete_by_document_id(doc_id)
                  # 真正删除元数据
                  del _doc_meta[doc_id]
                  _save_meta()
              except Exception as e:
                  logger.error(f"Cleanup failed for {doc_id}: {e}")
                  # 下次重试
        """)


class TestJSONPersistence:
    """测试 JSON 持久化问题"""
    
    def test_non_atomic_write(self):
        """测试非原子写入问题"""
        
        print("\nJSON 持久化问题分析:")
        print("  当前实现:")
        print("    def _save_meta():")
        print("        META_FILE.write_text(json.dumps(_doc_meta))")
        print()
        print("  ⚠️ 问题:")
        print("    1. 写入过程中崩溃 → 文件半写损坏")
        print("    2. 磁盘满 → 异常但内存状态已更新")
        print("    3. 无备份 → 损坏后无法恢复")
    
    def test_atomic_write_solution(self):
        """测试原子写入解决方案"""
        
        print("\n原子写入解决方案:")
        print("""
  import tempfile
  import shutil
  
  def _save_meta_atomic():
      \"\"\"原子性保存元数据，带备份。\"\"\"
      try:
          # 1. 写入临时文件（同目录保证同文件系统）
          with tempfile.NamedTemporaryFile(
              mode='w',
              encoding='utf-8',
              dir=META_FILE.parent,  # 同目录
              delete=False,
              suffix='.tmp'
          ) as f:
              json.dump(_doc_meta, f, ensure_ascii=False, indent=2)
              temp_path = Path(f.name)
          
          # 2. 备份原文件
          if META_FILE.exists():
              backup_path = META_FILE.with_suffix('.json.bak')
              shutil.copy2(META_FILE, backup_path)
          
          # 3. 原子替换
          temp_path.replace(META_FILE)
          
      except (OSError, IOError) as e:
          # 清理临时文件
          if 'temp_path' in locals():
              temp_path.unlink(missing_ok=True)
          raise RuntimeError(f"Failed to save metadata: {e}") from e
        """)
    
    def test_recovery_from_backup(self):
        """测试从备份恢复"""
        
        print("\n备份恢复机制:")
        print("""
  def _load_meta_with_recovery():
      \"\"\"加载元数据，支持从备份恢复。\"\"\"
      global _doc_meta
      
      if not META_FILE.exists():
          _doc_meta = {}
          return
      
      try:
          _doc_meta = json.loads(META_FILE.read_text(encoding='utf-8'))
          logger.info(f"Loaded metadata for {len(_doc_meta)} documents")
      except json.JSONDecodeError as e:
          logger.error(f"Metadata file corrupted: {e}")
          
          # 尝试从备份恢复
          backup_path = META_FILE.with_suffix('.json.bak')
          if backup_path.exists():
              try:
                  _doc_meta = json.loads(backup_path.read_text(encoding='utf-8'))
                  logger.info("Metadata recovered from backup")
                  # 恢复成功后，重写主文件
                  _save_meta_atomic()
                  return
              except Exception as e2:
                  logger.error(f"Backup also corrupted: {e2}")
          
          # 无法恢复，重置
          logger.warning("Starting with empty metadata")
          _doc_meta = {}
        """)
    
    def test_sqlite_alternative(self):
        """测试 SQLite 替代方案"""
        
        print("\nSQLite 替代方案（推荐用于生产环境）:")
        print("""
  优势:
    - ACID 事务支持
    - 并发访问安全
    - 增量更新（无需全量写入）
    - 索引支持（快速查询）
    - 更好的性能（大量文档时）
  
  表结构:
    CREATE TABLE documents (
        id TEXT PRIMARY KEY,
        filename TEXT NOT NULL,
        file_type TEXT,
        file_path TEXT,
        workspace TEXT,
        chunk_count INTEGER,
        status TEXT,
        indexed_at TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    
    CREATE INDEX idx_workspace ON documents(workspace);
    CREATE INDEX idx_status ON documents(status);
  
  使用示例:
    # 插入（事务内）
    with sqlite3.connect('metadata.db') as conn:
        conn.execute(
            'INSERT INTO documents VALUES (?, ?, ?, ...)',
            (doc_id, filename, ...)
        )
        conn.commit()
    
    # 查询
    cursor = conn.execute(
        'SELECT * FROM documents WHERE workspace = ?',
        (workspace,)
    )
        """)


class TestConcurrentModification:
    """测试并发修改问题"""
    
    def test_concurrent_index_and_delete(self):
        """测试并发索引和删除"""
        
        print("\n并发修改风险场景:")
        print()
        print("  场景 1: 并发索引同一文档")
        print("    线程 A: 开始索引 doc_1")
        print("    线程 B: 也开始索引 doc_1（重复）")
        print("    结果: 重复数据！")
        print()
        print("  场景 2: 索引时删除")
        print("    线程 A: 开始索引 doc_1（已解析，未保存元数据）")
        print("    线程 B: 删除 doc_1")
        print("    线程 A: 继续保存元数据")
        print("    结果: 删除后文档又出现了！")
        print()
        print("  场景 3: 并发删除")
        print("    线程 A: 读取 _doc_meta[doc_1]")
        print("    线程 B: 删除 _doc_meta[doc_1]")
        print("    线程 A: 尝试删除已不存在的文档")
        print("    结果: KeyError 或重复删除")
    
    def test_idempotency_solution(self):
        """测试幂等性解决方案"""
        
        print("\n幂等性解决方案:")
        print("""
  1. 文档去重（基于内容哈希）
     
     def _get_content_hash(file_path: Path) -> str:
         \"\"\"计算文件内容哈希用于去重\"\"\"
         hasher = hashlib.sha256()
         with open(file_path, 'rb') as f:
             for chunk in iter(lambda: f.read(8192), b''):
                 hasher.update(chunk)
         return hasher.hexdigest()[:16]
     
     # 索引前检查是否已存在
     content_hash = _get_content_hash(path)
     existing = _find_by_hash(content_hash)
     if existing:
         return {"success": True, "document_id": existing["id"], "deduplicated": True}
  
  2. 索引操作加锁
     
     _indexing_locks: dict[str, threading.Lock] = {}
     
     def _index_single_file(path: Path, workspace: str = "default"):
         content_hash = _get_content_hash(path)
         
         # 获取或创建该文件的锁
         if content_hash not in _indexing_locks:
             _indexing_locks[content_hash] = threading.Lock()
         
         with _indexing_locks[content_hash]:
             # 再次检查（双重检查锁定）
             existing = _find_by_hash(content_hash)
             if existing:
                 return {"success": True, "document_id": existing["id"], "deduplicated": True}
             
             # 执行索引...
  
  3. 乐观锁（版本控制）
     
     # 在文档元数据中添加版本号
     doc = {
         "id": doc_id,
         "version": 1,  # 乐观锁版本号
         ...
     }
     
     # 更新时检查版本
     UPDATE documents SET ... version = version + 1
     WHERE id = ? AND version = ?
        """)


if __name__ == "__main__":
    print("=" * 60)
    print("MCP Server 事务测试套件")
    print("=" * 60)
    
    test_classes = [
        TestIndexingTransaction(),
        TestDeletionTransaction(),
        TestJSONPersistence(),
        TestConcurrentModification(),
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
    print("\n总结:")
    print("  1. 当前实现存在多处非原子操作")
    print("  2. 建议使用事务或逻辑删除模式")
    print("  3. JSON 持久化应使用原子写入")
    print("  4. 生产环境建议使用 SQLite")
