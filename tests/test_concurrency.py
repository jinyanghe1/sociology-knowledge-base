"""并发问题测试 - 验证审查发现的线程安全问题

测试目标:
1. EmbeddingCache 线程安全问题 (chroma_manager.py)
2. _doc_meta 全局状态竞态条件 (mcp_server/server.py)
3. fallback_store 无锁保护 (chroma_manager.py)

注意: 这些测试验证并发问题，可能需要多次运行才能触发。
"""

import os
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


class TestEmbeddingCacheConcurrency:
    """测试 EmbeddingCache 的并发安全问题"""
    
    def test_concurrent_cache_access(self):
        """测试并发缓存访问可能导致的问题"""
        
        # 模拟 EmbeddingCache 的简化实现（有问题版本）
        class EmbeddingCacheVulnerable:
            def __init__(self, maxsize: int = 100):
                self.maxsize = maxsize
                self._cache = {}
                self._access_order = []
                self._lock = threading.Lock()
            
            def _get_key(self, text: str, model: str) -> str:
                return f"{model}:{hash(text)}"
            
            def get(self, text: str, model: str):
                key = self._get_key(text, model)
                with self._lock:
                    if key in self._cache:
                        # 问题1: 返回引用而非副本
                        # 问题2: list.remove 是 O(n)，可能 ValueError
                        try:
                            self._access_order.remove(key)
                        except ValueError:
                            pass
                        self._access_order.append(key)
                        return self._cache[key]  # 返回引用
                return None
            
            def put(self, text: str, model: str, embedding: list):
                key = self._get_key(text, model)
                with self._lock:
                    if key in self._cache:
                        self._access_order.remove(key)
                    elif len(self._cache) >= self.maxsize:
                        lru_key = self._access_order.pop(0)
                        del self._cache[lru_key]
                    
                    self._cache[key] = embedding
                    self._access_order.append(key)
        
        cache = EmbeddingCacheVulnerable(maxsize=10)
        errors = []
        
        def writer_thread(thread_id: int):
            """写入线程"""
            try:
                for i in range(100):
                    cache.put(f"text_{thread_id}_{i}", "model", [float(i)] * 768)
            except Exception as e:
                errors.append(f"Writer {thread_id}: {e}")
        
        def reader_thread(thread_id: int):
            """读取线程"""
            try:
                for i in range(100):
                    result = cache.get(f"text_{thread_id}_{i}", "model")
                    if result:
                        # 尝试修改返回的引用
                        result[0] = 999.0
            except Exception as e:
                errors.append(f"Reader {thread_id}: {e}")
        
        print("\nEmbeddingCache 并发测试:")
        print(f"  初始缓存大小: {len(cache._cache)}")
        
        # 启动多个读写线程
        threads = []
        for i in range(5):
            t = threading.Thread(target=writer_thread, args=(i,))
            threads.append(t)
            t = threading.Thread(target=reader_thread, args=(i,))
            threads.append(t)
        
        for t in threads:
            t.start()
        
        for t in threads:
            t.join()
        
        print(f"  最终缓存大小: {len(cache._cache)}")
        print(f"  错误数量: {len(errors)}")
        
        if errors:
            print("  ⚠️ 发现并发错误:")
            for err in errors[:5]:
                print(f"    - {err}")
    
    def test_safe_embedding_cache(self):
        """测试安全的 EmbeddingCache 实现"""
        from collections import OrderedDict
        
        class EmbeddingCacheSafe:
            """线程安全的 EmbeddingCache"""
            def __init__(self, maxsize: int = 100):
                self.maxsize = maxsize
                self._cache: OrderedDict[str, list] = OrderedDict()
                self._lock = threading.RLock()
            
            def _get_key(self, text: str, model: str) -> str:
                return f"{model}:{hash(text)}"
            
            def get(self, text: str, model: str):
                key = self._get_key(text, model)
                with self._lock:
                    if key in self._cache:
                        self._cache.move_to_end(key)
                        return self._cache[key].copy()  # 返回副本
                return None
            
            def put(self, text: str, model: str, embedding: list):
                key = self._get_key(text, model)
                with self._lock:
                    if key in self._cache:
                        self._cache.move_to_end(key)
                    else:
                        if len(self._cache) >= self.maxsize:
                            self._cache.popitem(last=False)
                        self._cache[key] = embedding.copy()  # 存储副本
        
        cache = EmbeddingCacheSafe(maxsize=10)
        errors = []
        
        def stress_test(thread_id: int):
            try:
                for i in range(100):
                    cache.put(f"text_{i}", "model", [float(i)] * 768)
                    result = cache.get(f"text_{i}", "model")
                    if result and thread_id % 2 == 0:
                        result[0] = 999.0  # 修改副本不影响缓存
            except Exception as e:
                errors.append(f"Thread {thread_id}: {e}")
        
        print("\n安全 EmbeddingCache 并发测试:")
        
        threads = []
        for i in range(10):
            t = threading.Thread(target=stress_test, args=(i,))
            threads.append(t)
        
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        
        print(f"  错误数量: {len(errors)}")
        print(f"  缓存大小: {len(cache._cache)}")
        
        if not errors:
            print("  ✓ 无并发错误")


