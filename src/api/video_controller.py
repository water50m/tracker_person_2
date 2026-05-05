from fastapi import APIRouter, UploadFile, File, Form, BackgroundTasks, HTTPException, Query
from fastapi.responses import FileResponse
import asyncio
import shutil
import os
import re
import time
import uuid
import sys
from pathlib import Path
from typing import Optional, List, AsyncGenerator
from concurrent.futures import ThreadPoolExecutor
from src.services.database import DatabaseService
from src.services.storage import StorageService
from src.api.schemas import DetectionResponse
import yt_dlp

# Add src to path for Feature Flag and VideoProcessor
sys.path.insert(0, str(Path(__file__).parent.parent))

# Refactored VideoProcessor (lazy import to avoid loading if not used)
_video_processor = None
_thread_pool = None

async def _get_video_processor():
    """Lazy initialization of VideoProcessor with thread pool"""
    global _video_processor, _thread_pool
    
    if _video_processor is None:
        from services.video_processor import VideoProcessor
        from services.thread_pool_processor import ThreadPoolProcessor
        
        _thread_pool = ThreadPoolProcessor(max_workers=4)
        await _thread_pool.initialize()
        
        _video_processor = VideoProcessor(
            thread_pool=_thread_pool,
            frame_skip=30,
            save_to_db=True,
            save_images=True,
        )
    
    return _video_processor, _thread_pool


async def _process_video_refactored(
    source: str,
    camera_id: str,
    video_id: Optional[str] = None,
    frame_skip: int = 30,
) -> None:
    """
    Video processing using the refactored VideoProcessor.
    """
    try:
        processor, pool = await _get_video_processor()
        
        # Use progress tracker for monitoring
        from services.video_processor import get_progress_tracker
        progress_tracker = get_progress_tracker()
        
        # Create progress callback
        progress_callback = progress_tracker.create_callback(video_id) if video_id else None
        
        # Create stop event (not used for file processing, but required by API)
        stop_event = asyncio.Event()
        
        # Process video
        stats = await processor.process_video(
            source=source,
            camera_id=camera_id,
            video_id=video_id,
            frame_skip=frame_skip,
            on_progress=progress_callback,
            stop_event=stop_event,
        )
        
        print(f"[VideoController] Video processing completed: {stats.to_dict()}")
        
    except Exception as e:
        print(f"[VideoController] Refactored video processing failed: {e}")
        raise

# Thread pool for blocking storage operations
_STORAGE_EXECUTOR = ThreadPoolExecutor(max_workers=2, thread_name_prefix="storage_ops")

router = APIRouter()

# ─── Thread pool for image uploads ──────────────────────────────
_UPLOAD_EXECUTOR = ThreadPoolExecutor(max_workers=4, thread_name_prefix="video_upload")

# ─── Active stream registry ────────────────────────────────────
# camera_id → asyncio.Event  (set the event to request stop)
_ACTIVE_STREAMS: dict[str, asyncio.Event] = {}


def _register_stream(camera_id: str) -> asyncio.Event:
    """Register a new active stream, raising 409 if already running."""
    if camera_id in _ACTIVE_STREAMS:
        raise HTTPException(
            status_code=409,
            detail=f"Camera '{camera_id}' already has an active processing task. Stop it first.",
        )
    event = asyncio.Event()
    _ACTIVE_STREAMS[camera_id] = event
    return event


def _unregister_stream(camera_id: str) -> None:
    _ACTIVE_STREAMS.pop(camera_id, None)


@router.get("/active-streams")
async def list_active_streams():
    """Return camera IDs that are currently being processed."""
    return {"active": list(_ACTIVE_STREAMS.keys())}


@router.post("/stop/{camera_id}")
async def stop_stream(camera_id: str):
    """Signal an active processing task to stop gracefully."""
    event = _ACTIVE_STREAMS.get(camera_id)
    if event is None:
        raise HTTPException(status_code=404, detail=f"No active task for camera '{camera_id}'")
    event.set()
    return {"status": "stop_requested", "camera_id": camera_id}


# สร้างโฟลเดอร์เก็บไฟล์ชั่วคราว
UPLOAD_DIR = "temp_videos"
os.makedirs(UPLOAD_DIR, exist_ok=True)

# โฟลเดอร์เก็บไฟล์ชั่วคราวสำหรับ realtime (ไม่บันทึกลง database)
REALTIME_TEMP_DIR = "temp_realtime"
os.makedirs(REALTIME_TEMP_DIR, exist_ok=True)


