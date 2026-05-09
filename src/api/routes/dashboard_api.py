"""
Dashboard API
- GET /api/dashboard/cameras           — list cameras + active-stream status
- GET /api/dashboard/mjpeg/{camera_id} — MJPEG live relay from RTSP
- GET /api/dashboard/latest-detections/{camera_id} — last N detections for overlay
"""

from __future__ import annotations

import cv2
import os
import asyncio
import sys
import time
from pathlib import Path
from typing import AsyncGenerator, Optional

from fastapi import APIRouter, HTTPException, Query, BackgroundTasks
from fastapi.responses import StreamingResponse

from src.services.database import DatabaseService
from src.services.stream_manager import stream_manager
from src.api.video_controller import (
    _ACTIVE_STREAMS, YOUTUBE_PATTERN, _extract_youtube_stream,
    _register_stream, _unregister_stream
)

# Add src to path for refactored services
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

# Refactored StreamProcessor (lazy import)
_stream_manager: Optional['StreamManager'] = None

async def _get_stream_manager():
    """Lazy initialization of StreamManager"""
    global _stream_manager
    
    if _stream_manager is None:
        from services.stream_processor import StreamManager
        from services.thread_pool_processor import ThreadPoolProcessor
        
        pool = ThreadPoolProcessor(max_workers=4)
        await pool.initialize()
        
        _stream_manager = StreamManager(pool)
    
    return _stream_manager


async def _process_stream_refactored(
    stream_url: str,
    camera_id: str,
    video_id: Optional[str],
    stop_event: asyncio.Event,
) -> None:
    """
    Stream processing using the refactored StreamProcessor.
    """
    try:
        stream_mgr = await _get_stream_manager()

        def on_detection(detection, frame_number):
            """Callback for real-time detection updates"""
            latest = stream_manager.get_detections(camera_id)
            latest.append(detection.to_dict())
            stream_manager.update_detections(camera_id, latest[-50:])

        def on_frame(frame, frame_number):
            """Callback for MJPEG relay frame cache."""
            ok, jpeg = cv2.imencode(".jpg", frame)
            if ok:
                stream_manager.update_frame(camera_id, jpeg.tobytes(), frame_number)
                if frame_number % 30 == 0:  # Log every 30 frames
                    print(f"[FrameCallback] Stored frame {frame_number} for camera {camera_id}, size: {len(jpeg.tobytes())} bytes")
                    # Test if frame is retrievable
                    test_frame = stream_manager.get_frame(camera_id)
                    print(f"[FrameCallback] Test retrieval: {'SUCCESS' if test_frame else 'FAILED'}")
            else:
                print(f"[FrameCallback] Failed to encode frame {frame_number} for camera {camera_id}")

        # Start stream
        await stream_mgr.start_stream(
            camera_id=camera_id,
            source=stream_url,
            on_detection=on_detection,
            on_frame=on_frame,
            stop_event=stop_event,
            frame_skip=3,
        )

        print(f"[DashboardAPI] Stream {camera_id} started with refactored StreamProcessor")
        task = stream_mgr._tasks.get(camera_id)
        if task:
            await task

    except Exception as e:
        print(f"[DashboardAPI] Refactored stream processing failed: {e}")
        raise

router = APIRouter()

MINIO_BASE = os.getenv("MINIO_BASE_URL", "http://myserver:9000")
print(f"[DEBUG] MINIO_BASE_URL forced to: {MINIO_BASE}")
# ─── Cameras ──────────────────────────────────────────────────────────────────

@router.get("/cameras")
async def list_dashboard_cameras():
    """Return all cameras from DB merged with active-stream registry."""
    try:
        db = DatabaseService()
        with db.conn.cursor() as cur:
            cur.execute("SELECT id, name, source_url, is_active FROM cameras ORDER BY id")
            rows = cur.fetchall()
        cameras = [
            {
                "id": row[0],
                "name": row[1],
                "source_url": row[2],
                "is_active": row[3],
                "is_processing": str(row[0]) in _ACTIVE_STREAMS,
                "is_prediction_paused": stream_manager.is_prediction_paused(str(row[0])),
            }
            for row in rows
        ]
        return {"cameras": cameras}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ─── Latest detections ────────────────────────────────────────────────────────

