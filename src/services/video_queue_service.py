"""
video_queue_service.py - Multi-Video Queue Management Service

This module provides the VideoQueueService class for managing multiple videos
with queue support, status tracking, and global status display.

Key Features:
- Queue management for multiple videos (pending, processing, paused, completed, failed)
- Reorder queue (move videos up/down in priority)
- Pause/resume processing
- Remove videos from queue
- Global status dashboard showing all videos
- Integration with existing VideoProcessor

Usage:
    from services.video_queue_service import VideoQueueService
    
    queue_service = VideoQueueService()
    
    # Add video to queue
    job_id = await queue_service.add_video(
        source="video.mp4",
        camera_id="CAM-01",
        display_mode="background",
        options={...}
    )
    
    # Start processing queue
    await queue_service.start_processing()
    
    # Get global status
    status = queue_service.get_global_status()
    
    # Reorder queue
    await queue_service.reorder_queue(job_id, new_position=0)
    
    # Pause specific video
    await queue_service.pause_job(job_id)
    
    # Resume specific video
    await queue_service.resume_job(job_id)
    
    # Remove from queue
    await queue_service.remove_job(job_id)
"""
import asyncio
import time
import threading
import uuid
from typing import Optional, Dict, List, Any, Callable
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
from pathlib import Path
import sys
import json

# Add parent directory for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from services.database import DatabaseService

# Import background task processor
from services.background_processor import process_video_background_task, get_background_task_status, _BACKGROUND_PROCESSING_STATE


class JobStatus(Enum):
    """Video processing job status"""
    PENDING = "pending"         # Waiting in queue
    PROCESSING = "processing"   # Currently being processed
    PAUSED = "paused"           # Paused by user
    COMPLETED = "completed"     # Finished successfully
    FAILED = "failed"         # Error occurred
    STOPPED = "stopped"         # Stopped by user
    CANCELLED = "cancelled"     # Cancelled before processing