@router.post("/analyze/upload-temp")
async def upload_video_temp(
    file: UploadFile = File(...),
):
    """
    อัปโหลดไฟล์วิดีโอชั่วคราวสำหรับ realtime processing
    ไม่บันทึกลง database ไฟล์จะถูกลบอัตโนมัติหลังใช้งาน
    """
    try:
        # สร้างชื่อไฟล์ชั่วคราว unique
        temp_id = uuid.uuid4().hex[:12]
        temp_filename = f"temp_{temp_id}_{file.filename}"
        file_path = os.path.abspath(os.path.join(REALTIME_TEMP_DIR, temp_filename))

        # บันทึกไฟล์ลง disk
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        file_size = os.path.getsize(file_path)
        print(f"[TempUpload] Saved {file.filename} ({file_size/1024/1024:.2f} MB) to {file_path}")

        # ตรวจสอบว่าไฟล์เป็นวิดีโอที่เปิดได้
        import cv2
        cap = cv2.VideoCapture(file_path)
        if not cap.isOpened():
            os.remove(file_path)
            raise HTTPException(status_code=400, detail=f"Cannot open video file: {file.filename}. File may be corrupted or in unsupported format.")

        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        cap.release()

        print(f"[TempUpload] Video verified: {width}x{height}, {fps:.2f}fps, {total_frames} frames")

        return {
            "status": "success",
            "message": "Video uploaded for realtime processing",
            "file_path": file_path,
            "original_filename": file.filename,
            "width": width,
            "height": height,
            "fps": fps,
            "total_frames": total_frames
        }
    except Exception as e:
        import traceback
        print(f"[ERROR] Temp upload failed: {e}")
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/analyze/temp/{temp_id}")
async def delete_temp_video(temp_id: str):
    """
    ลบไฟล์วิดีโอชั่วคราว
    """
    try:
        # ค้นหาไฟล์ที่ขึ้นต้นด้วย temp_id
        pattern = f"temp_{temp_id}_"
        deleted = []

        for filename in os.listdir(REALTIME_TEMP_DIR):
            if filename.startswith(pattern):
                file_path = os.path.join(REALTIME_TEMP_DIR, filename)
                try:
                    os.remove(file_path)
                    deleted.append(filename)
                    print(f"[TempCleanup] Deleted: {filename}")
                except Exception as e:
                    print(f"[TempCleanup] Failed to delete {filename}: {e}")

        if not deleted:
            raise HTTPException(status_code=404, detail=f"No temp files found for ID: {temp_id}")

        return {
            "status": "success",
            "deleted_files": deleted
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/analyze/upload")
async def upload_video(
    # 1. BackgroundTasks:
    # ใช้สำหรับสั่งให้โค้ดทำงานเบื้องหลัง (เช่น การรัน AI ประมวลผลวิดีโอ)
    # หลังจากที่ API ส่ง Response กลับไปหาหน้าบ้านแล้ว เพื่อไม่ให้หน้าบ้านต้องรอจน AI รันเสร็จ
    background_tasks: BackgroundTasks,

    # 2. camera_id:
    # รหัสประจำตัวของกล้อง (ID) รับค่าเป็น String
    # Form(...) หมายความว่าเป็นค่าที่ "จำเป็นต้องส่งมา" (Required) ผ่าน Body แบบ Form-data
    camera_id: str = Form(...),

    # 3. file:
    # ไฟล์วิดีโอที่ถูกอัปโหลดขึ้นมา (Binary File)
    # UploadFile เป็น Class ของ FastAPI ที่จัดการเรื่องการเก็บไฟล์ลง Memory/Disk ชั่วคราวให้อัตโนมัติ
    # File(...) หมายความว่าเป็น "ไฟล์ที่จำเป็นต้องอัปโหลด" (Required)
    file: UploadFile = File(...),

    # 4. label:
    # ชื่อเรียกของกล้องแบบที่มนุษย์เข้าใจง่าย (Display Name) เช่น "หน้าประตู", "ลานจอดรถ"
    # Optional[str] หมายถึง "จะส่งมาหรือไม่ส่งก็ได้" (ไม่ได้บังคับ)
    # Form(None) คือค่าตั้งต้นจะเป็น None ถ้าหน้าบ้านไม่ได้ส่งค่านี้มา
    label: Optional[str] = Form(None),
    frame_skip: int = Form(5, description="Process every N-th frame (default: 5 = ~0.17s at 30fps)")

):
    try:

        # 1. บันทึกไฟล์ลง Disk ก่อน
        file_path = os.path.abspath(os.path.join(UPLOAD_DIR, f"{camera_id}_{file.filename}"))

        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        file_size = os.path.getsize(file_path)
        print(f"[Upload] Saved {file.filename} ({file_size/1024/1024:.2f} MB) to {file_path}")

        # Get video dimensions and verify file is valid
        import cv2
        cap = cv2.VideoCapture(file_path)
        if not cap.isOpened():
            raise HTTPException(status_code=400, detail=f"Cannot open video file: {file.filename}. File may be corrupted or in unsupported format.")

        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        cap.release()

        print(f"[Upload] Video verified: {width}x{height}, {fps:.2f}fps, {total_frames} frames (~{total_frames/fps:.1f}s)")

        # 1.5 Register video in database
        db = DatabaseService()
        video_id = db.register_video(
            camera_id=camera_id,
            label=label or camera_id,
            filename=file.filename,
            file_path=file_path,
            width=width,
            height=height
        )

        # 2. Send the job to the refactored VideoProcessor in the background.
        print(f"[VideoController] Using refactored VideoProcessor for {camera_id}")
        background_tasks.add_task(
            _process_video_refactored,
            source=file_path,
            camera_id=camera_id,
            video_id=str(video_id) if video_id else None,
            frame_skip=frame_skip,
        )

        return {
            "status": "processing_started",
            "message": "Video received. AI is processing in the background.",
            "camera_id": camera_id,
            "file_path": file_path,
            "video_id": str(video_id) if video_id else None,
            "using_refactored": True,
        }
    except Exception as e:
        import traceback
        print(f"[ERROR] Upload failed: {e}")
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/analyze/upload-stream")
async def upload_video_stream(
    camera_id: str = Form(...),
    file: UploadFile = File(...),
    label: Optional[str] = Form(None),
    show_detector_bbox: bool = Form(True),
    show_detector_track_id: bool = Form(True),
    show_classifier_class_name: bool = Form(True),
    classifier_top_n: int = Form(1),
    frame_skip: int = Form(1, description="Process every N-th frame for AI detection (default: 1 = all frames)"),
):
    """
    Upload video and return a stream URL for real-time AI analysis.
    
    Unlike /analyze/upload which uses background tasks, this endpoint:
    1. Saves the uploaded file
    2. Registers the video in database
    3. Returns a stream URL that the client can connect to for live MJPEG streaming
    
    The client should then connect to the returned stream_url to see
    real-time detection with bounding boxes overlay.
    """
    try:
        # 1. Save uploaded file
        file_path = os.path.abspath(os.path.join(UPLOAD_DIR, f"{camera_id}_{file.filename}"))
        
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        
        file_size = os.path.getsize(file_path)
        print(f"[UploadStream] Saved {file.filename} ({file_size/1024/1024:.2f} MB) to {file_path}")
        
        # 2. Verify video and get dimensions
        import cv2
        cap = cv2.VideoCapture(file_path)
        if not cap.isOpened():
            os.remove(file_path)
            raise HTTPException(status_code=400, detail=f"Cannot open video file: {file.filename}")
        
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        cap.release()
        
        print(f"[UploadStream] Video verified: {width}x{height}, {fps:.2f}fps, {total_frames} frames")
        
        # 3. Register video in database
        db = DatabaseService()
        video_id = db.register_video(
            camera_id=camera_id,
            label=label or camera_id,
            filename=file.filename,
            file_path=file_path,
            width=width,
            height=height
        )
        
        # 4. Generate stream URL with parameters
        # Build query parameters for the stream
        stream_params = {
            "video_path": file_path,
            "camera_id": camera_id,
            "save_to_db": "true",
            "frame_skip": str(frame_skip),
            "show_detector_bbox": str(show_detector_bbox).lower(),
            "show_detector_track_id": str(show_detector_track_id).lower(),
            "show_classifier_class_name": str(show_classifier_class_name).lower(),
            "classifier_top_n": str(classifier_top_n),
        }
        
        # Build the stream URL (relative to API base)
        query_string = "&".join([f"{k}={v}" for k, v in stream_params.items()])
        stream_url = f"/api/video/stream-analyze?{query_string}"
        
        return {
            "status": "ready",
            "message": "Video uploaded. Connect to stream_url for real-time analysis.",
            "camera_id": camera_id,
            "video_id": str(video_id) if video_id else None,
            "file_path": file_path,
            "stream_url": stream_url,
            "video_info": {
                "width": width,
                "height": height,
                "fps": fps,
                "total_frames": total_frames,
                "duration_sec": round(total_frames / fps, 2) if fps > 0 else None,
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        print(f"[ERROR] Upload stream failed: {e}")
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/analyze/stream")
async def stream_video(
    background_tasks: BackgroundTasks,
    camera_id: str = Form(...),
    stream_url: str = Form(...),
    frame_skip: int = Form(30, description="Process every N-th frame (default: 30)")
):
    stop_event = _register_stream(camera_id)  # raises 409 if duplicate

    async def _task():
        try:
            print(f"[VideoController] Using refactored VideoProcessor for stream {camera_id}")
            processor, pool = await _get_video_processor()

            from services.video_processor import get_progress_tracker
            progress_tracker = get_progress_tracker()

            stats = await processor.process_video(
                source=stream_url,
                camera_id=camera_id,
                video_id=None,
                frame_skip=frame_skip,
                stop_event=stop_event,
                on_progress=progress_tracker.create_callback(f"stream_{camera_id}"),
            )
            print(f"[VideoController] Stream {camera_id} completed: {stats.to_dict()}")
        finally:
            _unregister_stream(camera_id)

    background_tasks.add_task(_task)
    return {
        "status": "stream_connected",
        "camera_id": camera_id,
        "source": stream_url,
        "using_refactored": True,
    }


YOUTUBE_PATTERN = re.compile(
    r"(https?://)?(www\.)?(youtube\.com/(watch\?v=|shorts/)|youtu\.be/)[A-Za-z0-9_\-]+"
)


def _extract_youtube_stream(url: str) -> dict:
    """Use yt-dlp to get the best direct video stream URL (no downloads)."""
    ydl_opts = {
        "quiet": True,
        "no_warnings": True,
        # Avoid m3u8 if possible because OpenCV's libavformat doesn't like jumping between Google's adaptive hosts
        "format": "best[ext=mp4]/best",
        "noplaylist": True,
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=False)
        if not info:
            raise ValueError("Could not extract video info from YouTube URL")
        
        # Check if it's a live stream
        is_live = info.get("is_live", False)
        
        # For merged format the url is in 'url', for adaptive it's in 'requested_downloads'
        stream_url = info.get("url") or (
            info["requested_downloads"][0]["url"] if info.get("requested_downloads") else None
        )
        if not stream_url:
            # Try first format that has a url
            formats = info.get("formats", [])
            valid_formats = [f for f in formats if f.get("url")]
            if valid_formats:
                stream_url = valid_formats[-1]["url"]  # last = usually highest quality
        if not stream_url:
            raise ValueError("No streamable URL found for this video")
        return {
            "stream_url": stream_url,
            "title": info.get("title", url),
            "duration": info.get("duration"),
            "thumbnail": info.get("thumbnail"),
            "uploader": info.get("uploader"),
        }


@router.post("/extract-youtube")
async def extract_youtube_stream(
    request: dict
):
    """Extract direct stream URL from YouTube link for real-time analysis."""
    youtube_url = request.get("url")
    if not youtube_url:
        raise HTTPException(status_code=400, detail="URL is required")
    
    is_raw_stream = ".m3u8" in youtube_url or ".mp4" in youtube_url
    
    if not is_raw_stream and not YOUTUBE_PATTERN.search(youtube_url):
        raise HTTPException(status_code=400, detail="Invalid YouTube or Stream URL")

    try:
        if is_raw_stream:
            # For direct stream URLs, return as-is
            return {
                "stream_url": youtube_url,
                "title": "Direct Stream",
                "duration": None,
                "thumbnail": None,
                "uploader": "Unknown",
            }
        else:
            # Extract YouTube stream
            info = _extract_youtube_stream(youtube_url)
            return info
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"yt-dlp error: {e}")


@router.post("/analyze/youtube")
async def analyze_youtube(
    youtube_url: str = Form(...),
    camera_id: str = Form(...),
    label: Optional[str] = Form(None),
    frame_skip: int = Form(30),
):
    """Download + analyse a YouTube video via yt-dlp, or accept raw m3u8 stream. (Registers ONLY)."""
    
    is_raw_stream = ".m3u8" in youtube_url or ".mp4" in youtube_url
    
    if not is_raw_stream and not YOUTUBE_PATTERN.search(youtube_url):
        raise HTTPException(status_code=400, detail="Invalid YouTube or Raw Stream URL")

    try:
        if is_raw_stream:
            info = {
                "stream_url": youtube_url,
                "title": f"Raw Stream {camera_id}",
                "duration": None,
                "thumbnail": None,
                "uploader": "Unknown",
            }
        else:
            info = _extract_youtube_stream(youtube_url)
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"yt-dlp error: {e}")

    # Register the Camera first so we get the auto-generated integer ID
    db = DatabaseService()
    generated_camera_id = None
    try:
        with db.conn.cursor() as cur:
            # We treat the user's string input 'camera_id' as the human name, omit the id column
            cur.execute("""
                INSERT INTO cameras (name, source_url, is_active) 
                VALUES (%s, %s, true)
                RETURNING id
            """, (camera_id, youtube_url))
            generated_camera_id = cur.fetchone()[0]
            db.conn.commit()
    except Exception as e:
        print(f"Warning: Could not insert camera to table: {e}")
        # If it fails, we assume the user passed an existing INT id
        try:
            generated_camera_id = int(camera_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="Could not create new camera and provided ID is not an integer.")

    # Register the Video into the DB using the REAL integer id
    video_id = db.register_video(
        camera_id=str(generated_camera_id),
        label=label or info["title"],
        filename=info["title"],
        file_path=youtube_url,
    )

    return {
        "status": "queued",
        "video_id": video_id,
        "camera_id": str(generated_camera_id),
        "source": youtube_url,
        "title": info["title"],
        "duration": info["duration"],
        "thumbnail": info["thumbnail"],
    }

# --- API endpoints สำหรับลบข้อมูล (สำหรับทดสอบ) ---

@router.delete("/clear")
async def clear_data(type: str = "all", delete_img: bool = False):
    """
    ลบข้อมูลในฐานข้อมูล (สำหรับทดสอบ)
    type: "all", "detections", "videos"
    delete_img: ถ้าเป็น true จะลบรูปภาพทั้งหมดใน MINIO bucket ด้วย
    """
    import time
    start_time = time.time()
    print(f"[/api/video/clear] Request started: type={type}, delete_img={delete_img}")
    
    db = DatabaseService()
    bucket_result = None

    # ลบรูปภาพใน MINIO ถ้า requested (run in thread pool to avoid blocking)
    if delete_img:
        print(f"[/api/video/clear] Starting bucket clear...")
        bucket_start = time.time()
        try:
            storage = StorageService()
            loop = asyncio.get_event_loop()
            bucket_result = await loop.run_in_executor(_STORAGE_EXECUTOR, storage.clear_bucket)
            bucket_elapsed = time.time() - bucket_start
            print(f"[/api/video/clear] Bucket clear completed in {bucket_elapsed:.2f}s")
        except Exception as e:
            bucket_elapsed = time.time() - bucket_start
            print(f"[/api/video/clear] Bucket clear failed after {bucket_elapsed:.2f}s: {e}")
            bucket_result = {"status": "error", "message": str(e)}

    try:
        with db.conn.cursor() as cur:
            deleted_detections = 0
            deleted_videos = 0
            deleted_colors = 0

            if type == "all":
                # ลบข้อมูล detection_colors ก่อน (เพราะมี foreign key กับ detections)
                cur.execute("DELETE FROM detection_colors")
                deleted_colors = cur.rowcount

                # ลบข้อมูล detections
                cur.execute("DELETE FROM detections")
                deleted_detections = cur.rowcount

                # ลบข้อมูล processed_videos
                cur.execute("DELETE FROM processed_videos")
                deleted_videos = cur.rowcount

                db.conn.commit()

                response = {
                    "status": "success",
                    "message": "All data cleared successfully",
                    "deleted_detections": deleted_detections,
                    "deleted_videos": deleted_videos,
                    "deleted_colors": deleted_colors
                }
                if bucket_result:
                    response["bucket_cleared"] = bucket_result
                elapsed = time.time() - start_time
                print(f"[/api/video/clear] Returning response (type=all) after {elapsed:.2f}s")
                return response

            elif type == "detections":
                # ลบข้อมูล detection_colors ก่อน
                cur.execute("DELETE FROM detection_colors")
                deleted_colors = cur.rowcount

                cur.execute("DELETE FROM detections")
                deleted_detections = cur.rowcount
                db.conn.commit()

                response = {
                    "status": "success",
                    "message": "All detections cleared",
                    "deleted_detections": deleted_detections,
                    "deleted_colors": deleted_colors
                }
                if bucket_result:
                    response["bucket_cleared"] = bucket_result
                elapsed = time.time() - start_time
                print(f"[/api/video/clear] Returning response (type=detections) after {elapsed:.2f}s")
                return response

            elif type == "videos":
                cur.execute("DELETE FROM processed_videos")
                deleted_videos = cur.rowcount
                db.conn.commit()

                response = {
                    "status": "success",
                    "message": "All videos cleared",
                    "deleted_count": deleted_videos
                }
                if bucket_result:
                    response["bucket_cleared"] = bucket_result
                elapsed = time.time() - start_time
                print(f"[/api/video/clear] Returning response (type=videos) after {elapsed:.2f}s")
                return response

            else:
                raise HTTPException(
                    status_code=400,
                    detail="Invalid type. Use: all, detections, or videos"
                )

    except Exception as e:
        db.conn.rollback()
        elapsed = time.time() - start_time
        print(f"[/api/video/clear] ERROR after {elapsed:.2f}s: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# --- API endpoints สำหรับดึงข้อมูล ---

@router.get("/detections", response_model=List[DetectionResponse])
async def get_detections(
    limit: int = Query(20, description="Limit number of results"),
    offset: int = Query(0, description="Offset for pagination"),
    camera_id: Optional[str] = Query(None, description="Filter by camera ID"),
    video_id: Optional[str] = Query(None, description="Filter by video ID")
):
    """
    ดึงข้อมูล detection พร้อม filter ตาม camera_id, limit, offset
    """
    try:
        db = DatabaseService()
        
        query = """
            SELECT id, track_id, timestamp, image_path, bbox_image_path, clothing_category, 
                   class_name, color_profile, camera_id, video_id::text
            FROM detections 
            WHERE 1=1
        """
        params = []
        
        if camera_id:
            query += " AND camera_id = %s"
            params.append(camera_id)
            
        if video_id:
            query += " AND video_id = %s"
            params.append(video_id)
        
        query += " ORDER BY timestamp DESC LIMIT %s OFFSET %s"
        params.extend([limit, offset])
        
        with db.conn.cursor() as cur:
            cur.execute(query, tuple(params))
            rows = cur.fetchall()
            
            # Map to DetectionResponse format
            minio_base = os.getenv("MINIO_BASE_URL", "http://myserver:9000")
            results = []
            for row in rows:
                results.append(DetectionResponse(
                    id=str(row[0]),
                    track_id=int(row[1]),
                    timestamp=row[2],
                    image_url=f"{minio_base}/{row[3]}" if row[3] else None,
                    bbox_image_url=f"{minio_base}/{row[4]}" if row[4] else None,
                    category=str(row[5]) if row[5] else "UNKNOWN",
                    class_name=str(row[6]) if row[6] else "unknown",
                    color_profile=row[7] if row[7] else {},
                    camera_id=str(row[8]) if row[8] else "N/A",
                    video_id=str(row[9]) if row[9] else None,
                ))
                # Log the generated URL for debugging
            
            return results
            
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/videos")
async def get_videos(
    camera_id: Optional[str] = Query(None, description="Filter by camera ID")
):
    """
    ดึงข้อมูลวิดีโอทั้งหมด (กรองตาม camera_id ได้)
    """
    try:
        db = DatabaseService()
        
        query = """
            SELECT id, camera_id, label, filename, file_path, status, created_at 
            FROM processed_videos 
            WHERE 1=1
        """
        params = []
        
        if camera_id:
            query += " AND camera_id = %s"
            params.append(camera_id)
        
        query += " ORDER BY created_at DESC"
        
        with db.conn.cursor() as cur:
            cur.execute(query, tuple(params))
            rows = cur.fetchall()
            
            results = []
            for row in rows:
                results.append({
                    "id": str(row[0]),
                    "camera_id": str(row[1]),
                    "label": str(row[2]),
                    "filename": str(row[3]),
                    "file_path": str(row[4]),
                    "status": str(row[5]),
                    "created_at": row[6]
                })
            
            return results
            
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/videos/{video_id}/stream")
async def stream_video_file(video_id: str):
    """
    Stream video file for playback
    """
    try:
        db = DatabaseService()
        
        # Get video file path from database
        query = "SELECT file_path, filename FROM processed_videos WHERE id::text = %s"
        
        with db.conn.cursor() as cur:
            cur.execute(query, (video_id,))
            result = cur.fetchone()
            
            if not result:
                raise HTTPException(status_code=404, detail="Video not found")
            
            file_path, filename = result
            file_path = os.path.normpath(str(file_path))
            resolved_path = file_path
            candidates = []
            if not os.path.isabs(resolved_path):
                project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
                candidates = [
                    os.path.normpath(os.path.join(project_root, resolved_path)),
                    os.path.normpath(os.path.join(project_root, UPLOAD_DIR, os.path.basename(resolved_path))),
                ]
                for candidate in candidates:
                    if os.path.exists(candidate):
                        resolved_path = candidate
                        break
            
            # Check if file exists
            if not os.path.exists(resolved_path):
                error_msg = f"Video file not found. Path: {file_path}, Resolved: {resolved_path}, Tried: {candidates}"
                raise HTTPException(
                    status_code=404,
                    detail=error_msg
                )
            
            # Return video file for streaming
            return FileResponse(
                path=resolved_path,
                filename=filename,
                media_type="video/mp4"
            )
            
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

async def _review_mjpeg_generator(video_id: str, file_path: str):
    import cv2
    import numpy as np
    
    # 1. Fetch all detections for this video, ordered by time
    db = DatabaseService()
    print(f"[Review] Fetching detections for video_id={video_id!r}")
    try:
        with db.conn.cursor() as cur:
            cur.execute(
                "SELECT video_time_offset, bbox, class_name, track_id FROM detections WHERE video_id = %s ORDER BY video_time_offset ASC",
                (video_id,)
            )
            rows = cur.fetchall()
    except Exception as e:
        print(f"Error fetching detections for review: {e}")
        rows = []
    
    print(f"[Review] Found {len(rows)} detection rows for video_id={video_id!r}")
    
    # Sample a few to see what's in them
    for i, r in enumerate(rows[:3]):
        print(f"[Review] Sample row {i}: time_offset={r[0]}, bbox={r[1]}, class={r[2]}")
        
    # Group detections by frame index (approximate, since we only have time_offset)
    cap = cv2.VideoCapture(file_path)
    fps = cap.get(cv2.CAP_PROP_FPS)
    if fps <= 0:
        fps = 30.0

    # Build a lookup dictionary: frame_index -> list of detections
    detections_by_frame = {}
    valid_count = 0
    for r in rows:
        time_offset = r[0]
        bbox = r[1]
        class_name = r[2]
        track_id = r[3]
        
        if time_offset is None or bbox is None:
            continue
            
        valid_count += 1
        # Convert time offset to frame number
        frame_idx = int(time_offset * fps)
        
        if frame_idx not in detections_by_frame:
            detections_by_frame[frame_idx] = []
            
        detections_by_frame[frame_idx].append({
            "bbox": bbox,
            "class_name": class_name,
            "track_id": track_id
        })

    print(f"[Review] Built {len(detections_by_frame)} frames with detections ({valid_count} valid bboxes)")
    
    # Debug: Show frames with multiple detections
    multi_detection_frames = {k: v for k, v in detections_by_frame.items() if len(v) > 1}
    if multi_detection_frames:
        print(f"[Review] ⚠️  Found {len(multi_detection_frames)} frames with MULTIPLE detections:")
        for frame_idx, dets in list(multi_detection_frames.items())[:5]:
            det_info = [f"{d['track_id']}:{d['class_name']}" for d in dets]
            print(f"  Frame {frame_idx}: {len(dets)} detections - {det_info}")
    else:
        print(f"[Review] ℹ️  No frames with multiple detections (all frames have 1 detection each)")


    current_frame = 0
    active_boxes = [] # (expiration_frame, bbox_data, index_in_frame)
    
    # Track color mapping: track_id -> color (BGR tuple)
    track_colors = {}
    
    # Predefined color palette for multiple people in same frame
    color_palette = [
        (255, 100, 100),  # Light Blue
        (100, 255, 100),  # Light Green
        (100, 100, 255),  # Light Red
        (255, 255, 100),  # Light Cyan
        (255, 100, 255),  # Light Magenta
        (100, 255, 255),  # Light Yellow
        (200, 150, 100),  # Light Purple
        (100, 200, 150),  # Teal
    ]

    while cap.isOpened():
        ret, frame = cap.read()
        if not ret:
            break
            
        # Add new boxes for this frame
        if current_frame in detections_by_frame:
            new_dets = detections_by_frame[current_frame]
            if len(new_dets) > 1:
                print(f"[Review] 📦 Frame {current_frame}: Adding {len(new_dets)} bboxes - {[d['class_name'] for d in new_dets]}")
            for idx, det in enumerate(new_dets, start=1):
                # Keep box alive for 6 frames (approx 0.2 sec at 30fps) to reduce overlapping
                # Store the index (1-based) for this detection within its frame
                active_boxes.append((current_frame + int(fps * 0.2), det, idx, len(new_dets)))
                
        # Filter out expired boxes
        active_boxes = [(exp, det, idx, total) for exp, det, idx, total in active_boxes if exp > current_frame]
        
        # Debug: Log when drawing multiple boxes
        if len(active_boxes) > 1 and current_frame % 30 == 0:  # Log every 30 frames
            print(f"[Review] 🎨 Frame {current_frame}: Drawing {len(active_boxes)} active bboxes")
        
        # Assign colors to track_ids that don't have one yet
        current_track_ids = [det["track_id"] for _, det, _, _ in active_boxes]
        for track_id in current_track_ids:
            if track_id not in track_colors:
                # Use palette color based on how many tracks we have
                color_idx = len(track_colors) % len(color_palette)
                track_colors[track_id] = color_palette[color_idx]
        
        # Draw active boxes
        for _, det, idx_in_frame, total_in_frame in active_boxes:
            bbox = det["bbox"]
            if len(bbox) == 4:
                x1, y1, x2, y2 = map(int, bbox)
                
                # Get consistent color for this track_id
                track_id = det["track_id"]
                color = track_colors.get(track_id, (255, 255, 255))
                
                # Draw rectangle around person
                cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
                
                # Use smaller font size (0.4 instead of 0.5)
                font_scale = 0.4
                font_thickness = 1
                
                # Create labels for 2 lines
                label_line1 = f"1. ID:{track_id} {det['class_name']}"
                
                # Show "2." for first detection, or "2. result" if this is the second detection
                if idx_in_frame == 1:
                    label_line2 = "2."
                elif idx_in_frame == 2:
                    label_line2 = f"2. ID:{track_id} {det['class_name']}"
                else:
                    # For 3rd+ detection, show the full label
                    label_line1 = f"{idx_in_frame}. ID:{track_id} {det['class_name']}"
                    label_line2 = None
                
                # Calculate text dimensions for both lines
                (text_width1, text_height1), baseline1 = cv2.getTextSize(label_line1, cv2.FONT_HERSHEY_SIMPLEX, font_scale, font_thickness)
                
                if idx_in_frame <= 2:
                    (text_width2, text_height2), baseline2 = cv2.getTextSize(label_line2, cv2.FONT_HERSHEY_SIMPLEX, font_scale, font_thickness)
                    
                    # Position BELOW the top edge of bbox (inside the box)
                    label_y_start = y1 + 2  # Start 2px below top edge
                    
                    # Draw line 1 (no background)
                    cv2.putText(frame, label_line1, (x1 + 2, label_y_start + text_height1 + baseline1), 
                               cv2.FONT_HERSHEY_SIMPLEX, font_scale, color, font_thickness)
                    # Draw line 2 (no background)
                    cv2.putText(frame, label_line2, (x1 + 2, label_y_start + text_height1 + baseline1 + text_height2 + baseline2 + 4), 
                               cv2.FONT_HERSHEY_SIMPLEX, font_scale, color, font_thickness)
                else:
                    # For 3rd+ detection, just show single line (no background)
                    label_y_start = y1 + 2
                    
                    cv2.putText(frame, label_line1, (x1 + 2, label_y_start + text_height1 + baseline1), 
                               cv2.FONT_HERSHEY_SIMPLEX, font_scale, color, font_thickness)

        # Encode and yield
        ret, buffer = cv2.imencode('.jpg', frame, [int(cv2.IMWRITE_JPEG_QUALITY), 70])
        if ret:
            yield (
                b"--frame\r\n"
                b"Content-Type: image/jpeg\r\n\r\n" + buffer.tobytes() + b"\r\n"
            )
            
        current_frame += 1
        
        # Throttle to real time (approximate)
        await asyncio.sleep(1.0 / fps)

    cap.release()

from fastapi.responses import StreamingResponse

@router.get("/videos/{video_id}/review")
async def review_video_stream(video_id: str):
    """
    Stream MJPEG of the video with bounding boxes drawn over it
    """
    db = DatabaseService()
    query = "SELECT file_path FROM processed_videos WHERE id::text = %s"
    with db.conn.cursor() as cur:
        cur.execute(query, (video_id,))
        result = cur.fetchone()
        
    if not result:
        raise HTTPException(status_code=404, detail="Video not found")
        
    file_path = result[0]
    
    if not os.path.exists(file_path):
        # Try resolving path if it moved
        project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
        file_path = os.path.normpath(os.path.join(project_root, UPLOAD_DIR, os.path.basename(file_path)))
        if not os.path.exists(file_path):
            raise HTTPException(status_code=404, detail="Video file not found on disk")

    return StreamingResponse(
        _review_mjpeg_generator(video_id, file_path),
        media_type="multipart/x-mixed-replace; boundary=frame"
    )

@router.post("/videos/{video_id}/pause")
async def pause_video_processing(video_id: str):
    """Pause an active processing task for a specific video id."""
    db = DatabaseService()
    with db.conn.cursor() as cur:
        cur.execute("SELECT camera_id FROM processed_videos WHERE id::text = %s", (video_id,))
        result = cur.fetchone()
    
    if not result:
        raise HTTPException(status_code=404, detail="Video not found")
        
    camera_id = result[0]
    event = _ACTIVE_STREAMS.get(camera_id)
    if event:
        event.set()
        await asyncio.sleep(0.5)
        # Assuming the cleanup block handles status=paused
    else:
        # If the task isn't active in memory (e.g., server restarted), just update DB directly
        db.update_video_progress(video_id, db.get_video_progress(video_id), "paused")
        
    return {"status": "success", "message": "Video processing paused"}

@router.post("/videos/{video_id}/resume")
async def resume_video_processing(video_id: str):
    """Resume a paused processing task for a specific video id."""
    db = DatabaseService()
    with db.conn.cursor() as cur:
        cur.execute("SELECT camera_id, file_path FROM processed_videos WHERE id::text = %s", (video_id,))
        result = cur.fetchone()
        
    if not result:
        raise HTTPException(status_code=404, detail="Video not found")
        
    camera_id, file_path = result
    
    if camera_id in _ACTIVE_STREAMS:
        raise HTTPException(status_code=400, detail="A task is already running for this camera slot")
        
    stop_event = _register_stream(camera_id)
    
    async def _task():
        try:
            print(f"[VideoController] Resuming with refactored VideoProcessor for {video_id}")
            processor, pool = await _get_video_processor()

            from services.video_processor import get_progress_tracker
            progress_tracker = get_progress_tracker()

            stats = await processor.process_video(
                source=file_path,
                camera_id=camera_id,
                video_id=video_id,
                frame_skip=5,
                stop_event=stop_event,
                on_progress=progress_tracker.create_callback(video_id) if video_id else None,
            )
            print(f"[VideoController] Resume completed for {video_id}: {stats.to_dict()}")
        except Exception as e:
            print(f"❌ Video {video_id} background task error: {e}")
        finally:
            _unregister_stream(camera_id)

    asyncio.create_task(_task())
    
    # Immediately optimistically update status to 'processing'
    db.update_video_status(video_id, "processing")
    
    return {"status": "success", "message": "Video processing resumed"}


# ═══════════════════════════════════════════════════════════════════════════════
# Real-time Video Analysis with MJPEG Stream
# ═══════════════════════════════════════════════════════════════════════════════

import cv2
import numpy as np
from typing import AsyncGenerator
from src.ai.detector import PersonDetector
from src.ai.classifier import ClothingClassifier
from fastapi.responses import StreamingResponse

# Active stream registry for real-time analysis
_STREAM_ANALYSIS_ACTIVE: dict[str, asyncio.Event] = {}


def _parse_top_n(value: str) -> int | str:
    """Parse top_n parameter (int or 'all')."""
    if value.lower() == "all":
        return "all"
    try:
        return int(value)
    except ValueError:
        return 1


async def _realtime_analysis_generator(
    video_path: str,
    stream_id: str,
    stop_event: asyncio.Event,
    show_detector_bbox: bool = True,
    show_detector_track_id: bool = True,
    show_classifier_bbox: bool = False,
    show_classifier_class_name: bool = True,
    show_classifier_count: bool = False,
    classifier_top_n: int | str = 1,
    save_to_db: bool = False,
    camera_id: Optional[str] = None,
    frame_skip: int = 1,
    save_images: bool = True,
    save_bbox_images: bool = True,
) -> AsyncGenerator[bytes, None]:
    """
    MJPEG generator that performs real-time AI analysis on video file.
    """
    print(f"🎬 [Stream {stream_id}] Starting real-time analysis: {video_path}")
    print(f"   Settings: detector_bbox={show_detector_bbox}, track_id={show_detector_track_id}")
    print(f"   Settings: classifier_bbox={show_classifier_bbox}, class_name={show_classifier_class_name}")
    print(f"   Settings: class_count={show_classifier_count}, top_n={classifier_top_n}")
    print(f"   Save to DB: {save_to_db}, frame_skip={frame_skip}, save_images={save_images}, save_bbox_images={save_bbox_images}")
    
    # Initialize database connection if saving is enabled
    db = None
    effective_camera_id = camera_id if camera_id else f"stream_{stream_id}"
    resolved_camera_id = None
    if save_to_db:
        try:
            from src.services.database import DatabaseService
            db = DatabaseService()
            # Resolve camera name to ID (creates new camera if doesn't exist)
            if camera_id:
                resolved_camera_id = db.resolve_camera_id(camera_id)
                effective_camera_id = str(resolved_camera_id)
            # Register a temporary video for this stream
            video_id = db.register_video(
                camera_id=effective_camera_id,
                label=f"Real-time Stream {stream_id}",
                filename=os.path.basename(video_path),
                file_path=video_path,
                width=0,  # Will be updated later
                height=0   # Will be updated later
            )
            print(f"📊 [Stream {stream_id}] Database saving enabled - Video ID: {video_id}, Camera ID: {effective_camera_id}")
        except Exception as e:
            print(f"⚠️ [Stream {stream_id}] Database connection failed: {e}")
            db = None

    # Initialize storage service for image uploads
    storage = None
    try:
        storage = StorageService()
    except Exception as e:
        print(f"⚠️ [Stream {stream_id}] Storage service unavailable: {e}")

    # Initialize AI models
    try:
        detector = PersonDetector()
        classifier = ClothingClassifier()
    except Exception as e:
        print(f"❌ [Stream {stream_id}] Model initialization failed: {e}")
        # Yield error frame
        error_frame = np.zeros((480, 640, 3), dtype=np.uint8)
        cv2.putText(error_frame, f"Model Error: {e}", (50, 240), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
        ret, buffer = cv2.imencode('.jpg', error_frame)
        if ret:
            yield (b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + buffer.tobytes() + b"\r\n")
        return
    
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        print(f"❌ [Stream {stream_id}] Cannot open video: {video_path}")
        error_frame = np.zeros((480, 640, 3), dtype=np.uint8)
        cv2.putText(error_frame, "Cannot open video", (50, 240), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2)
        ret, buffer = cv2.imencode('.jpg', error_frame)
        if ret:
            yield (b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + buffer.tobytes() + b"\r\n")
        return
    
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    frame_time = 1.0 / fps
    
    # Track IDs for detector
    track_id_mapping: dict[int, int] = {}  # byte_track_id -> our_id
    next_track_id = 1
    
    frame_count = 0
    last_process_time = asyncio.get_event_loop().time()
    
    try:
        while not stop_event.is_set():
            ret, frame = cap.read()
            if not ret:
                print(f"✅ [Stream {stream_id}] Video ended at frame {frame_count}")
                # Send video end notification
                if save_to_db and db and video_id:
                    try:
                        # Update video status to completed
                        db.update_video_status(video_id, "completed")
                        print(f"📊 [Stream {stream_id}] Video marked as completed in database")
                    except Exception as e:
                        print(f"⚠️ [Stream {stream_id}] Failed to update video status: {e}")
                
                # Yield final frame with video end message
                end_frame = np.zeros((480, 640, 3), dtype=np.uint8)
                cv2.putText(end_frame, f"VIDEO ENDED", (200, 200), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 255, 0), 2)
                cv2.putText(end_frame, f"Frames: {frame_count}", (220, 240), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 1)
                cv2.putText(end_frame, f"Stream ID: {stream_id}", (180, 260), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1)
                
                ret, buffer = cv2.imencode('.jpg', end_frame, [int(cv2.IMWRITE_JPEG_QUALITY), 85])
                if ret:
                    yield (
                        b"--frame\r\n"
                        b"Content-Type: image/jpeg\r\n\r\n"
                        + buffer.tobytes()
                        + b"\r\n"
                    )
                break
            
            frame_count += 1
            
            # Frame skip logic: only process AI on every Nth frame
            should_process_ai = (frame_count % frame_skip) == 0
            
            if not should_process_ai:
                # Just yield the frame without AI processing
                ret, buffer = cv2.imencode('.jpg', frame, [int(cv2.IMWRITE_JPEG_QUALITY), 85])
                if ret:
                    yield (
                        b"--frame\r\n"
                        b"Content-Type: image/jpeg\r\n\r\n"
                        + buffer.tobytes()
                        + b"\r\n"
                    )
                continue
            
            # AI Processing (only on frame_skip intervals)
            try:
                results = detector.track_people(frame)
                
                # Log detection results for debugging
                if results and hasattr(results, 'boxes') and results.boxes is not None:
                    num_detections = len(results.boxes)
                    if num_detections > 0 and frame_count % 30 == 0:  # Log every 30 frames
                        print(f"🎯 [Stream {stream_id}] Frame {frame_count}: Detected {num_detections} person(s)")
                else:
                    if frame_count % 30 == 0:  # Log every 30 frames
                        print(f"⚠️ [Stream {stream_id}] Frame {frame_count}: No detections")
                
                if results and hasattr(results, 'boxes') and results.boxes is not None:
                    # Process each detection
                    for box in results.boxes:
                        x1, y1, x2, y2 = map(int, box.xyxy[0])
                        
                        # Get track ID
                        track_id_obj = getattr(box, 'id', None)
                        byte_id = int(track_id_obj[0]) if track_id_obj is not None else None
                        
                        if byte_id is not None:
                            if byte_id not in track_id_mapping:
                                track_id_mapping[byte_id] = next_track_id
                                next_track_id += 1
                            our_id = track_id_mapping[byte_id]
                        else:
                            our_id = None
                        
                        # Extract person crop for classification
                        person_crop = frame[y1:y2, x1:x2]
                        
                        # Get classification predictions
                        class_predictions = []
                        if person_crop.size > 0 and classifier.model is not None:
                            class_predictions = classifier.predict_top_n(person_crop, top_n=classifier_top_n)
                        
                        # Save to database if enabled
                        if db and our_id is not None:
                            try:
                                # Extract clothing category
                                clothing_category = None
                                if class_predictions:
                                    clothing_category = class_predictions[0][0]  # Get top prediction

                                # Unified color analysis
                                from src.ai.color_analysis_unified import analyze_person_colors, build_db_detection_data

                                color_results = analyze_person_colors(
                                    person_crop=person_crop,
                                    clothing_type=clothing_category or "Unknown",
                                    embedder=None  # No Re-ID for realtime
                                )

                                # Initialize image paths
                                image_path = None
                                bbox_image_path = None

                                # Upload person crop image if enabled
                                if save_images and storage is not None and person_crop.size > 0:
                                    try:
                                        object_name = f"detections/{effective_camera_id}/{video_id or 'no-video'}/{frame_count}_{our_id}_{uuid.uuid4().hex[:8]}.jpg"
                                        crop_copy = person_crop.copy()
                                        upload_future = _UPLOAD_EXECUTOR.submit(storage.upload_image, crop_copy, object_name)
                                        # Wait for upload to complete
                                        image_path = await asyncio.get_running_loop().run_in_executor(
                                            None, upload_future.result, 10
                                        )
                                    except Exception as e:
                                        print(f"⚠️ [Stream {stream_id}] Person image upload failed: {e}")

                                # Upload bbox frame image if enabled
                                if save_bbox_images and storage is not None:
                                    try:
                                        bbox_object_name = f"detections/{effective_camera_id}/{video_id or 'no-video'}/bbox_{frame_count}_{our_id}_{uuid.uuid4().hex[:8]}.jpg"
                                        bbox_frame = frame.copy()
                                        cv2.rectangle(bbox_frame, (x1, y1), (x2, y2), (0, 255, 255), 2)
                                        label_text = f"ID:{our_id} {clothing_category or 'Person'}"
                                        cv2.putText(bbox_frame, label_text, (x1, y1 - 10),
                                                   cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 255), 2)
                                        bbox_copy = bbox_frame.copy()
                                        bbox_upload_future = _UPLOAD_EXECUTOR.submit(storage.upload_image, bbox_copy, bbox_object_name)
                                        # Wait for upload to complete
                                        bbox_image_path = await asyncio.get_running_loop().run_in_executor(
                                            None, bbox_upload_future.result, 10
                                        )
                                    except Exception as e:
                                        print(f"⚠️ [Stream {stream_id}] Bbox image upload failed: {e}")

                                # Build standardized detection data
                                detection_data = build_db_detection_data(
                                    track_id=our_id,
                                    clothing_type=clothing_category or "unknown",
                                    confidence=class_predictions[0][1] if class_predictions else 0.0,
                                    color_results=color_results,
                                    bbox=[x1, y1, x2, y2],
                                    camera_id=effective_camera_id,
                                    video_id=video_id,
                                    video_time_offset=frame_count / fps,
                                    image_path=image_path or "",
                                    bbox_image_path=bbox_image_path or "",
                                )

                                # Insert into database (color data goes to detection_colors table)
                                detection_id = db.insert_detection(
                                    camera_id=detection_data['camera_id'],
                                    track_id=detection_data['track_id'],
                                    class_name=detection_data['class_name'],
                                    image_path=image_path,  # Pass None if not uploaded
                                    category=detection_data['category'],
                                    video_time_offset=detection_data['video_time_offset'],
                                    video_id=detection_data['video_id'],
                                    bbox=detection_data['bbox'],
                                    embedding=detection_data['embedding'],
                                )
                                
                                # Insert color data into detection_colors table
                                if detection_id:
                                    db.insert_detection_colors(
                                        detection_id=detection_id,
                                        top_colors=color_results.get('top_colors', []),
                                        brightness_groups=color_results.get('brightness_groups', {}),
                                        vibrancy_groups=color_results.get('vibrancy_groups', {}),
                                        temperature_groups=color_results.get('temperature_groups', {}),
                                        clothing_groups=color_results.get('clothing_color_groups', {}),
                                        primary_color=color_results.get('primary_detailed_color', 'unknown'),
                                        primary_tone_group=color_results.get('primary_tone_group', 'unknown'),
                                    )
                                
                                print(f"✅ [Stream {stream_id}] Saved track {our_id} with color: {detection_data['primary_detailed_color']}")

                            except Exception as db_error:
                                print(f"⚠️ [Stream {stream_id}] Database save error: {db_error}")
                                import traceback
                                traceback.print_exc()
                        
                        # Draw detector bbox
                        if show_detector_bbox:
                            cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
                        
                        # Draw classifier bbox (if different)
                        if show_classifier_bbox:
                            for idx, (cls_name, conf, bbox) in enumerate(class_predictions):
                                if bbox is not None:
                                    cx1, cy1, cx2, cy2 = bbox
                                    color = (255, 0, 255) if idx == 0 else (255, 128, 0)
                                    cv2.rectangle(frame, (cx1, cy1), (cx2, cy2), color, 1)
                        
                        # Prepare labels
                        labels = []
                        
                        # Track ID label
                        if show_detector_track_id and our_id is not None:
                            labels.append(f"ID:{our_id}")
                        
                        # Class name(s) label
                        if show_classifier_class_name and class_predictions:
                            for idx, (cls_name, conf, _) in enumerate(class_predictions):
                                if idx == 0:
                                    labels.append(f"{cls_name} ({conf:.2f})")
                                else:
                                    labels.append(f"  {cls_name} ({conf:.2f})")
                        
                        # Class count label
                        if show_classifier_count and class_predictions:
                            labels.append(f"[Classes: {len(class_predictions)}]")
                        
                        # Draw labels
                        if labels:
                            y_offset = y1 - 10
                            font_scale = 0.5
                            thickness = 1
                            
                            for label in labels:
                                (text_w, text_h), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, font_scale, thickness)
                                
                                # Background for text
                                cv2.rectangle(frame, (x1, y_offset - text_h - 4), (x1 + text_w, y_offset + 4), (0, 0, 0), -1)
                                cv2.putText(frame, label, (x1, y_offset), cv2.FONT_HERSHEY_SIMPLEX, font_scale, (255, 255, 255), thickness)
                                
                                y_offset -= (text_h + 8)
            except Exception as ai_error:
                print(f"⚠️ [Stream {stream_id}] AI processing error at frame {frame_count}: {ai_error}")
                import traceback
                traceback.print_exc()
            
            # Yield the processed frame
            ret, buffer = cv2.imencode('.jpg', frame, [int(cv2.IMWRITE_JPEG_QUALITY), 85])
            if ret:
                yield (
                    b"--frame\r\n"
                    b"Content-Type: image/jpeg\r\n\r\n"
                    + buffer.tobytes()
                    + b"\r\n"
                )
            
            # Control frame rate to match video speed
            current_time = asyncio.get_event_loop().time()
            elapsed = current_time - last_process_time
            if elapsed < frame_time:
                await asyncio.sleep(frame_time - elapsed)
            last_process_time = current_time
    except Exception as e:
        print(f"❌ [Stream {stream_id}] AI processing error at frame {frame_count}: {e}")
        import traceback
        traceback.print_exc()
    finally:
        cap.release()
        print(f"🛑 [Stream {stream_id}] Stream ended")


