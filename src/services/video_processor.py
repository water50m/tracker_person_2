"""
video_processor.py - Video Processing with Progress Monitoring

This module provides the VideoProcessor class for processing video files
with real-time progress updates suitable for frontend dashboard display.

Key Features:
- Async video processing with ThreadPool
- Real-time progress callbacks (0-100%)
- Support multiple sources (file, RTSP, YouTube, webcam)
- Frame skip for performance tuning
- Stop event for graceful shutdown
- Database persistence with batch inserts
- MinIO image uploads
- Resume from interruption

Usage:
    from services.video_processor import VideoProcessor
    from services.thread_pool_processor import ThreadPoolProcessor
    
    pool = ThreadPoolProcessor(max_workers=4)
    await pool.initialize()
    
    processor = VideoProcessor(thread_pool=pool, frame_skip=30)
    
    stats = await processor.process_video(
        source="video.mp4",
        camera_id="CAM-01",
        video_id="uuid",
        on_progress=lambda pct, cur, total: print(f"{pct}%"),
        stop_event=asyncio.Event(),
    )
"""
import asyncio
import time
import threading
import json
import os
from typing import Optional, Callable, List, Dict, Any, Tuple
from dataclasses import dataclass, field
from pathlib import Path
from collections import defaultdict
import sys
import re

import numpy as np
import cv2

# Add parent directory for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

# Hybrid Tracking
from services.hybrid_tracker import HybridTracker, get_hybrid_tracker

# ==============================================================================
# Resume State Management
# ==============================================================================

@dataclass
class ResumeState:
    """
    Persistent state for video processing resumption.
    
    This class handles saving and loading progress to allow
    resuming video processing after interruptions.
    """
    video_id: str
    source: str
    camera_id: str
    last_processed_frame: int = 0
    total_frames: int = 0
    processed_persons: int = 0
    status: str = "processing"
    timestamp: float = field(default_factory=time.time)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'video_id': self.video_id,
            'source': self.source,
            'camera_id': self.camera_id,
            'last_processed_frame': self.last_processed_frame,
            'total_frames': self.total_frames,
            'processed_persons': self.processed_persons,
            'status': self.status,
            'timestamp': self.timestamp,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ResumeState':
        return cls(**data)
    
    def save(self, resume_dir: str = "resume_states"):
        """Save state to file"""
        Path(resume_dir).mkdir(parents=True, exist_ok=True)
        filepath = Path(resume_dir) / f"{self.video_id}.json"
        with open(filepath, 'w') as f:
            json.dump(self.to_dict(), f)
        print(f"[ResumeState] Saved state to {filepath}")
    
    @classmethod
    def load(cls, video_id: str, resume_dir: str = "resume_states") -> Optional['ResumeState']:
        """Load state from file"""
        filepath = Path(resume_dir) / f"{video_id}.json"
        if not filepath.exists():
            return None
        with open(filepath, 'r') as f:
            data = json.load(f)
        print(f"[ResumeState] Loaded state from {filepath}")
        return cls.from_dict(data)
    
    @classmethod
    def delete(cls, video_id: str, resume_dir: str = "resume_states"):
        """Delete state file"""
        filepath = Path(resume_dir) / f"{video_id}.json"
        if filepath.exists():
            filepath.unlink()
            print(f"[ResumeState] Deleted state file {filepath}")

# Add parent directory for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from services.ai_processing_types import (
    AIProcessingResult,
    PersonDetection,
    VideoProcessingStats,
    ProcessingStatus,
)
from services.thread_pool_processor import ThreadPoolProcessor
from services.frame_processor import FrameProcessor


# Type alias for progress callback
ProgressCallback = Callable[[int, int, int], None]  # (percentage, current_frame, total_frames)


