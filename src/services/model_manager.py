"""
model_manager.py - Singleton Model Manager for AI Processing

This module provides a thread-safe singleton for managing AI model instances
(PersonDetector, ClothingClassifier, ClothingEmbedder). It ensures:
- Models are loaded only once (memory efficient)
- Thread-safe access to shared models
- Lazy initialization (models loaded on first use)
- Proper cleanup on shutdown

Usage:
    from services.model_manager import ModelManager
    
    # Get singleton instance
    manager = ModelManager()
    
    # Access models (auto-initialized on first access)
    detector = manager.get_detector()
    classifier = manager.get_classifier()
    embedder = manager.get_embedder()
"""
import threading
from typing import Optional
import sys
from pathlib import Path

# Add parent directory for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from config_loader import (
    get_detector_model_path,
    get_classifier_model_path,
    get_reid_model_path,
)


class ModelManager:
    """
    Thread-safe singleton for managing AI model instances.
    
    This class ensures that heavy AI models are loaded only once
    and shared across all processing threads safely.
    """
    
    _instance: Optional["ModelManager"] = None
    _lock: threading.Lock = threading.Lock()
    _initialized: bool = False
    
    def __new__(cls) -> "ModelManager":
        """Thread-safe singleton creation"""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        """Initialize the model manager (only runs once)"""
        if ModelManager._initialized:
            return
        
        with ModelManager._lock:
            if ModelManager._initialized:
                return
            
            self._detector = None
            self._classifier = None
            self._embedder = None
            
            self._detector_lock = threading.Lock()
            self._classifier_lock = threading.Lock()
            self._embedder_lock = threading.Lock()
            
            ModelManager._initialized = True
    
    # ==========================================================================
    # Lazy-initialized model accessors
    # ==========================================================================
    
    def get_detector(self):
        """
        Get the PersonDetector instance (lazy initialization).
        
        Returns:
            PersonDetector: The detector model instance
        """
        if self._detector is None:
            with self._detector_lock:
                if self._detector is None:
                    from ai.detector import PersonDetector
                    
                    model_path = get_detector_model_path()
                    print(f"[ModelManager] Initializing PersonDetector from {model_path}")
                    self._detector = PersonDetector(model_path)
                    print(f"[ModelManager] PersonDetector ready")
        
        return self._detector
    
    def get_classifier(self):
        """
        Get the ClothingClassifier instance (lazy initialization).
        
        Returns:
            ClothingClassifier: The classifier model instance
        """
        if self._classifier is None:
            with self._classifier_lock:
                if self._classifier is None:
                    from ai.classifier import ClothingClassifier
                    
                    model_path = get_classifier_model_path()
                    print(f"[ModelManager] Initializing ClothingClassifier from {model_path}")
                    self._classifier = ClothingClassifier(model_path)
                    print(f"[ModelManager] ClothingClassifier ready")
        
        return self._classifier
    
    def get_embedder(self):
        """
        Get the ClothingEmbedder instance (lazy initialization).
        
        Returns:
            ClothingEmbedder: The embedder model instance
        """
        if self._embedder is None:
            with self._embedder_lock:
                if self._embedder is None:
                    from ai.feature_extractor import ClothingEmbedder
                    
                    # Embedder uses classifier model path + device
                    model_path = get_classifier_model_path()
                    print(f"[ModelManager] Initializing ClothingEmbedder from {model_path}")
                    self._embedder = ClothingEmbedder(model_path)
                    print(f"[ModelManager] ClothingEmbedder ready")
        
        return self._embedder
    
    # ==========================================================================
    # Status & Monitoring
    # ==========================================================================
    
    def get_status(self) -> dict:
        """
        Get the current status of all models.
        
        Returns:
            Dictionary with model initialization status
        """
        return {
            "detector_loaded": self._detector is not None,
            "classifier_loaded": self._classifier is not None,
            "embedder_loaded": self._embedder is not None,
            "all_ready": all([
                self._detector is not None,
                self._classifier is not None,
                self._embedder is not None,
            ]),
        }
    
    def is_ready(self) -> bool:
        """
        Check if all models are loaded and ready.
        
        Returns:
            True if all models are initialized
        """
        return all([
            self._detector is not None,
            self._classifier is not None,
            self._embedder is not None,
        ])
    
    def preload_all(self):
        """
        Preload all models eagerly (useful for startup).
        
        This forces all models to load immediately rather than
        waiting for first use.
        """
        print("[ModelManager] Preloading all models...")
        self.get_detector()
        self.get_classifier()
        self.get_embedder()
        print("[ModelManager] All models preloaded")
    
    # ==========================================================================
    # Cleanup
    # ==========================================================================
    
    def cleanup(self):
        """
        Clean up model resources.
        
        Call this on application shutdown to free GPU memory.
        """
        print("[ModelManager] Cleaning up models...")
        
        with self._detector_lock:
            self._detector = None
        
        with self._classifier_lock:
            self._classifier = None
        
        with self._embedder_lock:
            self._embedder = None
        
        import torch
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
        
        print("[ModelManager] Cleanup complete")
    
    def __del__(self):
        """Destructor - attempt cleanup"""
        try:
            self.cleanup()
        except:
            pass


# ==============================================================================
# Convenience Functions
# ==============================================================================

def get_model_manager() -> ModelManager:
    """
    Get the singleton ModelManager instance.
    
    This is the preferred way to access the model manager.
    
    Returns:
        ModelManager: The singleton instance
    
    Example:
        from services.model_manager import get_model_manager
        
        manager = get_model_manager()
        detector = manager.get_detector()
    """
    return ModelManager()


def reset_model_manager():
    """
    Reset the singleton (mainly for testing).
    
    WARNING: This will clear all model instances and
    they will be recreated on next access.
    """
    global ModelManager
    
    with ModelManager._lock:
        if ModelManager._instance is not None:
            ModelManager._instance.cleanup()
            ModelManager._instance = None
            ModelManager._initialized = False


# ==============================================================================
# Module-level singleton accessor (for backwards compatibility)
# ==============================================================================

# Global singleton instance (lazy access via get_model_manager)
_model_manager: Optional[ModelManager] = None
_model_manager_lock = threading.Lock()


def get_global_model_manager() -> ModelManager:
    """Get or create the global model manager instance."""
    global _model_manager
    
    if _model_manager is None:
        with _model_manager_lock:
            if _model_manager is None:
                _model_manager = ModelManager()
    
    return _model_manager
