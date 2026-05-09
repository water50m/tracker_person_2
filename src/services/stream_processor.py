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
import subprocess
import tempfile

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
        
        # Store last detections for bbox inheritance
        self._last_detections = []
    
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
        
        print(f"[StreamProcessor] Starting stream for {stream_camera_id} (skip: {stream_frame_skip})")
        
        # Update internal camera_id for this session
        self.camera_id = stream_camera_id
        
        try:
            loop = asyncio.get_running_loop()

            # Handle YouTube live streams specially
            if isinstance(resolved_source, str) and resolved_source.startswith("YOUTUBE_LIVE:"):
                youtube_url = resolved_source.replace("YOUTUBE_LIVE:", "")
                print(f"[StreamProcessor] Processing YouTube live stream: {youtube_url}")
                # For YouTube live streams, we'll use a different approach
                # Try to get a working direct stream URL periodically
                cap = await self._create_youtube_live_capture(youtube_url, loop)
            elif hasattr(resolved_source, 'stdout'):
                # FFmpeg subprocess - use stdout as video source
                import numpy as np
                print(f"[StreamProcessor] Using FFmpeg subprocess as video source")
                cap = cv2.VideoCapture(resolved_source.stdout.fileno())
            else:
                # Regular URL or file
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
            
                        
            # Initialize database if needed
            db = None
            if should_save_db:
                try:
                    from services.database import DatabaseService
                    db = DatabaseService()
                except Exception as e:
                    print(f"[StreamProcessor] Database initialization failed: {e}")
                    db = None
            
            # Record start time for URL to first frame timing
            stream_start_time = time.time()
            print(f"[StreamProcessor] ⏱️ Stream processing started at {stream_start_time:.3f} for camera {self.camera_id}")
            
            # Main processing loop
            consecutive_errors = 0
            max_consecutive_errors = 10
            first_frame_captured = False
            
            while not self._stop_event.is_set():
                try:
                    # Read frame
                    cv2_start = time.perf_counter()
                    if hasattr(resolved_source, 'stdout'):
                        # FFmpeg subprocess - read raw frames
                        import numpy as np
                        raw_bytes = resolved_source.stdout.read(width * height * 3)
                        if len(raw_bytes) == width * height * 3:
                            frame = np.frombuffer(raw_bytes, dtype=np.uint8).reshape((height, width, 3))
                            ret = True
                        else:
                            ret = False
                            frame = None
                    else:
                        # Regular capture
                        ret, frame = await loop.run_in_executor(None, cap.read)
                    
                    cv2_time = (time.perf_counter() - cv2_start) * 1000
                    
                    if ret and not first_frame_captured:
                        first_frame_captured = True
                        url_to_frame_time = (time.time() - stream_start_time) * 1000
                        print(f"[StreamProcessor] 🎯 FIRST FRAME CAPTURED: Frame {self._frame_count}, CV2 capture: {cv2_time:.2f}ms, URL to first frame: {url_to_frame_time:.2f}ms")
                    
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
                        # For skipped frames, draw inherited boxes from last detection
                        if hasattr(self, '_last_detections') and self._last_detections:
                            self._draw_inherited_boxes(frame, self._last_detections)
                        
                        # Still send frame to MJPEG for smooth streaming
                        if on_frame:
                            try:
                                on_frame(frame, self._frame_count)
                            except Exception as e:
                                print(f"[StreamProcessor] Frame callback error: {e}")
                        continue
                    
                    # Process frame
                    process_start = time.perf_counter()
                    try:
                        result = await self._process_frame(frame, self._frame_count)
                        process_time = (time.perf_counter() - process_start) * 1000
                        
                        # Update stats
                        self._stats.processed_frames += 1
                        
                        # Handle frame callback
                        if on_frame:
                            try:
                                on_frame(frame, self._frame_count)
                            except Exception as e:
                                print(f"[StreamProcessor] Frame callback error: {e}")
                        
                        # Handle detections and store for inheritance
                        if result.detections:
                            # Store latest detections for inheritance
                            self._last_detections = result.detections
                            
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
                        
                        # Handle frame callback AFTER detections are processed
                        # This ensures detection boxes are drawn on the frame before MJPEG streaming
                        if on_frame:
                            try:
                                on_frame(frame, self._frame_count)
                            except Exception as e:
                                print(f"[StreamProcessor] Frame callback error: {e}")
                        
                        # Save batch to database periodically
                        if len(self._detection_batch) >= self.batch_size:
                            await self._flush_batch(db)
                    
                    except Exception as e:
                        print(f"[StreamProcessor] Frame processing error: {e}")
                        self._stats.num_errors += 1
                
                except Exception as e:
                    print(f"[StreamProcessor] Frame read/processing error: {e}")
                    consecutive_errors += 1
                    self._stats.num_errors += 1
                    
                    # Brief pause before retry
                    await asyncio.sleep(0.1)
                    continue
            
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
    
    def _resolve_source(self, source: str) -> str:
        print(f"[StreamProcessor] Resolving source: {source}")
        # Check if it's a webcam index
        if isinstance(source, str) and source.isdigit():
            return int(source)
        
        # Check if it's a YouTube URL (handle directly)
        if 'youtube.com/watch?v=' in source:
            print(f"[StreamProcessor] Processing YouTube URL directly")
            try:
                direct_url = self._extract_direct_stream(source)
                if direct_url and direct_url != source:
                    print(f"[StreamProcessor] Using direct stream for YouTube")
                    # If it's still an HLS URL, try to get a better format
                    if '.m3u8' in direct_url or 'manifest.googlevideo.com' in direct_url:
                        return self._get_youtube_direct_video(source)
                    return direct_url
            except Exception as e:
                print(f"[StreamProcessor] YouTube extraction failed: {e}")
            raise ValueError(f"Cannot resolve YouTube URL: {source}")
        
        # Check if it's an HLS stream (YouTube manifest, .m3u8)
        if '.m3u8' in source or 'manifest.googlevideo.com' in source:
            # Try to get original YouTube URL first
            original_url = self._get_original_youtube_url(source)
            if original_url and original_url != source:
                print(f"[StreamProcessor] Using original YouTube URL")
                # Recursively resolve the YouTube URL
                return self._resolve_source(original_url)
            
            # Try yt-dlp extraction
            try:
                direct_url = self._extract_direct_stream(source)
                if direct_url and direct_url != source:
                    print(f"[StreamProcessor] Using direct stream for HLS")
                    return direct_url
            except Exception as e:
                print(f"[StreamProcessor] HLS extraction failed")
            
            raise ValueError(f"Cannot resolve stream source: {source}")
        
        return source
        
    def _extract_direct_stream(self, url: str) -> str:
        print(f"[StreamProcessor] Attempting yt-dlp extraction for: {url}")

        """
        Extract direct MP4 stream URL using yt-dlp.
        
        Args:
            url: HLS stream URL or YouTube URL
            
        Returns:
            Direct MP4 stream URL or original URL if extraction fails
        """
        print(f"[StreamProcessor] Attempting yt-dlp extraction for: {url}")
        
        # Store original URL for fallback
        original_url = url
        try:
            import yt_dlp
            print(f"[StreamProcessor] yt-dlp imported successfully")
            ydl_opts = {
                "quiet": True,
                "no_warnings": True,
                "format": "best[protocol!=http_dash_segments]/best",
                "noplaylist": True,
                "extract_flat": False,
                "no_check_certificates": True,
            }
            
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                print(f"[StreamProcessor] yt-dlp extracted info: {bool(info)}")

                if not info:
                    print(f"[StreamProcessor] yt-dlp failed to extract info")

                    return original_url
                
                # For live streams, try to get the best direct URL
                if info.get("is_live", False):
                    # Live stream - look for direct video URLs
                    formats = info.get("formats", [])
                    
                    # Find formats with direct URLs (not HLS)
                    direct_formats = []
                    for i, f in enumerate(formats[:3]):  # Show first 3 formats
                        format_url = f.get("url", "")
                        vcodec = f.get("vcodec", "none")
                        acodec = f.get("acodec", "none")
                        height = f.get("height", "unknown")
                        print(f"[StreamProcessor] Format {i}: height={height}, vcodec={vcodec}, acodec={acodec}, url_length={len(format_url)}")

                        # Add to direct_formats if it meets criteria
                        # แทนที่จะ reject .m3u8 ให้ใช้ FFmpeg pipe
                        if (format_url and 
                            vcodec != "none" and
                            acodec != "none"):
                            
                            if format_url.endswith('.m3u8'):
                                # Use FFmpeg subprocess for HLS
                                direct_formats.append({'url': format_url, 'height': height, 'use_ffmpeg': True})
                                print(f"[StreamProcessor] Added format {i} with FFmpeg for HLS")
                            elif not 'manifest.googlevideo.com' in format_url:
                                direct_formats.append(f)
                                print(f"[StreamProcessor] Added format {i} to direct_formats")
                                
                    if direct_formats:
                        # Sort by quality (height)
                        direct_formats.sort(key=lambda x: x.get("height", 0), reverse=True)
                        best_format = direct_formats[0]
                        
                        # If needs FFmpeg, get direct video URL instead
                        if best_format.get('use_ffmpeg'):
                            print(f"[StreamProcessor] HLS detected, getting direct video URL")
                            return self._get_youtube_direct_video(original_url)
                        
                        return best_format["url"]
                else:
                    # Regular video - get the best format
                    stream_url = info.get("url") or (
                        info["requested_downloads"][0]["url"] if info.get("requested_downloads") else None
                    )
                    
                    if stream_url and stream_url != url and not stream_url.endswith('.m3u8'):
                        return stream_url
                
                # Last resort: try any format that's not HLS
                formats = info.get("formats", [])
                for f in formats:
                    format_url = f.get("url", "")
                    if (format_url and 
                        not format_url.endswith('.m3u8') and 
                        not 'manifest.googlevideo.com' in format_url and
                        f.get("vcodec") != "none"):
                        return format_url
                
        except ImportError:
            print("[StreamProcessor] yt-dlp not available")
        except Exception as e:
            print(f"[StreamProcessor] yt-dlp error: {e}")
        
        # Fallback: Use FFmpeg pipe with first available format
        try:
            import yt_dlp
            ydl_opts = {
                "quiet": True,
                "no_warnings": True,
                "format": "best[protocol!=http_dash_segments]/best",
                "noplaylist": True,
                "extract_flat": False,
                "no_check_certificates": True,
            }
            
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                formats = info.get("formats", [])
                
                if formats:
                    first_url = formats[0].get("url", "")
                    if first_url:
                        print(f"[StreamProcessor] Using direct URL fallback for OpenCV")
                        return first_url
        except Exception as e:
            print(f"[StreamProcessor] FFmpeg fallback failed: {e}")
        
        return original_url
    
    def _get_youtube_direct_video(self, youtube_url: str) -> str:
        """
        Get a direct YouTube video URL that works with OpenCV.
        For live streams, this returns a special marker to use alternative processing.
        """
        try:
            import yt_dlp
            ydl_opts = {
                "quiet": True,
                "no_warnings": True,
                "format": "best[ext=mp4]/best[height<=720]/best",
                "noplaylist": True,
                "extract_flat": False,
                "no_check_certificates": True,
            }
            
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(youtube_url, download=False)
                
                if info:
                    # Check if it's a live stream
                    if info.get("is_live", False):
                        print(f"[StreamProcessor] YouTube live stream detected - using alternative approach")
                        # For live streams, we'll use a different approach in the main stream processing
                        return f"YOUTUBE_LIVE:{youtube_url}"
                    
                    formats = info.get("formats", [])
                    
                    # Find MP4 formats that are not HLS
                    mp4_formats = []
                    for f in formats:
                        url = f.get("url", "")
                        vcodec = f.get("vcodec", "none")
                        height = f.get("height", 0)
                        
                        # Prefer MP4 formats with direct URLs
                        if (url and 
                            vcodec != "none" and
                            not url.endswith('.m3u8') and
                            not 'manifest.googlevideo.com' in url and
                            height > 0):
                            
                            mp4_formats.append({
                                'url': url,
                                'height': height,
                                'format': f
                            })
                    
                    if mp4_formats:
                        # Sort by quality (height)
                        mp4_formats.sort(key=lambda x: x['height'], reverse=True)
                        best = mp4_formats[0]
                        print(f"[StreamProcessor] Found MP4 format: {best['height']}p")
                        return best['url']
                    
                    # Fallback: try any format that's not HLS
                    for f in formats:
                        url = f.get("url", "")
                        if (url and 
                            not url.endswith('.m3u8') and 
                            not 'manifest.googlevideo.com' in url and
                            f.get("vcodec") != "none"):
                            print(f"[StreamProcessor] Using fallback format")
                            return url
                            
        except Exception as e:
            print(f"[StreamProcessor] Direct video extraction failed: {e}")
        
        # Last resort - return the original URL to trigger the error
        return youtube_url
    
    def _get_original_youtube_url(self, manifest_url: str) -> str:
        """
        Try to extract the original YouTube video URL from a manifest URL.
        This works by extracting video ID from manifest parameters.
        """
        try:
            # Extract video ID from manifest URL
            import re
            
            # Look for video ID pattern in the manifest URL
            video_id_match = re.search(r'/id/([A-Za-z0-9_\-]+)', manifest_url)
            if video_id_match:
                video_id = video_id_match.group(1)
                original_url = f"https://www.youtube.com/watch?v={video_id}"
                print(f"[StreamProcessor] Extracted YouTube URL: {original_url}")
                print(f"[StreamProcessor] Original URL type: {type(original_url)}")
                return original_url
            
        except Exception:
            pass
        
        return manifest_url
    
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
            db_start = time.perf_counter()
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None,  # Default executor
                db.insert_detections_batch,
                batch_data
            )
            db_time = (time.perf_counter() - db_start) * 1000
            
            self._stats.num_detections_saved += len(self._detection_batch)
            print(f"[StreamProcessor] Batch inserted {len(self._detection_batch)} detections in {db_time:.2f}ms")
            
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
    
    async def _create_youtube_live_capture(self, youtube_url: str, loop):
        """
        Create a video capture for YouTube live streams with retry logic.
        This tries different approaches to get a working stream.
        """
        import yt_dlp
        
        max_attempts = 3
        for attempt in range(max_attempts):
            try:
                print(f"[StreamProcessor] YouTube live attempt {attempt + 1}/{max_attempts}")
                
                # Try to get a direct video URL that might work
                ydl_opts = {
                    "quiet": True,
                    "no_warnings": True,
                    "format": "best[height<=720]/best",
                    "noplaylist": True,
                    "extract_flat": False,
                    "no_check_certificates": True,
                }
                
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(youtube_url, download=False)
                    
                    if info:
                        formats = info.get("formats", [])
                        
                        # Try each format in order of preference
                        for f in formats:
                            url = f.get("url", "")
                            vcodec = f.get("vcodec", "none")
                            height = f.get("height", 0)
                            
                            if (url and 
                                vcodec != "none" and
                                height > 0 and
                                height <= 720):  # Limit to 720p for performance
                                
                                print(f"[StreamProcessor] Trying format: {height}p, vcodec={vcodec}")
                                
                                # Try to open this URL with OpenCV
                                cap = await loop.run_in_executor(None, cv2.VideoCapture, url)
                                
                                if await loop.run_in_executor(None, cap.isOpened):
                                    print(f"[StreamProcessor] ✅ Successfully opened YouTube live stream at {height}p")
                                    return cap
                                else:
                                    await loop.run_in_executor(None, cap.release)
                                    print(f"[StreamProcessor] ❌ Failed to open {height}p format")
                
                print(f"[StreamProcessor] Attempt {attempt + 1} failed")
                
                if attempt < max_attempts - 1:
                    # Wait before retry
                    await asyncio.sleep(2)
                    
            except Exception as e:
                print(f"[StreamProcessor] YouTube live attempt {attempt + 1} error: {e}")
                if attempt < max_attempts - 1:
                    await asyncio.sleep(2)
        
        # If all attempts failed, raise an error
        raise ValueError(f"Cannot open YouTube live stream after {max_attempts} attempts: {youtube_url}")
    
    def _draw_inherited_boxes(self, frame: np.ndarray, detections: List[Any]):
        """
        Draw inherited bounding boxes on frame for skipped frames.
        
        Args:
            frame: OpenCV frame to draw on
            detections: List of detection objects from last processed frame
        """
        try:
            import cv2
            
            for detection in detections:
                if hasattr(detection, 'bbox') and detection.bbox:
                    bbox = detection.bbox
                    # Draw bounding box
                    cv2.rectangle(frame, 
                               (int(bbox.x), int(bbox.y)), 
                               (int(bbox.x + bbox.width), int(bbox.y + bbox.height)), 
                               (0, 255, 0), 2)  # Green color
                    
                    # Add label
                    if hasattr(detection, 'track_id') and detection.track_id:
                        cv2.putText(frame, f"ID: {detection.track_id}", 
                                   (int(bbox.x), int(bbox.y - 10)), 
                                   cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)
        except Exception as e:
            print(f"[StreamProcessor] Error drawing inherited boxes: {e}")


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


# Global singleton instance
stream_processor = None

async def get_stream_processor():
    """Get or create global stream processor singleton"""
    global stream_processor
    print(f"[DEBUG] get_stream_processor called, stream_processor is None: {stream_processor is None}")
    if stream_processor is None:
        print(f"[DEBUG] Creating new StreamProcessor instance")
        from services.thread_pool_processor import ThreadPoolProcessor
        thread_pool = ThreadPoolProcessor(max_workers=4)
        await thread_pool.initialize()
        stream_processor = StreamManager(thread_pool)
        print(f"[DEBUG] StreamProcessor instance created: {id(stream_processor)}")
    else:
        print(f"[DEBUG] Returning existing StreamProcessor instance: {id(stream_processor)}")
    return stream_processor