class TestDocMetaConcurrency:
    """测试 _doc_meta 全局状态的并发问题"""
    
    def test_unsafe_global_state(self):
        """测试无锁保护的全局状态"""
        
        # 模拟 mcp_server/server.py 的实现
        _doc_meta: dict = {}
        
        def index_document(doc_id: str, filename: str):
            """模拟文档索引 - 无锁保护"""
            # 问题: 多线程并发访问可能损坏字典
            _doc_meta[doc_id] = {
                "id": doc_id,
                "filename": filename,
                "status": "ready"
            }
        
        def delete_document(doc_id: str):
            """模拟文档删除 - 无锁保护"""
            if doc_id in _doc_meta:
                del _doc_meta[doc_id]
        
        errors = []
        
        def worker(thread_id: int):
            try:
                for i in range(50):
                    doc_id = f"doc_{thread_id}_{i}"
                    index_document(doc_id, f"file_{i}.pdf")
                    if i % 2 == 0:
                        delete_document(doc_id)
            except Exception as e:
                errors.append(f"Thread {thread_id}: {e}")
        
        print("\n_doc_meta 无锁并发测试:")
        print(f"  初始文档数: {len(_doc_meta)}")
        
        threads = []
        for i in range(5):
            t = threading.Thread(target=worker, args=(i,))
            threads.append(t)
        
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        
        print(f"  最终文档数: {len(_doc_meta)}")
        print(f"  错误数量: {len(errors)}")
        
        if errors:
            print("  ⚠️ 并发访问错误:")
            for err in errors[:3]:
                print(f"    - {err}")
    
    def test_safe_global_state_with_lock(self):
        """测试带锁保护的全局状态"""
        
        _doc_meta: dict = {}
        _lock = threading.RLock()
        
        def index_document_safe(doc_id: str, filename: str):
            """带锁的文档索引"""
            with _lock:
                _doc_meta[doc_id] = {
                    "id": doc_id,
                    "filename": filename,
                    "status": "ready"
                }
        
        def delete_document_safe(doc_id: str):
            """带锁的文档删除"""
            with _lock:
                if doc_id in _doc_meta:
                    del _doc_meta[doc_id]
        
        def list_documents_safe():
            """带锁的文档列表"""
            with _lock:
                return list(_doc_meta.values())
        
        errors = []
        
        def worker(thread_id: int):
            try:
                for i in range(50):
                    doc_id = f"doc_{thread_id}_{i}"
                    index_document_safe(doc_id, f"file_{i}.pdf")
                    if i % 3 == 0:
                        delete_document_safe(doc_id)
                    if i % 5 == 0:
                        list_documents_safe()
            except Exception as e:
                errors.append(f"Thread {thread_id}: {e}")
        
        print("\n带锁保护的 _doc_meta 测试:")
        
        threads = []
        for i in range(5):
            t = threading.Thread(target=worker, args=(i,))
            threads.append(t)
        
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        
        print(f"  最终文档数: {len(_doc_meta)}")
        print(f"  错误数量: {len(errors)}")
        
        if not errors:
            print("  ✓ 无并发错误")