@router.get("/stream-analyze")
async def stream_analyze_video(
    video_path: str = Query(..., description="Absolute path to video file"),
    camera_id: Optional[str] = Query(None, description="Custom camera ID (default: auto-generated stream_<id>)"),
    show_detector_bbox: bool = Query(True, description="Show detector bounding boxes"),
    show_detector_track_id: bool = Query(True, description="Show detector track IDs"),
    show_classifier_bbox: bool = Query(False, description="Show classifier bounding boxes"),
    show_classifier_class_name: bool = Query(True, description="Show classifier class names"),
    show_classifier_count: bool = Query(False, description="Show total number of classes detected"),
    classifier_top_n: str = Query("1", description="Number of top class predictions to show (int or 'all')"),
    save_to_db: bool = Query(False, description="Save detection data to database"),
    frame_skip: int = Query(1, description="Process every N-th frame (default: 1 = all frames)"),
    save_images: bool = Query(True, description="Save person crop images to storage (only when save_to_db=true)"),
    save_bbox_images: bool = Query(True, description="Save bbox frame images to storage (only when save_to_db=true)"),
):
    """
    Stream MJPEG of video with real-time AI analysis.
    
    Query Parameters:
    - video_path: Absolute path to video file (required)
    - camera_id: Custom camera ID for database tagging (default: auto-generated)
    - show_detector_bbox: Show green bounding boxes from person detector (default: true)
    - show_detector_track_id: Show track ID labels (default: true)
    - show_classifier_bbox: Show classifier bounding boxes (default: false)
    - show_classifier_class_name: Show clothing class names (default: true)
    - show_classifier_count: Show count of detected classes (default: false)
    - classifier_top_n: Number of top predictions to display, or "all" (default: "1")
    - frame_skip: Process every N-th frame for AI detection (default: 1 = all frames)
    - save_images: Save person crop images to storage (default: true, only when save_to_db=true)
    - save_bbox_images: Save bbox frame images to storage (default: true, only when save_to_db=true)

    Example:
    /api/video/stream-analyze?video_path=/path/to/video.mp4&camera_id=CAM-01&show_detector_bbox=true&classifier_top_n=3&frame_skip=5&save_images=true&save_bbox_images=true
    
    Returns:
        MJPEG stream for use in <img src="...">
    """
    # Validate video path
    if not os.path.exists(video_path):
        raise HTTPException(status_code=404, detail=f"Video file not found: {video_path}")
    
    # Generate unique stream ID (use camera_id if provided, otherwise auto-generate)
    import uuid
    if camera_id:
        # Sanitize camera_id for safe URL usage
        safe_camera_id = re.sub(r'[^a-zA-Z0-9_-]', '_', camera_id)
        stream_id = f"analyze_{safe_camera_id}_{uuid.uuid4().hex[:4]}"
    else:
        stream_id = f"analyze_{uuid.uuid4().hex[:8]}"
    
    # Create stop event
    stop_event = asyncio.Event()
    _STREAM_ANALYSIS_ACTIVE[stream_id] = stop_event
    
    # Parse top_n
    parsed_top_n = _parse_top_n(classifier_top_n)
    
    async def _cleanup_wrapper():
        """Wrapper to clean up when stream ends."""
        try:
            async for frame in _realtime_analysis_generator(
                video_path=video_path,
                stream_id=stream_id,
                stop_event=stop_event,
                show_detector_bbox=show_detector_bbox,
                show_detector_track_id=show_detector_track_id,
                show_classifier_bbox=show_classifier_bbox,
                show_classifier_class_name=show_classifier_class_name,
                show_classifier_count=show_classifier_count,
                classifier_top_n=parsed_top_n,
                save_to_db=save_to_db,
                camera_id=camera_id,
                frame_skip=frame_skip,
                save_images=save_images,
                save_bbox_images=save_bbox_images,
            ):
                yield frame
        finally:
            _STREAM_ANALYSIS_ACTIVE.pop(stream_id, None)
    
    return StreamingResponse(
        _cleanup_wrapper(),
        media_type="multipart/x-mixed-replace; boundary=frame",
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate, max-age=0",
            "Pragma": "no-cache",
            "Expires": "0",
            "X-Stream-Id": stream_id,
        }
    )


