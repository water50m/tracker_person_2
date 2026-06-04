"""
Dashboard API
- GET /api/dashboard/cameras           — list cameras + active-stream status
- GET /api/dashboard/mjpeg/{camera_id} — MJPEG live relay from RTSP
- GET /api/dashboard/latest-detections/{camera_id} — last N detections for overlay
"""

from __future__ import annotations

import os
import asyncio
import sys
import time
import json
from pathlib import Path
from typing import AsyncGenerator, Optional

from fastapi import APIRouter, HTTPException, Query, BackgroundTasks
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from src.services.database import DatabaseService
from src.services.stream_manager import stream_manager
from src.config_loader import get_storage_mode
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
            import cv2

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


class StreamUpsertRequest(BaseModel):
    rtsp_url: str | None = None
    source_url: str | None = None
    camera_id: str
    label: str | None = None
    is_active: bool = True


def _json_streams_path() -> Path:
    from src.config_loader import get_json_storage_root

    root = Path(get_json_storage_root()).resolve()
    streams_path = (root / "json_jobs" / "streams.json").resolve()
    streams_path.parent.mkdir(parents=True, exist_ok=True)
    return streams_path


def _load_json_streams() -> list[dict]:
    path = _json_streams_path()
    if not path.exists():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []
    if isinstance(payload, dict):
        streams = payload.get("streams", [])
    else:
        streams = payload
    if not isinstance(streams, list):
        return []
    cleaned = []
    for row in streams:
        if not isinstance(row, dict):
            continue
        camera_id = str(row.get("camera_id") or "").strip()
        if not camera_id:
            continue
        cleaned.append(
            {
                "camera_id": camera_id,
                "rtsp_url": str(row.get("rtsp_url") or row.get("source_url") or "").strip(),
                "label": str(row.get("label") or camera_id),
                "is_active": bool(row.get("is_active", True)),
            }
        )
    return cleaned


def _save_json_streams(streams: list[dict]) -> None:
    path = _json_streams_path()
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps({"streams": streams}, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)
# ─── Cameras ──────────────────────────────────────────────────────────────────