@router.get("/latest-detections/{camera_id}")
async def latest_detections(camera_id: str, limit: int = Query(8, ge=1, le=50)):
    """Return the most recent N detections for a given camera_id."""
    try:
        db = DatabaseService()
        with db.conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, track_id, timestamp, image_path,
                       clothing_category, class_name, color_profile
                FROM detections
                WHERE camera_id = %s
                ORDER BY timestamp DESC
                LIMIT %s
                """,
                (camera_id, limit),
            )
            rows = cur.fetchall()
        return {
            "camera_id": camera_id,
            "detections": [
                {
                    "id": str(row[0]),
                    "track_id": row[1],
                    "timestamp": row[2].isoformat() if row[2] else None,
                    "image_url": f"{MINIO_BASE}/{row[3]}" if row[3] else None,
                    "category": row[4] or "UNKNOWN",
                    "class_name": row[5] or "unknown",
                    "color_profile": row[6] or {},
                }
                for row in rows
            ],
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ─── MJPEG relay ──────────────────────────────────────────────────────────────

_MJPEG_CACHE: dict[str, str] = {}   # camera_id → rtsp_url (cached from DB)


def _get_rtsp_url(camera_id: str) -> str | None:
    """Look up the RTSP stream URL for a camera_id from the DB (or int for webcam)."""
    try:
        db = DatabaseService()
        db._ensure_connection()
        with db.conn.cursor() as cur:
            cur.execute("SELECT source_url FROM cameras WHERE id = %s", (camera_id,))
            row = cur.fetchone()
        if row and row[0]:
            _MJPEG_CACHE[camera_id] = row[0]
            return row[0]
    except Exception:
        pass
    return None


async def _mjpeg_generator(source: str, camera_id: str) -> AsyncGenerator[bytes, None]:
    """Open a video source with OpenCV and yield MJPEG boundary frames."""
    loop = asyncio.get_event_loop()

    # If AI processing is active for this camera, stream from the global cache
    print(f"[DEBUG] Camera {camera_id} in _ACTIVE_STREAMS: {camera_id in _ACTIVE_STREAMS}")
    print(f"[DEBUG] Active streams: {list(_ACTIVE_STREAMS.keys())}")
    if camera_id in _ACTIVE_STREAMS:
        print(f"[MJPEG] Starting stream for camera {camera_id}, AI processing active")
        frame_count = 0
        start_time = time.time()
        last_log_time = time.time()
        while camera_id in _ACTIVE_STREAMS:
            try:
                frame_bytes = stream_manager.get_frame(camera_id)
                if frame_bytes:
                    frame_count += 1
                    current_time = time.time()
                    # Get frame number from stream manager
                    frame_number = stream_manager.latest_frame_numbers.get(camera_id, frame_count)
                    
                    # Skip duplicate frames to avoid sending the same frame multiple times
                    if not hasattr(stream_manager, '_last_sent_frame'):
                        stream_manager._last_sent_frame = {}
                    
                    last_frame = stream_manager._last_sent_frame.get(camera_id)
                    if frame_number == last_frame:
                        # Skip duplicate frame - log occasionally
                        if frame_count % 30 == 0:
                            print(f"[MJPEG] Skipping duplicate frame #{frame_number} for camera {camera_id}")
                        await asyncio.sleep(1 / 15)  # 15 FPS
                        continue
                    
                    # Update last sent frame
                    stream_manager._last_sent_frame[camera_id] = frame_number
                    
                    # Debug: Log when new frame is sent
                    if frame_count % 10 == 0:
                        print(f"[MJPEG] Sending NEW frame #{frame_number} for camera {camera_id} (previous: {last_frame})")
                    
                    # Transmission timing
                    trans_start = time.perf_counter()
                    yield (
                        b"--frame\r\n"
                        b"Content-Type: image/jpeg\r\n\r\n"
                        + frame_bytes
                        + b"\r\n"
                    )
                    trans_time = (time.perf_counter() - trans_start) * 1000
                    
                    # Log every frame that gets sent
                    timestamp = time.strftime("%H:%M:%S", time.localtime())
                    print(f"[{timestamp}] Frame #{frame_number} sent to frontend, transmission time: {trans_time:.2f}ms, size: {len(frame_bytes)} bytes, FPS: ~{frame_count/(time.time()-start_time+0.1):.1f}")
                else:
                    # No frame available yet
                    if frame_count == 0:  # Log only once at start
                        print(f"[MJPEG] Waiting for first frame for camera {camera_id}...")
                        start_time = time.time()
                    
                    # Check if AI processing is still active
                    if camera_id not in _ACTIVE_STREAMS:
                        print(f"[MJPEG] Camera {camera_id} no longer in active streams, stopping generator")
                        return
                    
                    # If no new frames for 10 seconds, stop the stream
                    no_frame_time = time.time() - current_time if 'current_time' in locals() else 0
                    if no_frame_time > 10:
                        print(f"[MJPEG] No new frames for {no_frame_time:.1f}s, stopping stream (AI processing likely stopped)")
                        return
                    
                    # Log warning after 5 seconds
                    if no_frame_time > 5:
                        print(f"[MJPEG] No new frames for {no_frame_time:.1f}s, AI processing may have stopped")
                    
                    await asyncio.sleep(1 / 30)  # Shorter sleep when waiting for frames
                    continue
                await asyncio.sleep(1 / 15)  # 15 FPS for better performance
            except Exception as e:
                print(f"[MJPEG] ❌ Error in MJPEG generator for camera {camera_id}: {e}")
                # Send error frame to frontend
                error_frame = b"ERROR: Stream interrupted"
                yield (
                    b"--frame\r\n"
                    b"Content-Type: text/plain\r\n\r\n"
                    + error_frame
                    + b"\r\n"
                )
                return
        print(f"[MJPEG] Stream ended for camera {camera_id}, total frames: {frame_count}")
        return  # Exit when AI processing stops
                
    # If not active, do not occupy the server. The frontend handles native playback.
    print(f"[MJPEG] Camera {camera_id} not in active streams, not streaming")
    return



@router.get("/mjpeg/{camera_id}")
async def mjpeg_stream(camera_id: str):
    """
    Stream live MJPEG from the camera's source_url or from the global shared buffer if AI is processing.
    Browser just needs: <img src="/api/dashboard/mjpeg/{camera_id}">
    """
    print(f"[MJPEG] Request received for camera {camera_id}")
    
    source = _get_rtsp_url(camera_id)
    if source is None:
        raise HTTPException(status_code=404, detail=f"Camera '{camera_id}' not found or has no source URL")

    print(f"[MJPEG] Starting streaming response for camera {camera_id}")
    return StreamingResponse(
        _mjpeg_generator(source, camera_id),
        media_type="multipart/x-mixed-replace; boundary=frame",
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate, max-age=0",
            "Pragma": "no-cache",
            "Expires": "0",
            "Connection": "close",
        }
    )

    # Log MJPEG stream start
    import time
    timestamp = time.strftime("%H:%M:%S", time.localtime())
    print(f"[{timestamp}] MJPEG stream started for camera {camera_id}")

# ─── Prediction Controls ──────────────────────────────────────────────────────

@router.post("/prediction/{camera_id}/stop")
async def stop_prediction(camera_id: str):
    """Stop AI processing for a camera entirely and return to inactive state."""
    event = _ACTIVE_STREAMS.get(camera_id)
    if event is None:
        raise HTTPException(status_code=404, detail="Camera is not currently processing")
    
    # 1. Trigger the stop event to stop the stream processor loop.
    event.set()
    
    # 2. Wait a moment for it to gracefully exit
    await asyncio.sleep(0.5)
    
    # 3. Clean up stream manager memory cache so old frames don't reappear later
    stream_manager.clear_camera(camera_id)
    
    return {"status": "success", "camera_id": camera_id, "message": "Prediction stopped"}

@router.post("/prediction/{camera_id}/start")
async def start_prediction(camera_id: str, background_tasks: BackgroundTasks, resume: bool = False):
    """Manually start AI processing for a camera that is currently inactive."""
    if camera_id in _ACTIVE_STREAMS:
        raise HTTPException(status_code=400, detail="Camera is already processing")

    source = _get_rtsp_url(camera_id)
    if not source:
        raise HTTPException(status_code=404, detail="Camera has no source URL")

    # Use StreamProcessor singleton to avoid duplicate processing
    from services.stream_processor import get_stream_processor
    import time
    
    stop_event = _register_stream(camera_id)
    
    # Define callbacks
    def on_detection(camera_id: str, detections: list, frame_number: int, frame_bytes: bytes):
        """Handle detection results"""
        try:
            print(f"[DEBUG] on_detection called for camera {camera_id}, frame #{frame_number}, detections: {len(detections)}")
            # Store in global cache for MJPEG streaming
            stream_manager.update_frame(camera_id, frame_bytes, frame_number)
            stream_manager.update_detections(camera_id, detections)
            
            # Log detection summary
            person_count = sum(1 for d in detections if d.get('class_name') == 'person')
            if person_count > 0:
                timestamp = time.strftime("%H:%M:%S", time.localtime())
                print(f"[{timestamp}] {person_count} person(s) detected in frame #{frame_number}")
                
        except Exception as e:
            print(f"Detection callback error: {e}")
    
    def on_frame(frame, frame_number):
        """Handle each frame"""
        pass
    
    # Start stream using StreamProcessor singleton
    processor_instance = await get_stream_processor()
    processor = await processor_instance.start_stream(
        camera_id=camera_id,
        source=source,
        on_detection=on_detection,
        on_frame=on_frame,
        stop_event=stop_event,
        frame_skip=5,
    )
    
    return {
        "status": "success",
        "camera_id": camera_id,
        "message": "Prediction started using StreamProcessor"
    }

# ─── Live Data API (Optional) ─────────────────────────────────────────────────

@router.get("/live-data/{camera_id}")
async def live_data(camera_id: str):
    """Returns the absolute newest detection box data from the stream manager (memory), for frontend clickable boxes."""
    return {"camera_id": camera_id, "detections": stream_manager.get_detections(camera_id)}
