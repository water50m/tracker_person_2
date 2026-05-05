"""
thread_pool_processor.py - Thread Pool Orchestrator for AI Processing

This module provides the ThreadPoolProcessor class which manages a pool
of worker threads for running CPU-intensive AI processing tasks.

Key Features:
- Async interface with sync execution in thread pool
- Configurable number of workers
- Task submission with futures
- Graceful shutdown support
- Error handling and timeout support

Usage:
    from services.thread_pool_processor import ThreadPoolProcessor
    from services.frame_processor import FrameProcessor
    
    # Create and initialize
    pool = ThreadPoolProcessor(max_workers=4)
    await pool.initialize()
    
    # Submit tasks
    result = await pool.process_frame(frame, frame_number=1)
    
    # Shutdown
    await pool.shutdown()
"""
import asyncio
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional, List, Callable, Any, Dict
import time
import sys
from pathlib import Path

import numpy as np

# Add parent directory for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from services.ai_processing_types import AIProcessingResult, ProcessingStatus
from services.frame_processor import FrameProcessor


class ThreadPoolProcessor:
    """
    Thread pool orchestrator for AI processing.
    
    This class manages a pool of worker threads that execute synchronous
    AI processing tasks (FrameProcessor) without blocking the async event loop.
    
    It provides:
    - Async interface for sync tasks
    - Configurable worker pool size
    - Task queuing and result retrieval
    - Timeout support
    """
    
    def __init__(
        self,
        max_workers: int = 4,
        frame_processor: Optional[FrameProcessor] = None,
        enable_classification: bool = True,
        enable_color_analysis: bool = True,
        enable_embedding: bool = True,
        classifier_top_n: int = 1,
    ):
        """
        Initialize the ThreadPoolProcessor.
        
        Args:
            max_workers: Number of worker threads (default: 4)
            frame_processor: Optional pre-configured FrameProcessor
            enable_classification: Enable clothing classification
            enable_color_analysis: Enable color analysis
            enable_embedding: Enable Re-ID embedding
            classifier_top_n: Number of top predictions to return
        """
        self.max_workers = max_workers
        self._executor: Optional[ThreadPoolExecutor] = None
        self._initialized = False
        self._lock = threading.Lock()
        
        # Frame processor configuration
        if frame_processor is not None:
            self._frame_processor = frame_processor
        else:
            self._frame_processor = FrameProcessor(
                enable_classification=enable_classification,
                enable_color_analysis=enable_color_analysis,
                enable_embedding=enable_embedding,
                classifier_top_n=classifier_top_n,
            )
        
        # Statistics
        self._total_submitted = 0
        self._total_completed = 0
        self._total_failed = 0
    
    async def initialize(self):
        """
        Initialize the thread pool.
        
        This must be called before submitting tasks.
        """
        with self._lock:
            if self._initialized:
                return
            
            self._executor = ThreadPoolExecutor(
                max_workers=self.max_workers,
                thread_name_prefix="frame_processor",
            )
            self._initialized = True
            print(f"[ThreadPoolProcessor] Initialized with {self.max_workers} workers")
    
    async def shutdown(self, wait: bool = True):
        """
        Shutdown the thread pool gracefully.
        
        Args:
            wait: Whether to wait for pending tasks to complete
        """
        with self._lock:
            if not self._initialized or self._executor is None:
                return
            
            print(f"[ThreadPoolProcessor] Shutting down (wait={wait})...")
            self._executor.shutdown(wait=wait)
            self._executor = None
            self._initialized = False
            print("[ThreadPoolProcessor] Shutdown complete")
    
    def is_initialized(self) -> bool:
        """Check if the processor is initialized."""
        return self._initialized
    
    async def process_frame(
        self,
        frame: np.ndarray,
        frame_number: int = 0,
        timestamp: Optional[float] = None,
        timeout: Optional[float] = None,
    ) -> AIProcessingResult:
        """
        Process a single frame asynchronously.
        
        This method submits the frame to the thread pool and returns
        the result asynchronously.
        
        Args:
            frame: Input frame (BGR format)
            frame_number: Frame number for tracking
            timestamp: Optional timestamp
            timeout: Optional timeout in seconds
        
        Returns:
            AIProcessingResult
        """
        if not self._initialized:
            raise RuntimeError("ThreadPoolProcessor not initialized. Call initialize() first.")
        
        self._total_submitted += 1
        
        # Get or create event loop
        loop = asyncio.get_event_loop()
        
        # Submit to thread pool
        future = loop.run_in_executor(
            self._executor,
            self._frame_processor.process_frame,
            frame,
            frame_number,
            timestamp,
        )
        
        try:
            if timeout is not None:
                result = await asyncio.wait_for(future, timeout=timeout)
            else:
                result = await future
            
            self._total_completed += 1
            return result
            
        except asyncio.TimeoutError:
            self._total_failed += 1
            return AIProcessingResult(
                status=ProcessingStatus.TIMEOUT,
                error_message=f"Processing timed out after {timeout}s",
                frame_number=frame_number,
            )
        except Exception as e:
            self._total_failed += 1
            return AIProcessingResult(
                status=ProcessingStatus.ERROR,
                error_message=str(e),
                frame_number=frame_number,
            )
    
    async def process_frames_batch(
        self,
        frames: List[np.ndarray],
        frame_numbers: Optional[List[int]] = None,
        timestamps: Optional[List[float]] = None,
        timeout_per_frame: Optional[float] = None,
    ) -> List[AIProcessingResult]:
        """
        Process multiple frames concurrently.
        
        This submits all frames to the thread pool and waits for
        all results.
        
        Args:
            frames: List of frames to process
            frame_numbers: Optional list of frame numbers
            timestamps: Optional list of timestamps
            timeout_per_frame: Optional timeout per frame
        
        Returns:
            List of AIProcessingResult (same order as input)
        """
        if not self._initialized:
            raise RuntimeError("ThreadPoolProcessor not initialized. Call initialize() first.")
        
        if not frames:
            return []
        
        # Default frame numbers
        if frame_numbers is None:
            frame_numbers = list(range(len(frames)))
        
        # Default timestamps
        if timestamps is None:
            timestamps = [None] * len(frames)
        
        # Create tasks for all frames
        tasks = [
            self.process_frame(
                frame,
                frame_number=fn,
                timestamp=ts,
                timeout=timeout_per_frame,
            )
            for frame, fn, ts in zip(frames, frame_numbers, timestamps)
        ]
        
        # Wait for all results
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Convert exceptions to error results
        processed_results = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                processed_results.append(AIProcessingResult(
                    status=ProcessingStatus.ERROR,
                    error_message=str(result),
                    frame_number=frame_numbers[i],
                ))
            else:
                processed_results.append(result)
        
        return processed_results
    
    async def process_image(
        self,
        image: np.ndarray,
        timeout: Optional[float] = None,
    ) -> AIProcessingResult:
        """
        Process a single image (convenience method).
        
        Args:
            image: Input image
            timeout: Optional timeout
        
        Returns:
            AIProcessingResult
        """
        return await self.process_frame(
            image,
            frame_number=0,
            timestamp=time.time(),
            timeout=timeout,
        )
    
    def get_stats(self) -> Dict[str, Any]:
        """
        Get processing statistics.
        
        Returns:
            Dictionary with statistics
        """
        return {
            "max_workers": self.max_workers,
            "initialized": self._initialized,
            "total_submitted": self._total_submitted,
            "total_completed": self._total_completed,
            "total_failed": self._total_failed,
            "pending": self._total_submitted - self._total_completed - self._total_failed,
        }
    
    def __enter__(self):
        """Context manager entry (sync version)."""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit (sync version)."""
        if self._executor is not None:
            self._executor.shutdown(wait=True)
        return False
    
    async def __aenter__(self):
        """Async context manager entry."""
        await self.initialize()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.shutdown(wait=True)
        return False


# ==============================================================================
# Global Singleton (optional)
# ==============================================================================

_global_processor: Optional[ThreadPoolProcessor] = None
_global_lock = threading.Lock()


async def get_global_thread_pool(
    max_workers: int = 4,
    force_new: bool = False,
) -> ThreadPoolProcessor:
    """
    Get or create a global ThreadPoolProcessor singleton.
    
    This is useful for sharing a single thread pool across the application.
    
    Args:
        max_workers: Number of workers (only used when creating new)
        force_new: If True, create a new processor even if one exists
    
    Returns:
        ThreadPoolProcessor
    """
    global _global_processor
    
    if force_new or _global_processor is None:
        with _global_lock:
            if force_new and _global_processor is not None:
                await _global_processor.shutdown()
                _global_processor = None
            
            if _global_processor is None:
                _global_processor = ThreadPoolProcessor(max_workers=max_workers)
                await _global_processor.initialize()
    
    return _global_processor


async def shutdown_global_thread_pool():
    """Shutdown the global thread pool if it exists."""
    global _global_processor
    
    if _global_processor is not None:
        await _global_processor.shutdown()
        _global_processor = None
