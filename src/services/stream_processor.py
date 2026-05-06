"""
stream_processor.py - Real-time Stream Processing

This module provides the StreamProcessor class for processing real-time
video streams (RTSP, webcam) with continuous AI analysis.

Key Features:
- Continuous frame processing from live sources
- Real-time detection callbacks
- Graceful stop handling via asyncio.Event
- Frame skip for performance tuning
- Support RTSP, webcam, and other live sources
- Integration with _ACTIVE_STREAMS registry

Usage:
    from services.stream_processor import StreamProcessor
    from services.thread_pool_processor import ThreadPoolProcessor
    
    pool = ThreadPoolProcessor(max_workers=4)
    await pool.initialize()
    
    processor = StreamProcessor(thread_pool=pool, camera_id="CAM-01")
    
    stop_event = asyncio.Event()
    await processor.start_stream(
        source="rtsp://...",
        on_detection=lambda det, fn: broadcast(det),
        stop_event=stop_event,
    )
"""
import asyncio
import time
import threading
from typing import Optional, Callable, Dict, Any, List
from dataclasses import dataclass, field
from pathlib import Path
from collections import defaultdict
import sys

import numpy as np
import cv2

# Add parent directory for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from services.ai_processing_types import (
    AIProcessingResult,
    PersonDetection,
    StreamProcessingStats,
    ProcessingStatus,
)
from services.thread_pool_processor import ThreadPoolProcessor
from services.frame_processor import FrameProcessor


# Type aliases
DetectionCallback = Callable[[PersonDetection, int], None]  # (detection, frame_number)
FrameCallback = Callable[[np.ndarray, int], None]  # (frame, frame_number)