@router.post("/stream-analyze/{stream_id}/stop")
async def stop_stream_analyze(stream_id: str):
    """Stop an active real-time analysis stream."""
    event = _STREAM_ANALYSIS_ACTIVE.get(stream_id)
    if event is None:
        raise HTTPException(status_code=404, detail=f"No active stream with ID '{stream_id}'")
    
    event.set()
    return {"status": "success", "message": f"Stream {stream_id} stop requested"}


@router.get("/stream-analyze/active")
async def list_active_stream_analysis():
    """List all active real-time analysis streams."""
    return {"active_streams": list(_STREAM_ANALYSIS_ACTIVE.keys())}


@router.post("/analyze-cv2")
async def analyze_video_cv2(
    request: dict,
):
    """
    Analyze video with AI and display in OpenCV window.
    
    Body Parameters:
    - video_path: Absolute path to video file
    - show_detector_bbox: Show detector bounding boxes (default: true)
    - show_detector_track_id: Show track ID labels (default: true)
    - show_classifier_bbox: Show classifier bounding boxes (default: false)
    - show_classifier_class_name: Show clothing class names (default: true)
    - show_classifier_count: Show count of detected classes (default: false)
    - classifier_top_n: Number of top predictions to display (int or "all")
    - save_to_db: Save detection data to database (default: false)
    - camera_id: Camera identifier for database tagging (default: auto-generated)
    - save_images: Save person crop images to storage (default: true, only when save_to_db=true)
    - save_bbox_images: Save bbox frame images to storage (default: true, only when save_to_db=true)

    Returns:
        Status of the analysis task
    """
    video_path = request.get("video_path")
    print(f"📥 [CV2 API] Received request: {request}")
    if not video_path or not os.path.exists(video_path):
        raise HTTPException(status_code=404, detail=f"Video file not found: {video_path}")
    
    # Extract parameters with defaults
    show_detector_bbox = request.get("show_detector_bbox", True)
    show_detector_track_id = request.get("show_detector_track_id", True)
    show_classifier_bbox = request.get("show_classifier_bbox", False)
    show_classifier_class_name = request.get("show_classifier_class_name", True)
    show_classifier_count = request.get("show_classifier_count", False)
    classifier_top_n = request.get("classifier_top_n", 1)
    save_to_db = request.get("save_to_db", False)
    camera_id = request.get("camera_id", None)
    save_images = request.get("save_images", True)
    save_bbox_images = request.get("save_bbox_images", True)

    print(f"📋 [CV2 API] Parsed params: save_to_db={save_to_db}, camera_id={camera_id}, save_images={save_images}, save_bbox_images={save_bbox_images}")
    
    # Start background task for CV2 analysis
    import asyncio
    task_id = f"cv2_{uuid.uuid4().hex[:8]}"
    
    async def run_cv2_analysis():
        """Run CV2 analysis in background."""
        try:
            print(f"[VideoController] Using refactored VideoProcessor for CV2 analysis")
            processor, pool = await _get_video_processor()

            stats = await processor.process_video(
                source=video_path,
                camera_id=camera_id or f"cv2_{int(time.time())}",
                video_id=None,  # No video registration for CV2 mode
                frame_skip=1,  # CV2 processes all frames
                save_to_db=save_to_db,
                save_images=save_images,
            )
            print(f"[VideoController] CV2 analysis completed: {stats.to_dict()}")
        except Exception as e:
            print(f"❌ CV2 Analysis Error: {e}")
            import traceback
            print(traceback.format_exc())
    
    # Create and start background task
    asyncio.create_task(run_cv2_analysis())
    
    return {
        "status": "success",
        "message": "CV2 analysis started",
        "task_id": task_id,
        "info": "Window will open on server machine. Press 'q' to stop."
    }