class VideoProcessor:
    """
    Video processor for file-based video analysis.
    
    This class handles:
    1. Video source opening (file, RTSP, YouTube, webcam)
    2. Frame reading with configurable skip
    3. AI processing via ThreadPoolProcessor
    4. Progress reporting for dashboard
    5. Database persistence (batch inserts)
    6. Image uploads to MinIO
    7. Graceful stop handling
    
    Progress Updates:
    - Calls on_progress callback with (percentage, current_frame, total_frames)
    - Percentage calculated as: (current_frame / total_frames) * 100
    - Updates every N frames to avoid overwhelming frontend
    """
    
    def __init__(
        self,
        thread_pool: ThreadPoolProcessor,
        frame_skip: int = 30,
        save_to_db: bool = True,
        save_images: bool = True,
        batch_size: int = 10,
        progress_update_interval: int = 5,  # Update progress every N frames
        use_hybrid_tracking: bool = True,
        use_reader_thread: bool = True,  # Use dedicated reader thread for frame capture
        use_async_db_queue: bool = True,  # Use async queue for DB inserts
    ):
        """
        Initialize VideoProcessor.
        
        Args:
            thread_pool: ThreadPoolProcessor for AI inference
            frame_skip: Process 1 frame every N frames (default: 30 = ~1fps for 30fps video)
            save_to_db: Whether to save detections to database
            save_images: Whether to save images to MinIO
            batch_size: Batch size for database inserts
            progress_update_interval: Update progress callback every N processed frames
            use_hybrid_tracking: Enable hybrid tracking with Re-ID
            use_reader_thread: Use dedicated thread for frame capture (prevents buffer lag)
            use_async_db_queue: Use async queue for non-blocking DB inserts
        """
        self.thread_pool = thread_pool
        self.frame_skip = frame_skip
        self.save_to_db = save_to_db
        self.save_images = save_images
        self.batch_size = batch_size
        self.progress_update_interval = progress_update_interval
        self.use_hybrid_tracking = use_hybrid_tracking
        self.use_reader_thread = use_reader_thread
        self.use_async_db_queue = use_async_db_queue
        
        # Stats tracking
        self._stats = VideoProcessingStats()
        self._lock = threading.Lock()
        
        # Detection batch buffer
        self._detection_batch: List[Dict] = []
        
        # Progress tracking
        self._last_progress_update = 0
        
        # Storage service for MinIO uploads
        self._storage = None
        if self.save_images:
            try:
                from services.storage import StorageService
                self._storage = StorageService()
            except Exception as e:
                print(f"[VideoProcessor] Storage service initialization failed: {e}")
        
        # Hybrid Tracker
        self._hybrid_tracker: Optional[HybridTracker] = None
        if self.use_hybrid_tracking:
            self._hybrid_tracker = get_hybrid_tracker()
        
        # Resume state
        self._resume_state: Optional[ResumeState] = None
        self._resume_dir = "resume_states"
        self._save_state_interval = 100  # Save state every 100 frames
        
        # Async DB Queue
        self._db_queue: Optional[asyncio.Queue] = None
        self._db_inserter_task: Optional[asyncio.Task] = None
        
        # Reader thread variables
        self._reader_thread: Optional[threading.Thread] = None
        self._capture_running = False
        self._latest_frame_data = {"count": 0, "frame": None, "ret": True}
        self._frame_lock = threading.Lock()
    
    def _start_reader_thread(
        self,
        cap: cv2.VideoCapture,
        start_frame: int,
        fps: float,
        stop_event: Optional[asyncio.Event],
    ) -> threading.Thread:
        """
        Start dedicated reader thread for frame capture.
        
        This prevents buffer lag for YouTube/RTSP streams by reading
        frames at the stream's native FPS.
        """
        self._capture_running = True
        self._latest_frame_data = {"count": start_frame, "frame": None, "ret": True}
        
        frame_time = 1.0 / fps if fps > 0 else 0.033
        
        def _reader():
            count = start_frame
            stream_start_time = time.perf_counter()
            frames_read = 0
            last_log_time = time.perf_counter()
            
            print(f"▶️ [Reader] Started from frame {start_frame}")
            
            while self._capture_running:
                if stop_event is not None and stop_event.is_set():
                    print(f"🛑 [Reader] Stop signal received")
                    break
                
                ret, frame = cap.read()
                if not ret:
                    print(f"⚠️ [Reader] cap.read() returned False after {frames_read} frames")
                    with self._frame_lock:
                        self._latest_frame_data["ret"] = False
                    break
                
                frames_read += 1
                
                # Log progress every 5 seconds
                now = time.perf_counter()
                if now - last_log_time > 5.0:
                    print(f"📈 [Reader] Read {frames_read} frames, {frames_read/5:.1f} fps")
                    last_log_time = now
                
                count += 1
                with self._frame_lock:
                    self._latest_frame_data["count"] = count
                    self._latest_frame_data["frame"] = frame
                
                # Pace reading to stream FPS
                frames_processed = count - start_frame
                expected_time = stream_start_time + (frames_processed * frame_time)
                sleep_time = expected_time - time.perf_counter()
                
                if sleep_time > 0:
                    time.sleep(sleep_time)
                elif sleep_time < -1.0:
                    # Reset baseline if lagging too much
                    stream_start_time = time.perf_counter() - (frames_processed * frame_time)
        
        thread = threading.Thread(target=_reader, daemon=True, name=f"VideoReader-{id(self)}")
        thread.start()
        return thread
    
    async def _start_db_inserter(
        self,
        db,
    ) -> asyncio.Task:
        """
        Start async database inserter task.
        
        This runs in background and consumes from the async queue,
        preventing DB inserts from blocking the main processing loop.
        """
        self._db_queue = asyncio.Queue()
        
        async def _inserter():
            from services.database import DatabaseService
            db_thread = DatabaseService()
            batch = []
            
            while True:
                try:
                    # Wait for items with timeout to flush partial batches
                    item = await asyncio.wait_for(self._db_queue.get(), timeout=2.0)
                    
                    if item is None:  # Sentinel to exit
                        break
                    
                    batch.append(item)
                    self._db_queue.task_done()
                    
                    # Flush batch when full
                    if len(batch) >= self.batch_size:
                        await self._flush_batch_async(db_thread, batch)
                        batch.clear()
                        
                except asyncio.TimeoutError:
                    # Flush partial batch on timeout
                    if batch:
                        await self._flush_batch_async(db_thread, batch)
                        batch.clear()
                except Exception as e:
                    print(f"❌ [DB Inserter] Error: {e}")
            
            # Final flush on exit
            if batch:
                await self._flush_batch_async(db_thread, batch)
        
        return asyncio.create_task(_inserter())
    
    async def _flush_batch_async(
        self,
        db,
        batch: List[Dict],
    ):
        """Async version of batch flush for DB inserter."""
        if not batch:
            return
        
        try:
            # Prepare batch data
            batch_data = []
            for detection_data in batch:
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
                    'image_path': detection_data.get('image_path') or '',
                    'video_time_offset': detection_data['frame_number'],
                    'video_id': detection_data['video_id'],
                    'embedding': person.embedding.tolist() if person.embedding is not None else None,
                })
            
            # Run in thread pool
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None,
                db.insert_detections_batch,
                batch_data
            )
            
            self._stats.num_detections_saved += len(batch)
            print(f"✅ [DB Inserter] Batch inserted {len(batch)} detections")
            
        except Exception as e:
            print(f"❌ [DB Inserter] Batch insert error: {e}")
    
    def _apply_hybrid_tracking(
        self,
        camera_id: str,
        person,
        person_crop: Optional[np.ndarray],
        embedder,
    ) -> int:
        """
        Apply hybrid tracking to get persistent track ID.
        
        Args:
            camera_id: Camera identifier
            person: PersonDetection object
            person_crop: Person crop image for Re-ID
            embedder: ClothingEmbedder for feature extraction
        
        Returns:
            Persistent track ID (our_id)
        """
        if not self._hybrid_tracker:
            return person.track_id
        
        # Get ByteTrack ID
        byte_id = person.track_id if person.track_id >= 0 else None
        
        # Match or create track
        our_id, is_new, is_recovered = self._hybrid_tracker.match_or_create_track(
            camera_id=camera_id,
            byte_id=byte_id,
            person_crop=person_crop,
            embedder=embedder,
        )
        
        # Update person track_id to our persistent ID
        person.track_id = our_id
        
        # Store features for future recovery
        if is_new and person_crop is not None and person_crop.size > 0:
            try:
                from src.ai.color_system import analyze_detailed_colors, get_color_groups
                detailed_colors = analyze_detailed_colors(person_crop)
                color_groups = get_color_groups(detailed_colors)
                
                embedding = None
                clothes = []
                if embedder is not None:
                    emb, cloth_names = embedder.get_embedding(person_crop)
                    embedding = emb.tolist() if emb is not None else None
                    clothes = cloth_names if cloth_names else []
                
                self._hybrid_tracker.store_track_features(
                    camera_id=camera_id,
                    our_id=our_id,
                    detailed_colors=detailed_colors,
                    color_groups=color_groups,
                    embedding=embedding,
                    clothes=clothes,
                )
            except Exception as e:
                print(f"⚠️ [HybridTracker] Error storing features: {e}")
        
        return our_id
    
    async def process_video(
        self,
        source: str,
        camera_id: str,
        video_id: Optional[str] = None,
        start_frame: int = 0,
        on_progress: Optional[ProgressCallback] = None,
        on_detection: Optional[Callable[[PersonDetection, int], None]] = None,
        stop_event: Optional[asyncio.Event] = None,
        save_to_db: Optional[bool] = None,
        save_images: Optional[bool] = None,
        frame_skip: Optional[int] = None,
    ) -> VideoProcessingStats:
        """
        Process a video file or stream.
        
        This is the main entry point for video processing. It:
        1. Opens the video source
        2. Reads frames with frame_skip
        3. Processes frames via ThreadPoolProcessor
        4. Reports progress via callback
        5. Saves results to database (if enabled)
        6. Handles stop events gracefully
        
        Args:
            source: Video source (file path, RTSP URL, YouTube URL, or webcam index)
            camera_id: Camera identifier for database
            video_id: Optional video ID for database tracking
            start_frame: Frame number to start from (for resume)
            on_progress: Callback(percentage, current_frame, total_frames)
            on_detection: Callback(detection, frame_number) for real-time updates
            stop_event: asyncio.Event to signal graceful stop
            save_to_db: Override default database saving option
            save_images: Override default image saving option
            frame_skip: Override default frame skip for this run
        
        Returns:
            VideoProcessingStats with processing results
        """
        start_time = time.perf_counter()
        
        # Use provided save options or fall back to instance defaults
        should_save_db = save_to_db if save_to_db is not None else self.save_to_db
        should_save_images = save_images if save_images is not None else self.save_images
        effective_frame_skip = max(1, frame_skip if frame_skip is not None else self.frame_skip)

        if should_save_images and self._storage is None:
            try:
                from services.storage import StorageService
                self._storage = StorageService()
            except Exception as e:
                print(f"[VideoProcessor] Storage service initialization failed: {e}")
        
        # Load resume state if available
        self._resume_state = None
        if video_id:
            self._resume_state = ResumeState.load(video_id, self._resume_dir)
            if self._resume_state and start_frame == 0:
                # Resume from saved state
                start_frame = self._resume_state.last_processed_frame
                print(f"[VideoProcessor] Resuming from frame {start_frame}")
        
        # Initialize stats
        self._stats = VideoProcessingStats(
            video_id=video_id,
            camera_id=camera_id,
            status=ProcessingStatus.PROCESSING,
        )
        
        # Create initial resume state
        if video_id:
            self._resume_state = ResumeState(
                video_id=video_id,
                source=source,
                camera_id=camera_id,
                last_processed_frame=start_frame,
                status="processing",
            )
        
        try:
            # Resolve video source (handle YouTube URLs)
            resolved_source = self._resolve_source(source)
            
            # Open video
            cap = cv2.VideoCapture(resolved_source)
            if not cap.isOpened():
                raise ValueError(f"Cannot open video source: {source}")
            
            # Get video info
            fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
            total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            
            # Handle live streams (no frame count)
            if total_frames <= 0:
                total_frames = 0  # Unknown/ streaming
            
            # Update stats
            self._stats.total_frames = total_frames
            self._stats.fps = fps
            self._stats.image_width = width
            self._stats.image_height = height
            
            print(f"[VideoProcessor] Video: {width}x{height}, FPS: {fps:.2f}, Frames: {total_frames}")
            print(f"[VideoProcessor] Frame skip: {effective_frame_skip}, Processing ~1/{effective_frame_skip} frames")
            
            # Seek to start frame if resuming
            if start_frame > 0 and total_frames > 0:
                cap.set(cv2.CAP_PROP_POS_FRAMES, start_frame)
                print(f"[VideoProcessor] Resuming from frame {start_frame}")
            
            # Initialize database if needed
            db = None
            if should_save_db and video_id:
                from services.database import DatabaseService
                db = DatabaseService()
                db.update_video_status(video_id, "processing")
            
            # Initialize embedder for hybrid tracking
            embedder = None
            if self.use_hybrid_tracking:
                try:
                    from src.ai.feature_extractor import ClothingEmbedder
                    from src.config_loader import get_classifier_model_path, get_device
                    model_path = get_classifier_model_path()
                    if os.path.exists(model_path):
                        device = get_device()
                        embedder = ClothingEmbedder(model_path=model_path, device=device)
                        print(f"✅ [VideoProcessor] ClothingEmbedder loaded for Re-ID (device: {device})")
                except Exception as e:
                    print(f"⚠️ [VideoProcessor] Embedder initialization failed: {e}")
            
            # Start async DB inserter if enabled
            if self.use_async_db_queue and should_save_db:
                self._db_inserter_task = await self._start_db_inserter(db)
                print(f"✅ [VideoProcessor] Async DB inserter started")
            
            # Start reader thread if enabled (prevents buffer lag for streams)
            if self.use_reader_thread:
                self._reader_thread = self._start_reader_thread(cap, start_frame, fps, stop_event)
                print(f"✅ [VideoProcessor] Reader thread started")
            
            # Process frames
            frame_number = start_frame
            processed_count = 0
            
            # Track last processed frame for reader thread mode
            last_processed_frame = start_frame - effective_frame_skip
            
            while True:
                # Check stop event
                if stop_event and stop_event.is_set():
                    print(f"[VideoProcessor] Stop requested at frame {frame_number}")
                    self._stats.status = ProcessingStatus.STOPPED
                    break
                
                # Read frame (use reader thread if enabled)
                if self.use_reader_thread:
                    with self._frame_lock:
                        ret = self._latest_frame_data["ret"]
                        frame_count = self._latest_frame_data["count"]
                        frame = self._latest_frame_data["frame"].copy() if self._latest_frame_data["frame"] is not None else None
                    
                    if not ret:
                        print(f"🛑 [VideoProcessor] Reader thread signaled end of stream")
                        break
                    
                    # Only process if we've advanced enough frames
                    if frame_count - last_processed_frame < effective_frame_skip:
                        await asyncio.sleep(0.005)  # Small delay to prevent busy loop
                        continue
                    
                    # Calculate which frame we should report as processed
                    frame_number = last_processed_frame + effective_frame_skip
                    last_processed_frame = frame_number
                else:
                    # Direct read from capture
                    ret, frame = cap.read()
                    if not ret:
                        break
                    
                    # Skip frames (only process every Nth frame)
                    if (frame_number - start_frame) % effective_frame_skip != 0:
                        frame_number += 1
                        continue
                    frame_number += 1
                
                # Process frame with stop event checking
                try:
                    result = await self._process_frame_with_timeout(
                        frame, frame_number, stop_event=stop_event, timeout=3.0
                    )
                    
                    # Check if stopped during processing
                    if result.status == ProcessingStatus.STOPPED:
                        print(f"[VideoProcessor] Processing stopped at frame {frame_number}")
                        self._stats.status = ProcessingStatus.STOPPED
                        break
                    
                    processed_count += 1
                    
                    # Handle detections
                    if result.detections:
                        for idx, person in enumerate(result.detections):
                            # Check stop event periodically during detection handling
                            if stop_event and stop_event.is_set():
                                print(f"[VideoProcessor] Stop requested during detection processing at frame {frame_number}")
                                self._stats.status = ProcessingStatus.STOPPED
                                break
                            # Update stats
                            self._stats.num_persons_detected += 1
                            
                            # Apply hybrid tracking if enabled
                            person_crop = None
                            if self.use_hybrid_tracking and person.bbox:
                                x, y = max(0, person.bbox.x), max(0, person.bbox.y)
                                x2 = min(frame.shape[1], person.bbox.x + person.bbox.width)
                                y2 = min(frame.shape[0], person.bbox.y + person.bbox.height)
                                if x2 > x and y2 > y:
                                    person_crop = frame[y:y2, x:x2]
                                    self._apply_hybrid_tracking(camera_id, person, person_crop, embedder)
                            
                            # Call detection callback
                            if on_detection:
                                on_detection(person, frame_number)
                            
                            # Add to batch/queue for database
                            if should_save_db:
                                # Upload image to MinIO if enabled
                                image_path = None
                                if should_save_images and self._storage and person.bbox:
                                    try:
                                        if person_crop is None:
                                            x = max(0, person.bbox.x)
                                            y = max(0, person.bbox.y)
                                            x2 = min(frame.shape[1], person.bbox.x + person.bbox.width)
                                            y2 = min(frame.shape[0], person.bbox.y + person.bbox.height)
                                            if x2 > x and y2 > y:
                                                person_crop = frame[y:y2, x:x2]
                                        
                                        if person_crop is not None:
                                            import uuid
                                            filename = f"{camera_id}/{video_id or 'stream'}/{frame_number}_{uuid.uuid4().hex[:8]}.jpg"
                                            loop = asyncio.get_event_loop()
                                            image_path = await loop.run_in_executor(
                                                None, self._storage.upload_image, person_crop, filename
                                            )
                                            if image_path:
                                                print(f"[VideoProcessor] Uploaded image: {image_path}")
                                                if self.use_hybrid_tracking and self._hybrid_tracker:
                                                    self._hybrid_tracker.store_image_path(
                                                        camera_id, person.track_id, "image_path", image_path
                                                    )
                                    except Exception as e:
                                        print(f"[VideoProcessor] Image upload error: {e}")
                                
                                # Add to async queue or batch
                                detection_data = {
                                    'person': person,
                                    'frame_number': frame_number,
                                    'camera_id': camera_id,
                                    'video_id': video_id,
                                    'image_path': image_path,
                                }
                                
                                if self.use_async_db_queue and self._db_queue:
                                    await self._db_queue.put(detection_data)
                                else:
                                    self._detection_batch.append(detection_data)
                    
                    # Report progress
                    if on_progress and total_frames > 0:
                        percentage = min(100, int((frame_number / total_frames) * 100))
                        
                        # Throttle updates
                        if percentage >= self._last_progress_update + self.progress_update_interval or percentage == 100:
                            on_progress(percentage, frame_number, total_frames)
                            self._last_progress_update = percentage
                    
                    # Save batch to database periodically
                    if len(self._detection_batch) >= self.batch_size:
                        await self._flush_batch(db)
                    
                    # Save resume state periodically (for interruption recovery)
                    if video_id and self._resume_state and frame_number % self._save_state_interval == 0:
                        self._resume_state.last_processed_frame = frame_number
                        self._resume_state.total_frames = total_frames
                        self._resume_state.processed_persons = self._stats.num_persons_detected
                        self._resume_state.save(self._resume_dir)
                
                except Exception as e:
                    print(f"[VideoProcessor] Error processing frame {frame_number}: {e}")
                    self._stats.num_errors += 1
                
                frame_number += 1
            
            # Cleanup
            self._capture_running = False
            if self._reader_thread:
                self._reader_thread.join(timeout=2.0)
                print(f"🧹 [VideoProcessor] Reader thread stopped")
            
            cap.release()
            
            # Signal DB inserter to stop and flush remaining items
            if self.use_async_db_queue and self._db_queue:
                await self._db_queue.put(None)  # Sentinel
                if self._db_inserter_task:
                    await self._db_inserter_task
                    print(f"🧹 [VideoProcessor] DB inserter stopped")
            
            # Flush remaining batch (for non-async mode)
            if self._detection_batch:
                await self._flush_batch(db)
            
            # Cleanup hybrid tracker
            if self.use_hybrid_tracking and self._hybrid_tracker:
                self._hybrid_tracker.cleanup(camera_id)
            
            # Update final stats
            self._stats.processed_frames = processed_count
            self._stats.skipped_frames = frame_number - start_frame - processed_count
            self._stats.processing_time_ms = (time.perf_counter() - start_time) * 1000
            
            if self._stats.status != ProcessingStatus.STOPPED:
                self._stats.status = ProcessingStatus.SUCCESS if self._stats.num_errors == 0 else ProcessingStatus.PARTIAL
            
            # Update database status
            if db and video_id:
                final_status = "completed" if self._stats.status == ProcessingStatus.SUCCESS else "failed"
                db.update_video_status(video_id, final_status)
            
            print(f"[VideoProcessor] Done. Processed {processed_count} frames, "
                  f"found {self._stats.num_persons_detected} persons, "
                  f"time: {self._stats.processing_time_ms/1000:.2f}s")
            
            # Clean up resume state on successful completion
            if video_id and self._stats.status == ProcessingStatus.SUCCESS:
                ResumeState.delete(video_id, self._resume_dir)
                print(f"[VideoProcessor] Resume state cleaned up for {video_id}")
            
            return self._stats
            
        except Exception as e:
            print(f"[VideoProcessor] Fatal error: {e}")
            self._stats.status = ProcessingStatus.ERROR
            self._stats.error_message = str(e)
            self._stats.processing_time_ms = (time.perf_counter() - start_time) * 1000
            
            # Update database status on error
            if should_save_db and video_id:
                try:
                    from services.database import DatabaseService
                    db = DatabaseService()
                    db.update_video_status(video_id, "failed")
                except:
                    pass
            
            # Save error state for resume (if interrupted, not a fatal error)
            if video_id and self._resume_state:
                self._resume_state.status = "error"
                self._resume_state.save(self._resume_dir)
                print(f"[VideoProcessor] Resume state saved for error recovery: {video_id}")
            
            return self._stats
    
    def _resolve_source(self, source: str) -> str:
        """
        Resolve video source (handle YouTube URLs, webcam indices).
        
        Args:
            source: Original source string
        
        Returns:
            Resolved source for VideoCapture
        """
        # Check if it's a YouTube URL
        if isinstance(source, str) and ('youtube.com' in source or 'youtu.be' in source):
            try:
                import re
                import yt_dlp
                
                print(f"[VideoProcessor] Resolving YouTube URL: {source}")
                
                ydl_opts = {
                    'format': 'best[ext=mp4]/best',
                    'quiet': True,
                    'no_warnings': True,
                }
                
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(source, download=False)
                    resolved = info.get('url', source)
                
                print(f"[VideoProcessor] YouTube resolved successfully")
                return resolved
                
            except Exception as e:
                print(f"[VideoProcessor] Failed to resolve YouTube URL: {e}")
                raise
        
        # Check if it's a webcam index
        if isinstance(source, str) and source.isdigit():
            return int(source)
        
        return source
    
    async def _process_frame_with_timeout(
        self, 
        frame: np.ndarray, 
        frame_number: int,
        stop_event: Optional[asyncio.Event] = None,
        timeout: float = 5.0
    ) -> AIProcessingResult:
        """
        Process a single frame with periodic stop checks.
        
        Uses timeout to allow checking stop event periodically.
        If processing times out, it will retry until complete or stopped.
        
        Args:
            frame: OpenCV frame
            frame_number: Frame number
            stop_event: Optional stop event to check
            timeout: Timeout per attempt in seconds
        
        Returns:
            AIProcessingResult
        """
        start_time = time.time()
        max_total_time = 60.0  # Maximum 60 seconds total per frame
        
        while True:
            # Check if we should stop
            if stop_event and stop_event.is_set():
                return AIProcessingResult(
                    status=ProcessingStatus.STOPPED,
                    frame_number=frame_number,
                    error_message="Processing stopped by request"
                )
            
            # Check if we've exceeded max total time
            if time.time() - start_time > max_total_time:
                return AIProcessingResult(
                    status=ProcessingStatus.TIMEOUT,
                    frame_number=frame_number,
                    error_message=f"Processing exceeded {max_total_time}s limit"
                )
            
            try:
                # Try processing with timeout
                result = await self.thread_pool.process_frame(
                    frame,
                    frame_number=frame_number,
                    timestamp=time.time(),
                    timeout=timeout,
                )
                
                # If successful, return result
                if result.status != ProcessingStatus.TIMEOUT:
                    return result
                
                # If timed out but not stopped, retry
                print(f"[VideoProcessor] Frame {frame_number} processing timed out, retrying...")
                await asyncio.sleep(0.1)  # Brief pause before retry
                
            except Exception as e:
                return AIProcessingResult(
                    status=ProcessingStatus.ERROR,
                    frame_number=frame_number,
                    error_message=str(e)
                )
    
    async def _process_frame(self, frame: np.ndarray, frame_number: int) -> AIProcessingResult:
        """
        Process a single frame using ThreadPoolProcessor.
        
        Args:
            frame: OpenCV frame
            frame_number: Frame number
        
        Returns:
            AIProcessingResult
        """
        # Use thread pool for processing (backward compatibility)
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
        camera_id: str,
        video_id: Optional[str],
        image_path: Optional[str] = None,
    ):
        """
        Add detection to batch for database insert.
        
        Args:
            person: PersonDetection object
            frame_number: Frame number
            camera_id: Camera ID
            video_id: Video ID
            image_path: Path to uploaded image in MinIO (optional)
        """
        detection_data = {
            'person': person,
            'frame_number': frame_number,
            'camera_id': camera_id,
            'video_id': video_id,
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
                    'video_id': detection_data['video_id'],
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
            print(f"[VideoProcessor] Batch inserted {len(self._detection_batch)} detections")
            
        except Exception as e:
            print(f"[VideoProcessor] Database batch insert error: {e}")
            self._stats.num_errors += 1
        
        finally:
            # Clear batch
            self._detection_batch.clear()
    
    def get_stats(self) -> VideoProcessingStats:
        """
        Get current processing stats.
        
        Returns:
            VideoProcessingStats
        """
        return self._stats


# ==============================================================================
# Convenience Functions
# ==============================================================================

async def process_video_file(
    video_path: str,
    camera_id: str,
    video_id: Optional[str] = None,
    on_progress: Optional[ProgressCallback] = None,
    stop_event: Optional[asyncio.Event] = None,
    frame_skip: int = 30,
    save_to_db: bool = True,
) -> VideoProcessingStats:
    """
    Convenience function for one-off video processing.
    
    Creates VideoProcessor with default settings and processes video.
    
    Args:
        video_path: Path to video file
        camera_id: Camera identifier
        video_id: Optional video ID for tracking
        on_progress: Progress callback
        stop_event: Stop event
        frame_skip: Frame skip interval
        save_to_db: Whether to save to database
    
    Returns:
        VideoProcessingStats
    """
    # Create thread pool
    pool = ThreadPoolProcessor(max_workers=4)
    await pool.initialize()
    
    try:
        # Create processor and process
        processor = VideoProcessor(
            thread_pool=pool,
            frame_skip=frame_skip,
            save_to_db=save_to_db,
        )
        
        stats = await processor.process_video(
            source=video_path,
            camera_id=camera_id,
            video_id=video_id,
            on_progress=on_progress,
            stop_event=stop_event,
        )
        
        return stats
        
    finally:
        await pool.shutdown()


# ==============================================================================
# Progress Helper for Frontend
# ==============================================================================

class ProgressTracker:
    """
    Helper class for tracking and reporting video processing progress.
    
    This can be used to store progress in memory or Redis for dashboard access.
    """
    
    def __init__(self):
        self._progress: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.Lock()
    
    def update_progress(
        self,
        video_id: str,
        percentage: int,
        current_frame: int,
        total_frames: int,
        status: str = "processing",
        message: str = "",
    ):
        """
        Update progress for a video.
        
        Args:
            video_id: Video identifier
            percentage: 0-100
            current_frame: Current frame number
            total_frames: Total frames
            status: Status message
            message: Additional info
        """
        with self._lock:
            self._progress[video_id] = {
                'percentage': percentage,
                'current_frame': current_frame,
                'total_frames': total_frames,
                'status': status,
                'message': message,
                'timestamp': time.time(),
            }
    
    def get_progress(self, video_id: str) -> Optional[Dict[str, Any]]:
        """
        Get progress for a video.
        
        Args:
            video_id: Video identifier
        
        Returns:
            Progress dict or None
        """
        with self._lock:
            return self._progress.get(video_id)
    
    def remove_progress(self, video_id: str):
        """Remove progress entry"""
        with self._lock:
            self._progress.pop(video_id, None)
    
    def create_callback(self, video_id: str) -> ProgressCallback:
        """
        Create a progress callback for use with VideoProcessor.
        
        Args:
            video_id: Video identifier
        
        Returns:
            Progress callback function
        """
        def callback(percentage: int, current_frame: int, total_frames: int):
            self.update_progress(
                video_id=video_id,
                percentage=percentage,
                current_frame=current_frame,
                total_frames=total_frames,
                status="processing",
                message=f"Processing frame {current_frame}/{total_frames}",
            )
        
        return callback


# Global progress tracker instance
_global_progress_tracker = ProgressTracker()


def get_progress_tracker() -> ProgressTracker:
    """Get global progress tracker instance"""
    return _global_progress_tracker