class StreamProcessor:
    """
    Real-time stream processor for live video sources.
    
    This class handles continuous processing of live video streams:
    - RTSP cameras
    - Webcam (USB / built-in)
    - Other live sources
    
    Unlike VideoProcessor (which processes a finite file), StreamProcessor
    runs continuously until stopped via stop_event.
    
    Key Differences from VideoProcessor:
    - No total_frames (infinite stream)
    - No progress percentage (ongoing process)
    - Continuous detection callbacks
    - Graceful stop handling
    """
    
    def __init__(
        self,
        thread_pool: ThreadPoolProcessor,
        camera_id: Optional[str] = None,
        frame_skip: int = 5,
        save_to_db: bool = True,
        batch_size: int = 5,
    ):
        """
        Initialize StreamProcessor.
        
        Args:
            thread_pool: ThreadPoolProcessor for AI inference
            camera_id: Camera identifier (for _ACTIVE_STREAMS registry), can be set later in start_stream()
            frame_skip: Process 1 frame every N frames (default: 5 = ~6fps for 30fps stream)
            save_to_db: Whether to save detections to database
            batch_size: Batch size for database inserts
        """
        self.thread_pool = thread_pool
        self.camera_id = camera_id or "UNKNOWN"
        self.frame_skip = frame_skip
        self.save_to_db = save_to_db
        self.batch_size = batch_size
        
        # Stats tracking
        self._stats = StreamProcessingStats(camera_id=self.camera_id)
        self._lock = threading.Lock()
        self._is_running = False
        
        # Detection batch buffer
        self._detection_batch: List[Dict] = []
        
        # Frame counter
        self._frame_count = 0
        
        # Stop event (set externally)
        self._stop_event: Optional[asyncio.Event] = None
        
        # Storage service for MinIO uploads
        self._storage = None
        if self.save_to_db:
            try:
                from services.storage import StorageService
                self._storage = StorageService()
            except Exception as e:
                print(f"[StreamProcessor] Storage service initialization failed: {e}")
    
    def stop_stream(self):
        """
        Signal the stream to stop gracefully.
        
        This sets the internal stop event, causing the processing loop
        to exit on the next iteration.
        """
        if self._stop_event:
            self._stop_event.set()
            print(f"[StreamProcessor] Stop signal sent for {self.camera_id}")
        self._is_running = False
    
    async def start_stream(
        self,
        source: str,
        on_detection: Optional[DetectionCallback] = None,
        on_frame: Optional[FrameCallback] = None,
        stop_event: Optional[asyncio.Event] = None,
        save_to_db: Optional[bool] = None,
        camera_id: Optional[str] = None,
        frame_skip: Optional[int] = None,
    ) -> StreamProcessingStats:
        """
        Start processing a live video stream.
        
        This method runs continuously until stop_event is set.
        It processes frames in a loop, calling callbacks for detections.
        
        Args:
            source: Stream source (RTSP URL, webcam index "0", "1", etc.)
            on_detection: Callback(detection, frame_number) for each detection
            on_frame: Callback(frame, frame_number) for each processed frame
            stop_event: asyncio.Event to signal graceful stop
            save_to_db: Override default save_to_db setting
            camera_id: Override camera_id for this stream session
            frame_skip: Override frame_skip for this stream session
        
        Returns:
            StreamProcessingStats when stream stops
        """
        # Use provided overrides or fall back to instance defaults
        stream_camera_id = camera_id if camera_id is not None else self.camera_id
        stream_frame_skip = frame_skip if frame_skip is not None else self.frame_skip
        
        # Use provided save option or fall back to instance default
        should_save_db = save_to_db if save_to_db is not None else self.save_to_db
        
        # Store stop event
        self._stop_event = stop_event or asyncio.Event()
        
        # Initialize stats
        self._stats = StreamProcessingStats(
            camera_id=stream_camera_id,
            status=ProcessingStatus.PROCESSING,
            start_time=time.time(),
        )
        
        self._is_running = True
        self._frame_count = 0
        
        # Resolve source
        resolved_source = self._resolve_source(source)
        
        print(f"[StreamProcessor] Starting stream for {stream_camera_id}")
        print(f"[StreamProcessor] Source: {source}")
        print(f"[StreamProcessor] Frame skip: {stream_frame_skip}")
        
        # Update internal camera_id for this session
        self.camera_id = stream_camera_id
        
        try:
            loop = asyncio.get_running_loop()

            # Open video capture. OpenCV calls can block for network streams, so
            # keep them off the FastAPI event loop.
            cap = await loop.run_in_executor(None, cv2.VideoCapture, resolved_source)
            if not await loop.run_in_executor(None, cap.isOpened):
                raise ValueError(f"Cannot open stream source: {source}")
            
            # Get stream info (may be 0 for live streams)
            fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
            width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)) or 640
            height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)) or 480
            
            self._stats.fps = fps
            self._stats.image_width = width
            self._stats.image_height = height
            
            print(f"[StreamProcessor] Stream opened: {width}x{height} @ {float(fps):.2f}fps")
            
            # Initialize database if needed
            db = None
            if should_save_db:
                try:
                    from services.database import DatabaseService
                    db = DatabaseService()
                except Exception as e:
                    print(f"[StreamProcessor] Database initialization failed: {e}")
                    db = None
            
            # Main processing loop
            consecutive_errors = 0
            max_consecutive_errors = 10
            
            while not self._stop_event.is_set():
                try:
                    # Read frame
                    ret, frame = await loop.run_in_executor(None, cap.read)
                    
                    if not ret:
                        # Failed to read frame
                        consecutive_errors += 1
                        
                        if consecutive_errors >= max_consecutive_errors:
                            print(f"[StreamProcessor] Too many consecutive errors, stopping")
                            self._stats.status = ProcessingStatus.ERROR
                            self._stats.error_message = "Too many consecutive frame read errors"
                            break
                        
                        # Brief pause before retry
                        await asyncio.sleep(0.1)
                        continue
                    
                    # Reset error counter on success
                    consecutive_errors = 0
                    
                    # Increment frame counter
                    self._frame_count += 1
                    
                    # Skip frames (only process every Nth frame)
                    if self._frame_count % stream_frame_skip != 0:
                        continue
                    
                    # Process frame
                    try:
                        result = await self._process_frame(frame, self._frame_count)
                        
                        # Update stats
                        self._stats.processed_frames += 1
                        
                        # Handle frame callback
                        if on_frame:
                            try:
                                on_frame(frame, self._frame_count)
                            except Exception as e:
                                print(f"[StreamProcessor] Frame callback error: {e}")
                        
                        # Handle detections
                        if result.detections:
                            for person in result.detections:
                                # Update stats
                                self._stats.num_persons_detected += 1
                                self._stats.total_detections += 1
                                
                                # Call detection callback
                                if on_detection:
                                    try:
                                        on_detection(person, self._frame_count)
                                    except Exception as e:
                                        print(f"[StreamProcessor] Detection callback error: {e}")
                                
                                # Add to batch for database
                                if should_save_db:
                                    # Upload image to MinIO if storage is available
                                    image_path = None
                                    if self._storage and person.bbox and frame is not None:
                                        try:
                                            # Extract person crop from frame
                                            x, y = max(0, person.bbox.x), max(0, person.bbox.y)
                                            x2 = min(frame.shape[1], person.bbox.x + person.bbox.width)
                                            y2 = min(frame.shape[0], person.bbox.y + person.bbox.height)
                                            
                                            if x2 > x and y2 > y:  # Valid bbox
                                                person_crop = frame[y:y2, x:x2]
                                                
                                                # Generate filename
                                                import uuid
                                                filename = f"{self.camera_id}/stream/{self._frame_count}_{uuid.uuid4().hex[:8]}.jpg"
                                                
                                                # Upload to MinIO (run in thread pool)
                                                loop = asyncio.get_event_loop()
                                                image_path = await loop.run_in_executor(
                                                    None,
                                                    self._storage.upload_image,
                                                    person_crop,
                                                    filename
                                                )
                                                
                                                if image_path:
                                                    print(f"[StreamProcessor] Uploaded image: {image_path}")
                                        except Exception as e:
                                            print(f"[StreamProcessor] Image upload error: {e}")
                                    
                                    self._add_to_batch(person, self._frame_count, image_path)
                        
                        # Save batch to database periodically
                        if len(self._detection_batch) >= self.batch_size:
                            await self._flush_batch(db)
                    
                    except Exception as e:
                        print(f"[StreamProcessor] Frame processing error: {e}")
                        self._stats.num_errors += 1
                
                except Exception as e:
                    print(f"[StreamProcessor] Loop error: {e}")
                    self._stats.num_errors += 1
                    await asyncio.sleep(0.1)  # Brief pause on error
            
            # Cleanup
            await loop.run_in_executor(None, cap.release)
            
            # Flush remaining batch
            if self._detection_batch:
                await self._flush_batch(db)
            
            # Update final stats
            self._is_running = False
            self._stats.end_time = time.time()
            
            if self._stats.status != ProcessingStatus.ERROR:
                self._stats.status = ProcessingStatus.STOPPED
            
            print(f"[StreamProcessor] Stream stopped for {self.camera_id}")
            print(f"[StreamProcessor] Processed {self._stats.processed_frames} frames, "
                  f"found {self._stats.num_persons_detected} persons")
            
            return self._stats
            
        except Exception as e:
            print(f"[StreamProcessor] Fatal error: {e}")
            self._is_running = False
            self._stats.status = ProcessingStatus.ERROR
            self._stats.error_message = str(e)
            self._stats.end_time = time.time()
            raise  # Re-raise the exception for caller to handle
    
    def stop(self):
        """
        Signal the stream to stop.
        
        This sets the stop_event if it exists.
        """
        if self._stop_event:
            self._stop_event.set()
            print(f"[StreamProcessor] Stop requested for {self.camera_id}")
    
    def _resolve_source(self, source: str) -> str or int:
        """
        Resolve stream source.
        
        Args:
            source: Original source string (RTSP URL or webcam index)
        
        Returns:
            Resolved source (string for RTSP, int for webcam)
        """
        # Check if it's a webcam index
        if isinstance(source, str) and source.isdigit():
            return int(source)
        
        return source
    
    async def _process_frame(self, frame: np.ndarray, frame_number: int) -> AIProcessingResult:
        """
        Process a single frame using ThreadPoolProcessor.
        
        Args:
            frame: OpenCV frame
            frame_number: Frame number
        
        Returns:
            AIProcessingResult
        """
        # Use thread pool for processing
        result = await self.thread_pool.process_frame(
            frame,
            frame_number=frame_number,
            timestamp=time.time(),
        )
        
        return result
    
    def _add_to_batch(
        self,
        person: PersonDetection,
        frame_number: int,
        image_path: Optional[str] = None,
    ):
        """
        Add detection to batch for database insert.
        
        Args:
            person: PersonDetection object
            frame_number: Frame number
            image_path: Path to uploaded image in MinIO (optional)
        """
        detection_data = {
            'person': person,
            'frame_number': frame_number,
            'camera_id': self.camera_id,
            'image_path': image_path,
            'timestamp': time.time(),
        }
        
        self._detection_batch.append(detection_data)
    
    async def _flush_batch(self, db: Optional[Any] = None):
        """
        Flush detection batch to database using batch insert.
        
        Args:
            db: DatabaseService instance
        """
        if not db or not self._detection_batch:
            return
        
        try:
            # Prepare batch data for database insert
            batch_data = []
            for detection_data in self._detection_batch:
                person = detection_data['person']
                # Get category and class_name from first item (if any)
                first_item = person.items[0] if person.items else None
                category = first_item.category.value if first_item and first_item.category else None
                class_name = first_item.class_name if first_item else None

                batch_data.append({
                    'camera_id': detection_data['camera_id'],
                    'track_id': person.track_id,
                    'category': category,
                    'class_name': class_name,
                    'bbox': {
                        'x': person.bbox.x,
                        'y': person.bbox.y,
                        'width': person.bbox.width,
                        'height': person.bbox.height,
                    } if person.bbox else None,
                    'image_path': detection_data.get('image_path') or '',  # From MinIO upload
                    'video_time_offset': detection_data['frame_number'],
                    'video_id': detection_data.get('video_id'),  # May be None for streams
                    'embedding': person.embedding.tolist() if person.embedding is not None else None,
                })
            
            # Use executemany for batch insert (runs in thread pool to avoid blocking)
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None,  # Default executor
                db.insert_detections_batch,
                batch_data
            )
            
            self._stats.num_detections_saved += len(self._detection_batch)
            print(f"[StreamProcessor] Batch inserted {len(self._detection_batch)} detections")
            
        except Exception as e:
            print(f"[StreamProcessor] Database batch insert error: {e}")
            self._stats.num_errors += 1
        
        finally:
            # Clear batch
            self._detection_batch.clear()
    
    def get_stats(self) -> StreamProcessingStats:
        """
        Get current stream stats.
        
        Returns:
            StreamProcessingStats
        """
        return self._stats
    
    def is_running(self) -> bool:
        """
        Check if stream is currently running.
        
        Returns:
            True if running, False otherwise
        """
        return self._is_running