@router.post("/analyze-background")
async def analyze_video_background(
    request: dict,
):
    """
    Analyze video in background without any display output.
    Saves detections to database and reports progress via status endpoint.

    Body Parameters:
    - video_path: Absolute path to video file
    - camera_id: Camera identifier for database tagging (default: auto-generated)
    - frame_skip: Process every N-th frame (default: 5)
    - save_to_db: Save detection data to database (default: true)
    - save_images: Save person crop images to storage (default: true, only when save_to_db=true)
    - save_bbox_images: Save bbox frame images to storage (default: true, only when save_to_db=true)

    Returns:
        Status of the background analysis task with task_id for tracking
    """
    video_path = request.get("video_path")
    print(f"📥 [BACKGROUND API] Received request: {request}")

    if not video_path or not os.path.exists(video_path):
        raise HTTPException(status_code=404, detail=f"Video file not found: {video_path}")

    # Extract parameters with defaults
    camera_id = request.get("camera_id", None)
    frame_skip = request.get("frame_skip", 5)
    save_to_db = request.get("save_to_db", True)
    save_images = request.get("save_images", True)
    save_bbox_images = request.get("save_bbox_images", True)

    # Validate and fix camera_id - reject "background" as it's not a valid camera identifier
    if not camera_id or camera_id.lower() == "background":
        # Auto-generate camera_id from filename or timestamp
        video_filename = os.path.basename(video_path)
        video_name = os.path.splitext(video_filename)[0]
        # Clean up the name to be a valid camera_id (alphanumeric, hyphens, underscores only)
        camera_id = re.sub(r'[^a-zA-Z0-9_-]', '_', video_name)
        # If still empty or too short, use timestamp
        if len(camera_id) < 3:
            camera_id = f"cam_{int(time.time())}"
        print(f"⚠️ [BACKGROUND API] Invalid camera_id provided ('{request.get('camera_id')}'), auto-generated: {camera_id}")

    print(f"📋 [BACKGROUND API] Parsed params: camera_id={camera_id}, frame_skip={frame_skip}, save_to_db={save_to_db}, save_images={save_images}, save_bbox_images={save_bbox_images}")

    # Generate task ID
    task_id = f"bg_{uuid.uuid4().hex[:8]}"

    async def run_background_analysis():
        """Run background analysis."""
        try:
            from src.services.background_processor import process_video_background_task

            await process_video_background_task(
                video_path=video_path,
                camera_id=camera_id,
                frame_skip=frame_skip,
                save_to_db=save_to_db,
                task_id=task_id,
                save_images=save_images,
                save_bbox_images=save_bbox_images,
            )
        except Exception as e:
            print(f"❌ Background Analysis Error: {e}")
            import traceback
            print(traceback.format_exc())

    # Create and start background task
    asyncio.create_task(run_background_analysis())

    return {
        "status": "success",
        "message": "Background analysis started",
        "task_id": task_id,
        "info": "Processing without display. Use /background-status/{task_id} to check progress."
    }