@dataclass
class VideoJob:
    """Represents a video processing job in the queue"""
    id: str
    source: str                           # Video file path or URL
    camera_id: str
    display_mode: str = "background"      # web, cv2, background
    status: JobStatus = JobStatus.PENDING
    priority: int = 0                     # Higher = earlier in queue
    created_at: float = field(default_factory=time.time)
    started_at: Optional[float] = None
    completed_at: Optional[float] = None
    progress_pct: int = 0
    frames_processed: int = 0
    total_frames: int = 0
    detections_count: int = 0
    error_message: Optional[str] = None
    # Processing options
    save_to_db: bool = True
    save_images: bool = True
    save_bbox_images: bool = True
    frame_skip: int = 5
    show_detector_bbox: bool = True
    show_detector_track_id: bool = True
    show_classifier_class_name: bool = True
    classifier_top_n: int = 2
    # Original filename (for display)
    original_filename: Optional[str] = None
    # Video metadata
    width: Optional[int] = None
    height: Optional[int] = None
    fps: Optional[float] = None
    duration_sec: Optional[float] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization"""
        return {
            "id": self.id,
            "source": self.source,
            "camera_id": self.camera_id,
            "display_mode": self.display_mode,
            "status": self.status.value,
            "priority": self.priority,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "progress_pct": self.progress_pct,
            "frames_processed": self.frames_processed,
            "total_frames": self.total_frames,
            "detections_count": self.detections_count,
            "error_message": self.error_message,
            "save_to_db": self.save_to_db,
            "save_images": self.save_images,
            "save_bbox_images": self.save_bbox_images,
            "frame_skip": self.frame_skip,
            "show_detector_bbox": self.show_detector_bbox,
            "show_detector_track_id": self.show_detector_track_id,
            "show_classifier_class_name": self.show_classifier_class_name,
            "classifier_top_n": self.classifier_top_n,
            "original_filename": self.original_filename,
            "width": self.width,
            "height": self.height,
            "fps": self.fps,
            "duration_sec": self.duration_sec,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'VideoJob':
        """Create from dictionary"""
        job = cls(
            id=data["id"],
            source=data["source"],
            camera_id=data["camera_id"],
            display_mode=data.get("display_mode", "background"),
            status=JobStatus(data.get("status", "pending")),
            priority=data.get("priority", 0),
            created_at=data.get("created_at", time.time()),
            started_at=data.get("started_at"),
            completed_at=data.get("completed_at"),
            progress_pct=data.get("progress_pct", 0),
            frames_processed=data.get("frames_processed", 0),
            total_frames=data.get("total_frames", 0),
            detections_count=data.get("detections_count", 0),
            error_message=data.get("error_message"),
            save_to_db=data.get("save_to_db", True),
            save_images=data.get("save_images", True),
            save_bbox_images=data.get("save_bbox_images", True),
            frame_skip=data.get("frame_skip", 5),
            show_detector_bbox=data.get("show_detector_bbox", True),
            show_detector_track_id=data.get("show_detector_track_id", True),
            show_classifier_class_name=data.get("show_classifier_class_name", True),
            classifier_top_n=data.get("classifier_top_n", 2),
            original_filename=data.get("original_filename"),
            width=data.get("width"),
            height=data.get("height"),
            fps=data.get("fps"),
            duration_sec=data.get("duration_sec"),
        )
        return job


class VideoQueueService:
    """
    Service for managing multiple video processing jobs with queue support.
    
    This class provides:
    - Queue management (add, remove, reorder)
    - Status tracking for each video
    - Global status dashboard
    - Pause/resume functionality
    - Integration with VideoProcessor for actual processing
    """
    
    def __init__(self, max_concurrent: int = 1):
        """
        Initialize VideoQueueService.
        
        Args:
            max_concurrent: Maximum number of videos to process simultaneously
                          (default 1 for sequential processing)
        """
        self.max_concurrent = max_concurrent
        self._jobs: Dict[str, VideoJob] = {}
        self._queue_order: List[str] = []  # Ordered list of pending job IDs
        self._current_job_id: Optional[str] = None
        self._stop_event: Optional[asyncio.Event] = None
        self._processing_task: Optional[asyncio.Task] = None
        self._lock = threading.RLock()
        self._db = DatabaseService()
        
        # Callbacks for status updates
        self._status_callbacks: List[Callable[[str, Dict], None]] = []
        
        # Setup database table
        self._setup_database()

        # Load existing jobs from database
        self._load_jobs_from_db()
    
    def _setup_database(self):
        """Setup video_queue table in database"""
        try:
            with self._db.conn.cursor() as cur:
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS video_queue (
                        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                        job_id VARCHAR(100) UNIQUE NOT NULL,
                        source TEXT NOT NULL,
                        camera_id VARCHAR(50) NOT NULL,
                        display_mode VARCHAR(20) DEFAULT 'background',
                        status VARCHAR(20) DEFAULT 'pending',
                        priority INT DEFAULT 0,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        started_at TIMESTAMP,
                        completed_at TIMESTAMP,
                        progress_pct INT DEFAULT 0,
                        frames_processed INT DEFAULT 0,
                        total_frames INT DEFAULT 0,
                        detections_count INT DEFAULT 0,
                        error_message TEXT,
                        options JSONB DEFAULT '{}',
                        video_metadata JSONB DEFAULT '{}'
                    )
                """)
                
                # Create index for efficient status queries
                cur.execute("CREATE INDEX IF NOT EXISTS idx_video_queue_status ON video_queue(status)")
                cur.execute("CREATE INDEX IF NOT EXISTS idx_video_queue_priority ON video_queue(priority)")
                cur.execute("CREATE INDEX IF NOT EXISTS idx_video_queue_job_id ON video_queue(job_id)")
                
                self._db.conn.commit()
        except Exception as e:
            print(f"[VideoQueueService] Database setup error: {e}")
            self._db.conn.rollback()
    
    def _save_job_to_db(self, job: VideoJob):
        """Save job to database"""
        try:
            options = {
                "save_to_db": job.save_to_db,
                "save_images": job.save_images,
                "save_bbox_images": job.save_bbox_images,
                "frame_skip": job.frame_skip,
                "show_detector_bbox": job.show_detector_bbox,
                "show_detector_track_id": job.show_detector_track_id,
                "show_classifier_class_name": job.show_classifier_class_name,
                "classifier_top_n": job.classifier_top_n,
            }
            
            metadata = {
                "original_filename": job.original_filename,
                "width": job.width,
                "height": job.height,
                "fps": job.fps,
                "duration_sec": job.duration_sec,
            }
            
            with self._db.conn.cursor() as cur:
                # Convert timestamps
                started_at = datetime.fromtimestamp(job.started_at) if job.started_at else None
                completed_at = datetime.fromtimestamp(job.completed_at) if job.completed_at else None
                
                cur.execute("""
                    INSERT INTO video_queue (
                        job_id, source, camera_id, display_mode, status, priority,
                        created_at, started_at, completed_at, progress_pct,
                        frames_processed, total_frames, detections_count,
                        error_message, options, video_metadata
                    ) VALUES (%s, %s, %s, %s, %s, %s, to_timestamp(%s), %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (job_id) DO UPDATE SET
                        status = EXCLUDED.status,
                        priority = EXCLUDED.priority,
                        started_at = EXCLUDED.started_at,
                        completed_at = EXCLUDED.completed_at,
                        progress_pct = EXCLUDED.progress_pct,
                        frames_processed = EXCLUDED.frames_processed,
                        total_frames = EXCLUDED.total_frames,
                        detections_count = EXCLUDED.detections_count,
                        error_message = EXCLUDED.error_message,
                        options = EXCLUDED.options,
                        video_metadata = EXCLUDED.video_metadata
                """, (
                    job.id, job.source, job.camera_id, job.display_mode,
                    job.status.value, job.priority, job.created_at,
                    started_at, completed_at, job.progress_pct,
                    job.frames_processed, job.total_frames, job.detections_count,
                    job.error_message, json.dumps(options), json.dumps(metadata)
                ))
                self._db.conn.commit()
        except Exception as e:
            print(f"[VideoQueueService] Error saving job to DB: {e}")
            self._db.conn.rollback()
    
    def _delete_job_from_db(self, job_id: str):
        """Delete job from database"""
        try:
            with self._db.conn.cursor() as cur:
                cur.execute("DELETE FROM video_queue WHERE job_id = %s", (job_id,))
                self._db.conn.commit()
        except Exception as e:
            print(f"[VideoQueueService] Error deleting job from DB: {e}")
            self._db.conn.rollback()

    def _load_jobs_from_db(self):
        """Load existing pending and paused jobs from database on startup"""
        try:
            with self._db.conn.cursor() as cur:
                cur.execute("""
                    SELECT job_id, source, camera_id, display_mode, status, priority,
                           created_at, started_at, completed_at, progress_pct,
                           frames_processed, total_frames, detections_count,
                           error_message, options, video_metadata
                    FROM video_queue
                    WHERE status IN ('pending', 'paused', 'processing', 'stopped')
                """)
                rows = cur.fetchall()

                for row in rows:
                    (job_id, source, camera_id, display_mode, status, priority,
                     created_at, started_at, completed_at, progress_pct,
                     frames_processed, total_frames, detections_count,
                     error_message, options, metadata) = row

                    job_data = {
                        "id": job_id,
                        "source": source,
                        "camera_id": camera_id,
                        "display_mode": display_mode,
                        "status": status,
                        "priority": priority,
                        "created_at": created_at.timestamp() if created_at else time.time(),
                        "started_at": started_at.timestamp() if started_at else None,
                        "completed_at": completed_at.timestamp() if completed_at else None,
                        "progress_pct": progress_pct,
                        "frames_processed": frames_processed,
                        "total_frames": total_frames,
                        "detections_count": detections_count,
                        "error_message": error_message,
                    }

                    # Merge options and metadata
                    if options:
                        job_data.update(options)
                    if metadata:
                        job_data.update(metadata)

                    job = VideoJob.from_dict(job_data)

                    # Handle processing jobs that were interrupted - convert to paused
                    if job.status == JobStatus.PROCESSING:
                        job.status = JobStatus.PAUSED
                        print(f"[VideoQueueService] Converted interrupted job {job_id} from processing to paused")
                        # Save the status change to database immediately
                        self._save_job_to_db(job)

                    self._jobs[job_id] = job

                    # Only add pending, paused, and stopped jobs to queue order
                    if job.status in [JobStatus.PENDING, JobStatus.PAUSED, JobStatus.STOPPED]:
                        # Insert based on priority
                        inserted = False
                        for i, existing_id in enumerate(self._queue_order):
                            existing_job = self._jobs[existing_id]
                            if job.priority > existing_job.priority:
                                self._queue_order.insert(i, job_id)
                                inserted = True
                                break
                        if not inserted:
                            self._queue_order.append(job_id)

                print(f"[VideoQueueService] Loaded {len(rows)} jobs from database ({len(self._queue_order)} in queue)")

        except Exception as e:
            print(f"[VideoQueueService] Error loading jobs from DB: {e}")

    async def add_video(
        self,
        source: str,
        camera_id: str,
        display_mode: str = "background",
        priority: int = 0,
        original_filename: Optional[str] = None,
        width: Optional[int] = None,
        height: Optional[int] = None,
        fps: Optional[float] = None,
        duration_sec: Optional[float] = None,
        **options
    ) -> str:
        """
        Add a video to the processing queue.
        
        Args:
            source: Video file path or URL
            camera_id: Camera identifier
            display_mode: Processing mode (web, cv2, background)
            priority: Queue priority (higher = earlier in queue)
            original_filename: Original filename for display
            width: Video width
            height: Video height
            fps: Video FPS
            duration_sec: Video duration
            **options: Additional processing options
            
        Returns:
            Job ID (UUID string)
        """
        job_id = str(uuid.uuid4())
        
        job = VideoJob(
            id=job_id,
            source=source,
            camera_id=camera_id,
            display_mode=display_mode,
            priority=priority,
            original_filename=original_filename or Path(source).name,
            width=width,
            height=height,
            fps=fps,
            duration_sec=duration_sec,
            save_to_db=options.get("save_to_db", True),
            save_images=options.get("save_images", True),
            save_bbox_images=options.get("save_bbox_images", True),
            frame_skip=options.get("frame_skip", 5),
            show_detector_bbox=options.get("show_detector_bbox", True),
            show_detector_track_id=options.get("show_detector_track_id", True),
            show_classifier_class_name=options.get("show_classifier_class_name", True),
            classifier_top_n=options.get("classifier_top_n", 2),
        )
        
        with self._lock:
            self._jobs[job_id] = job
            # Insert at correct position based on priority
            inserted = False
            for i, existing_id in enumerate(self._queue_order):
                existing_job = self._jobs[existing_id]
                if job.priority > existing_job.priority:
                    self._queue_order.insert(i, job_id)
                    inserted = True
                    break
            if not inserted:
                self._queue_order.append(job_id)
        
        # Save to database
        self._save_job_to_db(job)
        
        print(f"[VideoQueueService] Added job {job_id} for {camera_id} (priority: {priority})")
        
        # Notify status change
        self._notify_status_change(job_id)
        
        return job_id
    
    async def remove_job(self, job_id: str) -> bool:
        """
        Remove a job from the queue.
        
        Can only remove jobs that are pending or paused.
        Processing jobs must be stopped first.
        
        Args:
            job_id: Job ID to remove
            
        Returns:
            True if removed successfully
        """
        with self._lock:
            if job_id not in self._jobs:
                return False
            
            job = self._jobs[job_id]
            
            # Cannot remove processing jobs
            if job.status == JobStatus.PROCESSING:
                print(f"[VideoQueueService] Cannot remove job {job_id}: currently processing")
                return False
            
            # Update status to cancelled
            job.status = JobStatus.CANCELLED
            job.completed_at = time.time()
            
            # Remove from queue order
            if job_id in self._queue_order:
                self._queue_order.remove(job_id)
            
            # Remove from jobs dict
            del self._jobs[job_id]
        
        # Delete from database
        self._delete_job_from_db(job_id)
        
        print(f"[VideoQueueService] Removed job {job_id}")
        return True
    
    async def reorder_queue(self, job_id: str, new_position: int) -> bool:
        """
        Reorder a job in the queue by moving it to a new position.
        
        Args:
            job_id: Job ID to move
            new_position: New position in queue (0 = first)
            
        Returns:
            True if reordered successfully
        """
        with self._lock:
            if job_id not in self._jobs:
                return False
            
            job = self._jobs[job_id]
            
            # Can only reorder pending or paused jobs
            if job.status not in [JobStatus.PENDING, JobStatus.PAUSED]:
                print(f"[VideoQueueService] Cannot reorder job {job_id}: status is {job.status.value}")
                return False
            
            # Remove from current position
            if job_id in self._queue_order:
                self._queue_order.remove(job_id)
            
            # Clamp position
            new_position = max(0, min(new_position, len(self._queue_order)))
            
            # Insert at new position
            self._queue_order.insert(new_position, job_id)
            
            # Update priority (inverse of position for consistency)
            job.priority = len(self._queue_order) - new_position
        
        # Save to database
        self._save_job_to_db(job)
        
        print(f"[VideoQueueService] Reordered job {job_id} to position {new_position}")
        
        self._notify_status_change(job_id)
        return True
    
    async def pause_job(self, job_id: str) -> bool:
        """
        Pause a processing job.
        
        Args:
            job_id: Job ID to pause
            
        Returns:
            True if paused successfully (idempotent - returns True if already paused)
        """
        with self._lock:
            if job_id not in self._jobs:
                return False
            
            job = self._jobs[job_id]
            
            # Idempotent: if already paused, consider it success
            if job.status == JobStatus.PAUSED:
                return True
            
            if job.status != JobStatus.PROCESSING:
                print(f"[VideoQueueService] Cannot pause job {job_id}: not currently processing (status: {job.status.value})")
                return False
            
            # Signal stop event to pause processing
            if self._stop_event:
                self._stop_event.set()
            
            job.status = JobStatus.PAUSED
        
        # Save to database
        self._save_job_to_db(job)
        
        print(f"[VideoQueueService] Paused job {job_id}")
        
        self._notify_status_change(job_id)
        return True
    
    async def resume_job(self, job_id: str) -> bool:
        """
        Resume a paused job.
        
        Args:
            job_id: Job ID to resume
            
        Returns:
            True if resumed successfully (idempotent - returns True if already active/completed)
        """
        with self._lock:
            if job_id not in self._jobs:
                return False
            
            job = self._jobs[job_id]
            
            # Idempotent: if already pending, processing, or completed, consider it success
            if job.status in [JobStatus.PENDING, JobStatus.PROCESSING, JobStatus.COMPLETED]:
                return True
            
            if job.status not in [JobStatus.PAUSED, JobStatus.STOPPED]:
                print(f"[VideoQueueService] Cannot resume job {job_id}: not paused or stopped (status: {job.status.value})")
                return False
            
            job.status = JobStatus.PENDING
            job.started_at = None
            
            # Add back to queue if not present
            if job_id not in self._queue_order:
                # Insert at front for resumed jobs
                self._queue_order.insert(0, job_id)
        
        # Save to database
        self._save_job_to_db(job)
        
        print(f"[VideoQueueService] Resumed job {job_id}")
        
        self._notify_status_change(job_id)
        return True
    
    async def stop_job(self, job_id: str) -> bool:
        """
        Stop a processing or pending job.
        
        Args:
            job_id: Job ID to stop
            
        Returns:
            True if stopped successfully
        """
        with self._lock:
            if job_id not in self._jobs:
                return False
            
            job = self._jobs[job_id]
            
            # Idempotent: if already stopped, consider it success
            if job.status == JobStatus.STOPPED:
                return True
            
            if job.status == JobStatus.PROCESSING:
                # Signal stop event
                if self._stop_event:
                    self._stop_event.set()
                job.status = JobStatus.STOPPED
            elif job.status == JobStatus.PENDING:
                job.status = JobStatus.STOPPED
                if job_id in self._queue_order:
                    self._queue_order.remove(job_id)
            else:
                print(f"[VideoQueueService] Cannot stop job {job_id}: status is {job.status.value}")
                return False
            
            job.completed_at = time.time()
        
        # Save to database
        self._save_job_to_db(job)
        
        print(f"[VideoQueueService] Stopped job {job_id}")
        
        self._notify_status_change(job_id)
        return True

    async def start_queue_job_immediately(self, job_id: str) -> bool:
        """
        Stop current processing job and start this queue job immediately.

        Args:
            job_id: Job ID from queue to start immediately

        Returns:
            True if successful (idempotent - returns True if already processing)
        """
        with self._lock:
            if job_id not in self._jobs:
                return False

            target_job = self._jobs[job_id]

            # Idempotent: if already processing, consider it success
            if target_job.status == JobStatus.PROCESSING:
                return True

            # Can only start pending jobs immediately
            if target_job.status != JobStatus.PENDING:
                print(f"[VideoQueueService] Cannot start job {job_id}: not pending (status: {target_job.status.value})")
                return False

            # If there's a current processing job, pause it
            if self._current_job_id and self._current_job_id in self._jobs:
                current_job = self._jobs[self._current_job_id]
                if current_job.status == JobStatus.PROCESSING:
                    # Signal stop to pause current job
                    if self._stop_event:
                        self._stop_event.set()
                    current_job.status = JobStatus.PAUSED
                    print(f"[VideoQueueService] Paused current job {self._current_job_id} to start {job_id}")

            # Move target job to front of queue
            if job_id in self._queue_order:
                self._queue_order.remove(job_id)
            self._queue_order.insert(0, job_id)
            target_job.priority = 9999  # Highest priority

        # Save changes to database
        if self._current_job_id:
            self._save_job_to_db(self._jobs[self._current_job_id])
        self._save_job_to_db(target_job)

        print(f"[VideoQueueService] Job {job_id} moved to front, will start immediately")

        self._notify_status_change(job_id)
        if self._current_job_id:
            self._notify_status_change(self._current_job_id)
        return True

    async def cancel_and_remove_job(self, job_id: str) -> bool:
        """
        Cancel current processing and remove from queue.

        Args:
            job_id: Job ID to cancel and remove

        Returns:
            True if successful (idempotent - returns True if already cancelled/completed/stopped)
        """
        with self._lock:
            if job_id not in self._jobs:
                return False

            job = self._jobs[job_id]

            # Idempotent: if already in terminal state, just remove it
            if job.status in [JobStatus.CANCELLED, JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.STOPPED]:
                # Just remove from queue order if present
                if job_id in self._queue_order:
                    self._queue_order.remove(job_id)
                
                # Remove from jobs dict
                del self._jobs[job_id]
                
                # Delete from database
                self._delete_job_from_db(job_id)
                return True

            # Can only cancel processing or pending jobs
            if job.status not in [JobStatus.PROCESSING, JobStatus.PENDING]:
                print(f"[VideoQueueService] Cannot cancel job {job_id}: status is {job.status.value}")
                return False

            # Signal stop event to stop processing (for processing jobs)
            if job.status == JobStatus.PROCESSING and self._stop_event:
                self._stop_event.set()

            job.status = JobStatus.CANCELLED
            job.completed_at = time.time()

            # Remove from queue order if present
            if job_id in self._queue_order:
                self._queue_order.remove(job_id)

            # Remove from jobs dict
            del self._jobs[job_id]

        # Delete from database
        self._delete_job_from_db(job_id)

        print(f"[VideoQueueService] Cancelled and removed job {job_id}")
        return True

    async def reprocess_video(self, job_id: str, start_immediately: bool = False) -> Optional[str]:
        """
        Reprocess a completed video by creating a new job.

        Args:
            job_id: Completed job ID to reprocess
            start_immediately: If True, stop current job and start this immediately

        Returns:
            New job ID if successful, None otherwise
        """
        with self._lock:
            if job_id not in self._jobs:
                # Try to load from database
                return None

            old_job = self._jobs[job_id]

            # Can only reprocess completed, failed, stopped, or cancelled jobs
            if old_job.status not in [JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.STOPPED, JobStatus.CANCELLED]:
                print(f"[VideoQueueService] Cannot reprocess job {job_id}: status is {old_job.status.value}")
                return None

            # Create new job with same parameters
            new_job_id = str(uuid.uuid4())
            new_job = VideoJob(
                id=new_job_id,
                source=old_job.source,
                camera_id=old_job.camera_id,
                display_mode=old_job.display_mode,
                status=JobStatus.PENDING,
                priority=9999 if start_immediately else old_job.priority,
                original_filename=f"[RE] {old_job.original_filename}" if old_job.original_filename else f"[RE] {old_job.source}",
                width=old_job.width,
                height=old_job.height,
                fps=old_job.fps,
                duration_sec=old_job.duration_sec,
                save_to_db=old_job.save_to_db,
                save_images=old_job.save_images,
                save_bbox_images=old_job.save_bbox_images,
                frame_skip=old_job.frame_skip,
                show_detector_bbox=old_job.show_detector_bbox,
                show_detector_track_id=old_job.show_detector_track_id,
                show_classifier_class_name=old_job.show_classifier_class_name,
                classifier_top_n=old_job.classifier_top_n,
            )

            self._jobs[new_job_id] = new_job

            # If start immediately, pause current job and insert at front
            if start_immediately:
                if self._current_job_id and self._current_job_id in self._jobs:
                    current_job = self._jobs[self._current_job_id]
                    if current_job.status == JobStatus.PROCESSING:
                        if self._stop_event:
                            self._stop_event.set()
                        current_job.status = JobStatus.PAUSED
                        # Add paused job back to queue
                        if self._current_job_id not in self._queue_order:
                            self._queue_order.insert(0, self._current_job_id)
                        self._save_job_to_db(current_job)

                self._queue_order.insert(0, new_job_id)
            else:
                # Insert based on priority
                inserted = False
                for i, existing_id in enumerate(self._queue_order):
                    existing_job = self._jobs[existing_id]
                    if new_job.priority > existing_job.priority:
                        self._queue_order.insert(i, new_job_id)
                        inserted = True
                        break
                if not inserted:
                    self._queue_order.append(new_job_id)

        # Save to database
        self._save_job_to_db(new_job)

        print(f"[VideoQueueService] Created reprocess job {new_job_id} from {job_id}")

        self._notify_status_change(new_job_id)
        return new_job_id

    async def resume_and_replace(self, job_id: str) -> bool:
        """
        Resume a paused job and replace the current queue with it.
        The current queue job (if any) will become paused.

        Args:
            job_id: Paused job ID to resume

        Returns:
            True if successful (idempotent - returns True if already processing)
        """
        with self._lock:
            if job_id not in self._jobs:
                return False

            paused_job = self._jobs[job_id]

            # Idempotent: if already processing, consider it success
            if paused_job.status == JobStatus.PROCESSING:
                return True

            # Can only resume paused jobs
            if paused_job.status != JobStatus.PAUSED:
                print(f"[VideoQueueService] Cannot resume job {job_id}: not paused")
                return False

            # If there's a current processing job, pause it
            if self._current_job_id and self._current_job_id in self._jobs:
                current_job = self._jobs[self._current_job_id]
                if current_job.status == JobStatus.PROCESSING:
                    if self._stop_event:
                        self._stop_event.set()
                    current_job.status = JobStatus.PAUSED
                    # Add to queue if not present
                    if self._current_job_id not in self._queue_order:
                        self._queue_order.insert(0, self._current_job_id)
                    print(f"[VideoQueueService] Paused current job {self._current_job_id}")

            # Resume the target job and put at front
            paused_job.status = JobStatus.PENDING
            paused_job.started_at = None

            if job_id in self._queue_order:
                self._queue_order.remove(job_id)
            self._queue_order.insert(0, job_id)
            paused_job.priority = 9999

        # Save to database
        if self._current_job_id and self._current_job_id in self._jobs:
            self._save_job_to_db(self._jobs[self._current_job_id])
        self._save_job_to_db(paused_job)

        print(f"[VideoQueueService] Resumed job {job_id} and moved to front")

        self._notify_status_change(job_id)
        if self._current_job_id:
            self._notify_status_change(self._current_job_id)
        return True

    def get_job(self, job_id: str) -> Optional[VideoJob]:
        """Get a job by ID"""
        return self._jobs.get(job_id)
    
    def get_all_jobs(self) -> List[VideoJob]:
        """Get all jobs"""
        with self._lock:
            return list(self._jobs.values())
    
    def get_queue(self) -> List[VideoJob]:
        """Get jobs in queue order (pending only)"""
        with self._lock:
            result = []
            for job_id in self._queue_order:
                if job_id in self._jobs:
                    job = self._jobs[job_id]
                    if job.status == JobStatus.PENDING:
                        result.append(job)
            return result
    
    def get_global_status(self) -> Dict[str, Any]:
        """
        Get global status of all video processing.
        
        Returns:
            Dictionary with:
            - current_job: Currently processing job (if any)
            - queue: List of pending jobs in order
            - paused: List of paused jobs
            - completed: List of completed jobs
            - failed: List of failed jobs
            - stats: Processing statistics
        """
        with self._lock:
            current_job = None
            queue = []
            paused = []
            completed = []
            failed = []
            stopped = []
            
            for job in self._jobs.values():
                if job.status == JobStatus.PROCESSING:
                    current_job = job
                elif job.status == JobStatus.PENDING:
                    queue.append(job)
                elif job.status == JobStatus.PAUSED:
                    paused.append(job)
                elif job.status == JobStatus.COMPLETED:
                    completed.append(job)
                elif job.status == JobStatus.FAILED:
                    failed.append(job)
                elif job.status == JobStatus.STOPPED:
                    stopped.append(job)
            
            # Sort queue by priority and position
            queue.sort(key=lambda j: (-j.priority, j.created_at))
            
            # Sort completed by completion time (newest first)
            completed.sort(key=lambda j: j.completed_at or 0, reverse=True)
            
            # Sort failed by completion time (newest first)
            failed.sort(key=lambda j: j.completed_at or 0, reverse=True)
            
            return {
                "current_job": current_job.to_dict() if current_job else None,
                "queue": [j.to_dict() for j in queue],
                "paused": [j.to_dict() for j in paused],
                "completed": [j.to_dict() for j in completed],
                "failed": [j.to_dict() for j in failed],
                "stopped": [j.to_dict() for j in stopped],
                "stats": {
                    "total_jobs": len(self._jobs),
                    "pending_count": len(queue),
                    "processing_count": 1 if current_job else 0,
                    "paused_count": len(paused),
                    "completed_count": len(completed),
                    "failed_count": len(failed),
                    "stopped_count": len(stopped),
                }
            }
    
    def register_status_callback(self, callback: Callable[[str, Dict], None]):
        """Register a callback for status changes"""
        self._status_callbacks.append(callback)
    
    def unregister_status_callback(self, callback: Callable[[str, Dict], None]):
        """Unregister a status callback"""
        if callback in self._status_callbacks:
            self._status_callbacks.remove(callback)
    
    def _notify_status_change(self, job_id: str):
        """Notify all registered callbacks of a status change"""
        job = self._jobs.get(job_id)
        if job:
            for callback in self._status_callbacks:
                try:
                    callback(job_id, job.to_dict())
                except Exception as e:
                    print(f"[VideoQueueService] Callback error: {e}")
    
    async def start_processing(self):
        """
        Start the queue processing loop.
        
        This runs continuously, processing videos from the queue
        until stop_processing() is called.
        """
        if self._processing_task and not self._processing_task.done():
            print("[VideoQueueService] Processing already running")
            return
        
        self._stop_event = asyncio.Event()
        self._processing_task = asyncio.create_task(self._processing_loop())
        print("[VideoQueueService] Started processing loop")
    
    async def stop_processing(self):
        """Stop the queue processing loop"""
        if self._stop_event:
            self._stop_event.set()
        
        if self._processing_task:
            try:
                await asyncio.wait_for(self._processing_task, timeout=10.0)
            except asyncio.TimeoutError:
                self._processing_task.cancel()
                try:
                    await self._processing_task
                except asyncio.CancelledError:
                    pass
        
        print("[VideoQueueService] Stopped processing loop")
    
    async def _processing_loop(self):
        """Main processing loop"""
        while not self._stop_event.is_set():
            try:
                # Get next job from queue
                job_id = None
                with self._lock:
                    for jid in self._queue_order:
                        if jid in self._jobs and self._jobs[jid].status == JobStatus.PENDING:
                            job_id = jid
                            break
                
                if job_id is None:
                    # No pending jobs, wait a bit
                    await asyncio.wait_for(
                        self._stop_event.wait(),
                        timeout=1.0
                    )
                    continue
                
                # Process the job
                await self._process_job(job_id)
                
            except asyncio.TimeoutError:
                continue
            except Exception as e:
                print(f"[VideoQueueService] Processing loop error: {e}")
                await asyncio.sleep(1.0)
    
    async def _process_job(self, job_id: str):
        """Process a single video job using process_video_background_task"""
        job = self._jobs.get(job_id)
        if not job or job.status != JobStatus.PENDING:
            return

        # Update job status
        job.status = JobStatus.PROCESSING
        job.started_at = time.time()
        self._current_job_id = job_id

        # Remove from queue order
        with self._lock:
            if job_id in self._queue_order:
                self._queue_order.remove(job_id)

        # Save to database
        self._save_job_to_db(job)
        self._notify_status_change(job_id)

        print(f"[VideoQueueService] Starting background processing for job {job_id}")

        # Create a fresh stop event for this job
        job_stop_event = asyncio.Event()
        self._stop_event = job_stop_event

        try:
            # Start background task
            background_task = asyncio.create_task(
                process_video_background_task(
                    video_path=job.source,
                    camera_id=job.camera_id,
                    frame_skip=job.frame_skip,
                    save_to_db=job.save_to_db,
                    task_id=job_id,
                    save_images=job.save_images,
                    save_bbox_images=job.save_bbox_images,
                    stop_event=job_stop_event,
                )
            )

            # Poll background task status until complete
            last_state = None
            while not background_task.done():
                # Check if job was stopped externally
                if job.status == JobStatus.STOPPED:
                    job_stop_event.set()
                    break

                # Get current background state
                state = get_background_task_status(job_id)
                if state and state != last_state:
                    last_state = state.copy()

                    # Update job progress from background state
                    job.progress_pct = int(
                        (state.get("frames_processed", 0) / max(state.get("total_frames", 1), 1)) * 100
                    )
                    job.frames_processed = state.get("frames_processed", 0)
                    job.total_frames = state.get("total_frames", 0)
                    job.detections_count = state.get("detections_count", 0)

                    # Check for error
                    if state.get("status") == "failed":
                        job.status = JobStatus.FAILED
                        job.error_message = state.get("error", "Unknown error")
                        break

                    # Save and notify
                    self._save_job_to_db(job)
                    self._notify_status_change(job_id)

                # Wait before next poll
                await asyncio.sleep(0.5)

            # Get final result
            if not background_task.done():
                background_task.cancel()
                try:
                    await background_task
                except asyncio.CancelledError:
                    pass
                result = {"status": "stopped"}
            else:
                try:
                    result = await background_task
                except Exception as e:
                    result = {"status": "failed", "error": str(e)}

            # Update job with final result
            final_status = result.get("status", "unknown")
            if final_status == "completed":
                job.status = JobStatus.COMPLETED
                job.progress_pct = 100
            elif final_status == "stopped":
                job.status = JobStatus.STOPPED
            elif final_status == "failed":
                job.status = JobStatus.FAILED
                job.error_message = result.get("error", "Unknown error")

            job.frames_processed = result.get("frames_processed", job.frames_processed)
            job.detections_count = result.get("detections_count", job.detections_count)
            job.completed_at = time.time()

            print(f"[VideoQueueService] Job {job_id} finished with status: {final_status}")

        except Exception as e:
            job.status = JobStatus.FAILED
            job.error_message = str(e)
            job.completed_at = time.time()
            print(f"[VideoQueueService] Job {job_id} failed: {e}")

        finally:
            self._current_job_id = None
            # Clear the stop event so the processing loop can continue with next job
            # Don't set to None - that causes AttributeError in _processing_loop
            if self._stop_event is not None:
                self._stop_event.clear()
            self._save_job_to_db(job)
            self._notify_status_change(job_id)


# ==============================================================================
# Global VideoQueueService Instance
# ==============================================================================

_global_queue_service: Optional[VideoQueueService] = None
_global_lock = threading.Lock()


async def get_video_queue_service() -> VideoQueueService:
    """
    Get or create global VideoQueueService instance.
    
    Returns:
        VideoQueueService singleton instance
    """
    global _global_queue_service
    
    if _global_queue_service is None:
        with _global_lock:
            if _global_queue_service is None:
                _global_queue_service = VideoQueueService()
                await _global_queue_service.start_processing()
    
    return _global_queue_service