class TestFallbackStoreConcurrency:
    """测试 fallback_store 的并发问题"""
    
    def test_unsafe_fallback_store(self):
        """测试无锁保护的 fallback_store"""
        
        _fallback_store = {
            "ids": [],
            "embeddings": [],
            "documents": [],
            "metadatas": []
        }
        
        def add_document(doc_id: str, embedding: list, text: str):
            """模拟添加 - 无锁保护"""
            if doc_id not in _fallback_store["ids"]:
                _fallback_store["ids"].append(doc_id)
                _fallback_store["embeddings"].append(embedding)
                _fallback_store["documents"].append(text)
                _fallback_store["metadatas"].append({})
        
        def delete_document(doc_id: str):
            """模拟删除 - 无锁保护"""
            store = _fallback_store
            keep = [i for i, id in enumerate(store["ids"]) if id != doc_id]
            _fallback_store["ids"] = [store["ids"][i] for i in keep]
            _fallback_store["embeddings"] = [store["embeddings"][i] for i in keep]
            _fallback_store["documents"] = [store["documents"][i] for i in keep]
            _fallback_store["metadatas"] = [store["metadatas"][i] for i in keep]
        
        errors = []
        
        def writer(thread_id: int):
            try:
                for i in range(30):
                    doc_id = f"doc_{thread_id}_{i}"
                    add_document(doc_id, [float(i)] * 768, f"text_{i}")
            except Exception as e:
                errors.append(f"Writer {thread_id}: {e}")
        
        def deleter(thread_id: int):
            try:
                for i in range(30):
                    doc_id = f"doc_{thread_id}_{i}"
                    delete_document(doc_id)
            except Exception as e:
                errors.append(f"Deleter {thread_id}: {e}")
        
        print("\nfallback_store 无锁并发测试:")
        print(f"  初始文档数: {len(_fallback_store['ids'])}")
        
        threads = []
        for i in range(3):
            t = threading.Thread(target=writer, args=(i,))
            threads.append(t)
            t = threading.Thread(target=deleter, args=(i,))
            threads.append(t)
        
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        
        print(f"  最终文档数: {len(_fallback_store['ids'])}")
        print(f"  错误数量: {len(errors)}")
        
        # 验证数据一致性
        ids_len = len(_fallback_store["ids"])
        embeddings_len = len(_fallback_store["embeddings"])
        documents_len = len(_fallback_store["documents"])
        metadatas_len = len(_fallback_store["metadatas"])
        
        consistent = ids_len == embeddings_len == documents_len == metadatas_len
        print(f"  数据一致性: {'✓' if consistent else '✗'}")
        
        if not consistent:
            print(f"    ids: {ids_len}, embeddings: {embeddings_len}, "
                  f"documents: {documents_len}, metadatas: {metadatas_len}")


class TestCacheKeyCollision:
    """测试查询缓存键的哈希冲突"""
    
    def test_embedding_hash_collision(self):
        """测试仅使用前10维导致的哈希冲突"""
        import hashlib
        
        def get_cache_key_vulnerable(embedding: list) -> str:
            """有问题的缓存键生成 - 仅使用前10维"""
            return hashlib.md5(
                str(embedding[:10]).encode()
            ).hexdigest()
        
        # 生成两个不同的嵌入向量，但前10维相同
        embedding1 = [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0] + [0.5] * 758
        embedding2 = [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0] + [0.9] * 758
        
        key1 = get_cache_key_vulnerable(embedding1)
        key2 = get_cache_key_vulnerable(embedding2)
        
        print("\n缓存键哈希冲突测试:")
        print(f"  嵌入向量1 (后758维=0.5): ...{embedding1[-5:]}")
        print(f"  嵌入向量2 (后758维=0.9): ...{embedding2[-5:]}")
        print(f"  向量不同: {embedding1 != embedding2}")
        print(f"  缓存键1: {key1[:16]}...")
        print(f"  缓存键2: {key2[:16]}...")
        print(f"  缓存键相同 (冲突!): {key1 == key2}")
        
        if key1 == key2:
            print("  ⚠️ 警告: 不同查询可能命中错误缓存！")
    
    def test_safe_embedding_hash(self):
        """测试安全的缓存键生成"""
        import hashlib
        import numpy as np
        
        def get_cache_key_safe(embedding: list) -> str:
            """安全的缓存键生成 - 使用完整向量"""
            embedding_bytes = np.array(embedding, dtype=np.float32).tobytes()
            return hashlib.sha256(embedding_bytes).hexdigest()
        
        embedding1 = [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0] + [0.5] * 758
        embedding2 = [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0] + [0.9] * 758
        
        key1 = get_cache_key_safe(embedding1)
        key2 = get_cache_key_safe(embedding2)
        
        print("\n安全缓存键测试:")
        print(f"  缓存键不同: {key1 != key2}")
        
        if key1 != key2:
            print("  ✓ 无哈希冲突")


if __name__ == "__main__":
    print("=" * 60)
    print("并发问题测试套件")
    print("=" * 60)
    
    test_classes = [
        TestEmbeddingCacheConcurrency(),
        TestDocMetaConcurrency(),
        TestFallbackStoreConcurrency(),
        TestCacheKeyCollision(),
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
    print("\n注意: 并发问题可能不是每次都能复现，")
    print("      需要多次运行或使用更高并发压力才能触发。")