@router.get("/cameras")
async def list_dashboard_cameras():
    """Return all cameras from DB merged with active-stream registry."""
    try:
        if get_storage_mode() == "json":
            cameras = []
            for stream in _load_json_streams():
                cam_id = stream["camera_id"]
                cameras.append(
                    {
                        "id": cam_id,
                        "name": stream.get("label") or cam_id,
                        "source_url": stream.get("rtsp_url") or "",
                        "is_active": stream.get("is_active", True),
                        "is_processing": cam_id in _ACTIVE_STREAMS,
                        "is_prediction_paused": False,
                    }
                )
            return {"cameras": cameras, "storage_mode": "json"}

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
        if get_storage_mode() == "json":
            return {"camera_id": camera_id, "detections": [], "storage_mode": "json"}

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
    if get_storage_mode() == "json":
        for stream in _load_json_streams():
            if stream["camera_id"] == camera_id:
                url = stream.get("rtsp_url") or ""
                return url or None
        return None

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
                
    # Inactive camera: relay raw stream without AI processing.
    from src.config_loader import get_stream_config
    import cv2

    # For HTTP/HTTPS sources, try direct byte-relay first (avoids OpenCV decode→encode overhead
    # and handles MJPEG streams that OpenCV on Windows cannot open via HTTP).
    if source.startswith("http://") or source.startswith("https://"):
        try:
            import httpx
            print(f"[MJPEG] Trying HTTP direct relay for camera {camera_id}: {source}")
            async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
                async with client.stream("GET", source, headers={"Connection": "keep-alive"}) as resp:
                    content_type = resp.headers.get("content-type", "")
                    print(f"[MJPEG] HTTP relay connected for camera {camera_id}, content-type: {content_type}")
                    if "multipart" in content_type:
                        # Already MJPEG multipart — pipe bytes through directly
                        print(f"[MJPEG] Piping multipart MJPEG directly for camera {camera_id}")
                        async for chunk in resp.aiter_bytes(chunk_size=65536):
                            yield chunk
                        return
                    elif "image/jpeg" in content_type or "image/jpg" in content_type:
                        # Single JPEG snapshot — wrap in MJPEG boundary and loop
                        print(f"[MJPEG] Wrapping single JPEG as MJPEG for camera {camera_id}")
                        data = await resp.aread()
                        while True:
                            yield (
                                b"--frame\r\nContent-Type: image/jpeg\r\n\r\n"
                                + data
                                + b"\r\n"
                            )
                            await asyncio.sleep(1 / 15)
                            # Refresh snapshot
                            try:
                                snap = await client.get(source)
                                data = snap.content
                            except Exception:
                                break
                        return
                    else:
                        # Unknown content type — fall through to OpenCV
                        print(f"[MJPEG] Unknown HTTP content-type '{content_type}' for camera {camera_id}, falling back to OpenCV")
        except Exception as e:
            print(f"[MJPEG] HTTP relay failed for camera {camera_id}: {e}, falling back to OpenCV")

    scfg = get_stream_config()
    mode = scfg.get("frame_skip_mode", "auto")
    skip_n = max(1, int(scfg.get("frame_skip_n", 2)))
    target_fps = max(1, int(scfg.get("target_fps", 15)))
    buf_size = max(1, int(scfg.get("buffer_size", 1)))

    cap = cv2.VideoCapture(source)
    if not cap.isOpened():
        print(f"[MJPEG] Cannot open raw source for camera {camera_id}: {source}")
        return
    cap.set(cv2.CAP_PROP_BUFFERSIZE, buf_size)
    print(f"[MJPEG] Raw relay started for camera {camera_id} | mode={mode} skip_n={skip_n} target_fps={target_fps} buf={buf_size}")

    frame_interval = 1.0 / target_fps
    frame_count = 0
    last_send_time = 0.0

    def _read_latest_frame():
        """Flush buffer with grab() then decode only the newest frame."""
        grabbed = 0
        while True:
            ok = cap.grab()
            if not ok:
                break
            grabbed += 1
            # stop grabbing once buffer is empty (grab returns immediately when empty)
            # we do at most buf_size+2 extra grabs to drain stale frames
            if grabbed > buf_size + 2:
                break
        return cap.retrieve()

    try:
        while True:
            if mode == "none":
                ok, frame = await loop.run_in_executor(None, cap.read)
            elif mode == "fixed":
                # grab (skip) skip_n-1 frames, decode only the last
                def _read_fixed():
                    for _ in range(skip_n - 1):
                        cap.grab()
                    return cap.read()
                ok, frame = await loop.run_in_executor(None, _read_fixed)
            else:  # auto — drain buffer, get freshest frame
                ok, frame = await loop.run_in_executor(None, _read_latest_frame)

            if not ok or frame is None:
                await asyncio.sleep(0.05)
                continue

            ok_enc, jpeg = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
            if not ok_enc:
                await asyncio.sleep(0.01)
                continue

            frame_count += 1
            yield (
                b"--frame\r\n"
                b"Content-Type: image/jpeg\r\n\r\n"
                + jpeg.tobytes()
                + b"\r\n"
            )

            # rate-limit to target_fps
            now = time.perf_counter()
            elapsed = now - last_send_time
            sleep_time = frame_interval - elapsed
            last_send_time = now
            if sleep_time > 0:
                await asyncio.sleep(sleep_time)
    finally:
        cap.release()
        print(f"[MJPEG] Raw relay stopped for camera {camera_id} total_frames={frame_count}")



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
    """Stop AI processing for a camera. _run_and_finalize will unregister + finalize job."""
    event = _ACTIVE_STREAMS.get(camera_id)
    if event is None:
        raise HTTPException(status_code=404, detail="Camera is not currently processing")

    event.set()
    await asyncio.sleep(0.5)
    stream_manager.clear_camera(camera_id)
    return {"status": "success", "camera_id": camera_id, "message": "Prediction stopped"}

def _live_job_result_path(job_id: str) -> "Path":
    from pathlib import Path
    from src.config_loader import get_json_storage_root
    return Path(get_json_storage_root()).resolve() / job_id / "prediction_results.json"


