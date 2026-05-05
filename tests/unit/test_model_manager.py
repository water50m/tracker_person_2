"""
Tests for model_manager.py
TDD: Write tests before implementing dependent modules

Run with:
    uv run python -m pytest tests/unit/test_model_manager.py -v
"""
import pytest
import threading
import time
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

from services.model_manager import ModelManager, get_model_manager, reset_model_manager


class TestModelManagerSingleton:
    """Test ModelManager singleton behavior"""
    
    def setup_method(self):
        """Reset singleton before each test"""
        reset_model_manager()
    
    def teardown_method(self):
        """Clean up after each test"""
        reset_model_manager()
    
    def test_singleton_same_instance(self):
        """Test: เรียก ModelManager() หลายครั้งต้องได้ instance เดียวกัน"""
        manager1 = ModelManager()
        manager2 = ModelManager()
        
        assert manager1 is manager2
        assert id(manager1) == id(manager2)
    
    def test_singleton_thread_safety(self):
        """Test: singleton ต้อง thread-safe"""
        instances = []
        errors = []
        
        def create_instance():
            try:
                manager = ModelManager()
                instances.append(id(manager))
            except Exception as e:
                errors.append(str(e))
        
        # Create multiple threads
        threads = []
        for _ in range(10):
            t = threading.Thread(target=create_instance)
            threads.append(t)
        
        # Start all threads
        for t in threads:
            t.start()
        
        # Wait for all to complete
        for t in threads:
            t.join()
        
        # All instances should be the same
        assert len(set(instances)) == 1
        assert len(errors) == 0
    
    def test_get_model_manager_same_instance(self):
        """Test: get_model_manager() ต้อง return instance เดียวกัน"""
        manager1 = get_model_manager()
        manager2 = get_model_manager()
        
        assert manager1 is manager2


class TestModelManagerStatus:
    """Test ModelManager status methods"""
    
    def setup_method(self):
        reset_model_manager()
    
    def teardown_method(self):
        reset_model_manager()
    
    def test_initial_status_all_false(self):
        """Test: เริ่มต้นทุก model ต้องยังไม่ loaded"""
        manager = ModelManager()
        status = manager.get_status()
        
        assert status["detector_loaded"] is False
        assert status["classifier_loaded"] is False
        assert status["embedder_loaded"] is False
        assert status["all_ready"] is False
    
    def test_is_ready_initially_false(self):
        """Test: is_ready() เริ่มต้นต้อง return False"""
        manager = ModelManager()
        
        assert manager.is_ready() is False


class TestModelManagerReset:
    """Test ModelManager reset functionality"""
    
    def setup_method(self):
        reset_model_manager()
    
    def teardown_method(self):
        reset_model_manager()
    
    def test_reset_creates_new_instance(self):
        """Test: reset ต้องสร้าง instance ใหม่"""
        manager1 = ModelManager()
        id1 = id(manager1)
        
        reset_model_manager()
        
        manager2 = ModelManager()
        id2 = id(manager2)
        
        assert id1 != id2


class TestModelManagerLazyInit:
    """Test lazy initialization behavior"""
    
    def setup_method(self):
        reset_model_manager()
    
    def teardown_method(self):
        reset_model_manager()
    
    def test_models_not_loaded_until_accessed(self):
        """Test: models ยังไม่ load จนกว่าจะเรียก accessor"""
        manager = ModelManager()
        
        # Models should not be loaded yet
        assert manager._detector is None
        assert manager._classifier is None
        assert manager._embedder is None


class TestModelManagerConcurrency:
    """Test ModelManager under concurrent access"""
    
    def setup_method(self):
        reset_model_manager()
    
    def teardown_method(self):
        reset_model_manager()
    
    def test_concurrent_status_access(self):
        """Test: concurrent access to get_status() ต้องไม่ error"""
        manager = ModelManager()
        results = []
        errors = []
        
        def check_status():
            try:
                status = manager.get_status()
                results.append(status)
            except Exception as e:
                errors.append(str(e))
        
        threads = [threading.Thread(target=check_status) for _ in range(20)]
        
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        
        assert len(errors) == 0
        assert len(results) == 20


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