# ==============================================================================
# Stream Manager for Multiple Cameras
# ==============================================================================

class StreamManager:
    """
    Manager for multiple concurrent stream processors.
    
    This class manages multiple StreamProcessor instances,
    allowing concurrent processing of multiple cameras.
    """
    
    def __init__(self, thread_pool: ThreadPoolProcessor):
        """
        Initialize StreamManager.
        
        Args:
            thread_pool: Shared ThreadPoolProcessor for all streams
        """
        self.thread_pool = thread_pool
        self._streams: Dict[str, StreamProcessor] = {}
        self._tasks: Dict[str, asyncio.Task] = {}
        self._lock = threading.Lock()
    
    async def start_stream(
        self,
        camera_id: str,
        source: str,
        on_detection: Optional[DetectionCallback] = None,
        on_frame: Optional[FrameCallback] = None,
        stop_event: Optional[asyncio.Event] = None,
        frame_skip: int = 5,
    ) -> StreamProcessor:
        """
        Start a new stream.
        
        Args:
            camera_id: Camera identifier
            source: Stream source (RTSP, webcam)
            on_detection: Detection callback
            on_frame: Frame callback
            stop_event: Stop event
            frame_skip: Frame skip interval
        
        Returns:
            StreamProcessor instance
        """
        with self._lock:
            # Stop existing stream if any
            if camera_id in self._streams:
                print(f"[StreamManager] Stopping existing stream for {camera_id}")
                self._streams[camera_id].stop_stream()
                if camera_id in self._tasks:
                    try:
                        await asyncio.wait_for(self._tasks[camera_id], timeout=5.0)
                    except asyncio.TimeoutError:
                        self._tasks[camera_id].cancel()
            
            # Create new processor
            processor = StreamProcessor(
                thread_pool=self.thread_pool,
                camera_id=camera_id,
                frame_skip=frame_skip,
            )
            
            self._streams[camera_id] = processor
            
            # Start stream task
            task = asyncio.create_task(
                processor.start_stream(
                    source=source,
                    on_detection=on_detection,
                    on_frame=on_frame,
                    stop_event=stop_event,
                )
            )
            
            self._tasks[camera_id] = task
            
            return processor
    
    async def stop_stream(self, camera_id: str) -> Optional[StreamProcessingStats]:
        """
        Stop a stream.
        
        Args:
            camera_id: Camera identifier
        
        Returns:
            StreamProcessingStats or None
        """
        with self._lock:
            if camera_id not in self._streams:
                return None
            
            processor = self._streams[camera_id]
            task = self._tasks.get(camera_id)
            
            # Signal stop
            processor.stop_stream()
            
            # Wait for task to complete
            if task:
                try:
                    stats = await asyncio.wait_for(task, timeout=10.0)
                except asyncio.TimeoutError:
                    task.cancel()
                    stats = processor.get_stats()
            else:
                stats = processor.get_stats()
            
            # Cleanup
            del self._streams[camera_id]
            del self._tasks[camera_id]
            
            return stats
    
    def get_stream(self, camera_id: str) -> Optional[StreamProcessor]:
        """
        Get stream processor by camera ID.
        
        Args:
            camera_id: Camera identifier
        
        Returns:
            StreamProcessor or None
        """
        return self._streams.get(camera_id)
    
    def list_streams(self) -> List[str]:
        """
        List all active stream camera IDs.
        
        Returns:
            List of camera IDs
        """
        return list(self._streams.keys())
    
    async def stop_all(self):
        """Stop all active streams."""
        camera_ids = self.list_streams()
        
        for camera_id in camera_ids:
            await self.stop_stream(camera_id)


# ==============================================================================
# Global Stream Manager Instance
# ==============================================================================

_global_stream_manager: Optional[StreamManager] = None
_global_lock = threading.Lock()


async def get_global_stream_manager(
    thread_pool: Optional[ThreadPoolProcessor] = None,
) -> StreamManager:
    """
    Get or create global StreamManager instance.
    
    Args:
        thread_pool: Optional ThreadPoolProcessor (creates new if None)
    
    Returns:
        StreamManager
    """
    global _global_stream_manager
    
    if _global_stream_manager is None:
        with _global_lock:
            if _global_stream_manager is None:
                if thread_pool is None:
                    from services.thread_pool_processor import ThreadPoolProcessor
                    thread_pool = ThreadPoolProcessor(max_workers=4)
                    await thread_pool.initialize()
                
                _global_stream_manager = StreamManager(thread_pool)
    
    return _global_stream_manager