def _init_live_job(job_id: str, camera_id: str, source: str) -> "Path":
    """Create job directory + initial prediction_results.json + register in index."""
    import datetime
    from pathlib import Path
    from src.config_loader import get_json_storage_root

    json_root = Path(get_json_storage_root()).resolve()
    job_dir = json_root / job_id
    job_dir.mkdir(parents=True, exist_ok=True)
    result_path = job_dir / "prediction_results.json"

    result_data = {
        "metadata": {
            "source_video": source,
            "camera_id": camera_id,
            "fps": 0, "width": 0, "height": 0,
            "job_id": job_id,
            "stream_id": job_id,
            "status": "processing",
            "started_at": datetime.datetime.now().isoformat(),
        },
        "frames": [],
    }
    result_path.write_text(json.dumps(result_data, ensure_ascii=False, indent=2), encoding="utf-8")

    # Register in index.json
    index_path = json_root / "json_jobs" / "index.json"
    index_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        idx = json.loads(index_path.read_text(encoding="utf-8")) if index_path.exists() else {"jobs": []}
        if not isinstance(idx.get("jobs"), list):
            idx["jobs"] = []
        idx["jobs"].append({
            "id": job_id,
            "label": f"[LIVE] {camera_id}",
            "source": source,
            "status": "processing",
            "output_dir": job_id,
            "path": str(job_dir),
            "metadata": {"camera_id": camera_id},
        })
        tmp = index_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(idx, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(index_path)
    except Exception as e:
        print(f"[LiveJob] Failed to register in index: {e}")

    return result_path


def _append_frame_result(result_path: "Path", frame_number: int, persons: list) -> None:
    """Append one frame's detections to prediction_results.json (thread-safe via tmp swap)."""
    try:
        data = json.loads(result_path.read_text(encoding="utf-8"))
        data["frames"].append({"frame": frame_number, "time": round(frame_number / 30, 3), "persons": persons})
        tmp = result_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(result_path)
    except Exception as e:
        print(f"[LiveJob] Failed to append frame {frame_number}: {e}")


def _finalize_live_job(job_id: str) -> None:
    """Mark job as completed in prediction_results.json and index."""
    from pathlib import Path
    from src.config_loader import get_json_storage_root

    json_root = Path(get_json_storage_root()).resolve()
    result_path = json_root / job_id / "prediction_results.json"
    try:
        data = json.loads(result_path.read_text(encoding="utf-8"))
        data["metadata"]["status"] = "completed"
        result_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass

    index_path = json_root / "json_jobs" / "index.json"
    try:
        idx = json.loads(index_path.read_text(encoding="utf-8"))
        for job in idx.get("jobs", []):
            if job.get("id") == job_id:
                job["status"] = "completed"
                break
        tmp = index_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(idx, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(index_path)
    except Exception:
        pass


@router.post("/prediction/{camera_id}/start")
async def start_prediction(camera_id: str, background_tasks: BackgroundTasks, resume: bool = False):
    """Start AI processing for a live camera — same pipeline as processing page, saves to JSON."""
    if camera_id in _ACTIVE_STREAMS:
        raise HTTPException(status_code=400, detail="Camera is already processing")

    source = _get_rtsp_url(camera_id)
    if not source:
        raise HTTPException(status_code=404, detail="Camera has no source URL")

    from src.config_loader import get_stream_config, get_storage_mode
    import uuid

    scfg = get_stream_config()
    ai_frame_skip = max(1, int(scfg.get("ai_frame_skip", 5)))

    stop_event = _register_stream(camera_id)

    # Create JSON job for result storage
    job_id = f"live_{camera_id}_{uuid.uuid4().hex[:8]}"
    result_path = None
    if get_storage_mode() == "json":
        result_path = _init_live_job(job_id, camera_id, source)
        print(f"[LiveJob] Created job {job_id} for camera {camera_id}")

    def on_detection(cam_id: str, detections: list, frame_number: int, frame_bytes: bytes):
        try:
            stream_manager.update_frame(cam_id, frame_bytes, frame_number)
            stream_manager.update_detections(cam_id, detections)
            if result_path and detections:
                _append_frame_result(result_path, frame_number, detections)
        except Exception as e:
            print(f"[LiveJob] Detection callback error: {e}")

    def on_frame(frame, frame_number):
        pass

    async def _run_and_finalize():
        from services.stream_processor import get_stream_processor
        try:
            processor_instance = await get_stream_processor()
            await processor_instance.start_stream(
                camera_id=camera_id,
                source=source,
                on_detection=on_detection,
                on_frame=on_frame,
                stop_event=stop_event,
                frame_skip=ai_frame_skip,
            )
        finally:
            if result_path:
                _finalize_live_job(job_id)
                print(f"[LiveJob] Finalized job {job_id}")
            _unregister_stream(camera_id)

    background_tasks.add_task(_run_and_finalize)

    return {
        "status": "success",
        "camera_id": camera_id,
        "job_id": job_id,
        "ai_frame_skip": ai_frame_skip,
        "message": f"Prediction started (frame_skip={ai_frame_skip}, saving={'json' if result_path else 'off'})",
    }

# ─── Live Data API (Optional) ─────────────────────────────────────────────────

@router.get("/live-data/{camera_id}")
async def live_data(camera_id: str):
    """Returns the absolute newest detection box data from the stream manager (memory), for frontend clickable boxes."""
    return {"camera_id": camera_id, "detections": stream_manager.get_detections(camera_id)}


@router.get("/streams")
async def list_streams():
    if get_storage_mode() == "json":
        return {"streams": _load_json_streams(), "storage_mode": "json"}
    db = DatabaseService()
    with db.conn.cursor() as cur:
        cur.execute("SELECT id, name, source_url, is_active FROM cameras ORDER BY id")
        rows = cur.fetchall()
    streams = [
        {
            "camera_id": str(row[0]),
            "label": row[1],
            "rtsp_url": row[2],
            "is_active": bool(row[3]),
        }
        for row in rows
    ]
    return {"streams": streams, "storage_mode": "db"}


@router.post("/streams")
async def upsert_stream(payload: StreamUpsertRequest):
    stream_url = (payload.rtsp_url or payload.source_url or "").strip()
    camera_id = payload.camera_id.strip()
    if not stream_url:
        raise HTTPException(status_code=400, detail="source_url (or rtsp_url) is required")
    if not camera_id:
        raise HTTPException(status_code=400, detail="camera_id is required")
    label = (payload.label or camera_id).strip() or camera_id

    if get_storage_mode() == "json":
        streams = _load_json_streams()
        updated = False
        for item in streams:
            if item["camera_id"] == camera_id:
                item["rtsp_url"] = stream_url
                item["label"] = label
                item["is_active"] = bool(payload.is_active)
                updated = True
                break
        if not updated:
            streams.append(
                {
                    "camera_id": camera_id,
                    "rtsp_url": stream_url,
                    "label": label,
                    "is_active": bool(payload.is_active),
                }
            )
        _save_json_streams(streams)
        return {"status": "saved", "camera_id": camera_id, "storage_mode": "json"}

    db = DatabaseService()
    with db.conn.cursor() as cur:
        cur.execute("SELECT id FROM cameras WHERE id::text = %s OR name = %s LIMIT 1", (camera_id, camera_id))
        row = cur.fetchone()
        if row is not None:
            cur.execute(
                "UPDATE cameras SET name=%s, source_url=%s, is_active=%s WHERE id=%s",
                (label, stream_url, bool(payload.is_active), row[0]),
            )
        else:
            cur.execute(
                "INSERT INTO cameras (name, source_url, is_active) VALUES (%s, %s, %s)",
                (label, stream_url, bool(payload.is_active)),
            )
    db.conn.commit()
    return {"status": "saved", "camera_id": camera_id, "storage_mode": "db"}


@router.delete("/streams/{camera_id}")
async def delete_stream(camera_id: str):
    camera_id = camera_id.strip()
    if not camera_id:
        raise HTTPException(status_code=400, detail="camera_id is required")
    if get_storage_mode() == "json":
        streams = [item for item in _load_json_streams() if item["camera_id"] != camera_id]
        _save_json_streams(streams)
        return {"status": "deleted", "camera_id": camera_id, "storage_mode": "json"}
    db = DatabaseService()
    with db.conn.cursor() as cur:
        cur.execute("DELETE FROM cameras WHERE id::text = %s OR name = %s", (camera_id, camera_id))
        deleted = cur.rowcount
    db.conn.commit()
    if deleted == 0:
        raise HTTPException(status_code=404, detail=f"Camera not found: {camera_id}")
    return {"status": "deleted", "camera_id": camera_id, "storage_mode": "db"}