@router.get("/background-status/{task_id}")
async def get_background_status(task_id: str):
    """
    Get the status of a background processing task.

    Returns:
        Current status including frames_processed, total_frames, detections_count, etc.
    """
    from src.services.background_processor import get_background_task_status

    status = get_background_task_status(task_id)
    if status is None:
        raise HTTPException(status_code=404, detail=f"Task not found: {task_id}")

    return {
        "task_id": task_id,
        "status": status.get("status"),
        "frames_processed": status.get("frames_processed", 0),
        "total_frames": status.get("total_frames", 0),
        "detections_count": status.get("detections_count", 0),
        "fps": status.get("fps", 0.0),
        "error": status.get("error"),
    }


@router.get("/background-tasks")
async def list_background_tasks():
    """
    List all active background processing tasks.

    Returns:
        List of task IDs currently being processed
    """
    from src.services.background_processor import _BACKGROUND_PROCESSING_STATE

    return {
        "active_tasks": list(_BACKGROUND_PROCESSING_STATE.keys()),
        "tasks": [
            {
                "task_id": task_id,
                "status": state.get("status"),
                "frames_processed": state.get("frames_processed", 0),
                "total_frames": state.get("total_frames", 0),
                "progress_pct": round(state.get("frames_processed", 0) / state.get("total_frames", 1) * 100, 1) if state.get("total_frames", 0) > 0 else 0,
            }
            for task_id, state in _BACKGROUND_PROCESSING_STATE.items()
        ]
    }
