"""
video_queue.py - API Routes for Video Queue Management

Provides endpoints for:
- Adding videos to queue
- Getting global status
- Reordering queue
- Pausing/resuming videos
- Removing videos from queue
"""
from fastapi import APIRouter, HTTPException, BackgroundTasks, UploadFile, File, Form
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
import asyncio
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from services.video_queue_service import (
    get_video_queue_service,
    VideoQueueService,
    JobStatus
)
from services.database import DatabaseService

router = APIRouter(prefix="/api/video-queue", tags=["Video Queue"])

# Pydantic models
class AddVideoRequest(BaseModel):
    source: str
    camera_id: str
    display_mode: str = "background"
    priority: int = 0
    original_filename: Optional[str] = None
    width: Optional[int] = None
    height: Optional[int] = None
    fps: Optional[float] = None
    duration_sec: Optional[float] = None
    # Processing options
    save_to_db: bool = True
    save_images: bool = True
    save_bbox_images: bool = True
    frame_skip: int = 5
    show_detector_bbox: bool = True
    show_detector_track_id: bool = True
    show_classifier_class_name: bool = True
    classifier_top_n: int = 2


class ReorderRequest(BaseModel):
    job_id: str
    new_position: int


class JobIdRequest(BaseModel):
    job_id: str


class JobResponse(BaseModel):
    id: str
    source: str
    camera_id: str
    display_mode: str
    status: str
    priority: int
    created_at: float
    started_at: Optional[float]
    completed_at: Optional[float]
    progress_pct: int
    frames_processed: int
    total_frames: int
    detections_count: int
    error_message: Optional[str]
    original_filename: Optional[str]
    width: Optional[int]
    height: Optional[int]
    fps: Optional[float]
    duration_sec: Optional[float]


class GlobalStatusResponse(BaseModel):
    current_job: Optional[Dict[str, Any]]
    queue: List[Dict[str, Any]]
    paused: List[Dict[str, Any]]
    completed: List[Dict[str, Any]]
    failed: List[Dict[str, Any]]
    stopped: List[Dict[str, Any]]
    stats: Dict[str, int]


# Helper to get service
async def _get_service() -> VideoQueueService:
    return await get_video_queue_service()


@router.post("/add", response_model=Dict[str, str])
async def add_video_to_queue(request: AddVideoRequest):
    """
    Add a video to the processing queue.
    
    The video will be processed in order based on priority and queue position.
    """
    try:
        service = await _get_service()
        
        job_id = await service.add_video(
            source=request.source,
            camera_id=request.camera_id,
            display_mode=request.display_mode,
            priority=request.priority,
            original_filename=request.original_filename,
            width=request.width,
            height=request.height,
            fps=request.fps,
            duration_sec=request.duration_sec,
            save_to_db=request.save_to_db,
            save_images=request.save_images,
            save_bbox_images=request.save_bbox_images,
            frame_skip=request.frame_skip,
            show_detector_bbox=request.show_detector_bbox,
            show_detector_track_id=request.show_detector_track_id,
            show_classifier_class_name=request.show_classifier_class_name,
            classifier_top_n=request.classifier_top_n,
        )
        
        return {
            "status": "added",
            "job_id": job_id,
            "message": f"Video added to queue with job ID: {job_id}"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/upload-add")
async def upload_and_add_to_queue(
    file: UploadFile = File(...),
    camera_id: str = Form(...),
    display_mode: str = Form("background"),
    priority: int = Form(0),
    save_to_db: bool = Form(True),
    save_images: bool = Form(True),
    save_bbox_images: bool = Form(True),
    frame_skip: int = Form(5),
):
    """
    Upload a video file and add it to the processing queue.
    """
    import shutil
    import os
    import uuid
    import cv2
    
    UPLOAD_DIR = "temp_queue_videos"
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    
    try:
        # Save uploaded file
        temp_id = uuid.uuid4().hex[:12]
        temp_filename = f"queue_{temp_id}_{file.filename}"
        file_path = os.path.abspath(os.path.join(UPLOAD_DIR, temp_filename))
        
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        
        # Verify video and get metadata
        cap = cv2.VideoCapture(file_path)
        if not cap.isOpened():
            os.remove(file_path)
            raise HTTPException(status_code=400, detail=f"Cannot open video file: {file.filename}")
        
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        duration_sec = total_frames / fps if fps > 0 else None
        cap.release()
        
        # Add to queue
        service = await _get_service()
        job_id = await service.add_video(
            source=file_path,
            camera_id=camera_id,
            display_mode=display_mode,
            priority=priority,
            original_filename=file.filename,
            width=width,
            height=height,
            fps=fps,
            duration_sec=duration_sec,
            save_to_db=save_to_db,
            save_images=save_images,
            save_bbox_images=save_bbox_images,
            frame_skip=frame_skip,
        )
        
        return {
            "status": "added",
            "job_id": job_id,
            "file_path": file_path,
            "original_filename": file.filename,
            "video_info": {
                "width": width,
                "height": height,
                "fps": fps,
                "total_frames": total_frames,
                "duration_sec": duration_sec,
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/status", response_model=GlobalStatusResponse)
async def get_global_status():
    """
    Get global status of all video processing jobs (from memory).

    Returns:
    - current_job: The job currently being processed
    - queue: List of pending jobs in processing order
    - paused: List of paused jobs
    - completed: List of completed jobs
    - failed: List of failed jobs
    - stats: Summary statistics
    """
    try:
        service = await _get_service()
        status = service.get_global_status()
        return GlobalStatusResponse(**status)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


import json
from datetime import datetime

# อย่าลืม import GlobalStatusResponse, DatabaseService ที่คุณใช้อยู่

def parse_dt_to_timestamp(dt_val):
    """Helper สำหรับแปลง Datetime หรือ String จาก DB ให้เป็น Timestamp อย่างปลอดภัย"""
    if not dt_val:
        return None
    if hasattr(dt_val, "timestamp"):  # กรณี DB คืนค่าเป็น datetime object
        return dt_val.timestamp()
    if isinstance(dt_val, str):       # กรณี DB คืนค่าเป็น string
        try:
            # แทนที่เว้นวรรคด้วย T เพื่อรองรับ isoformat
            return datetime.fromisoformat(dt_val.replace(" ", "T")).timestamp()
        except ValueError:
            return None
    return None

@router.get("/db-status", response_model=GlobalStatusResponse)
async def get_db_status():
    """
    Get global status of all video processing jobs from database.
    This includes all persisted jobs, not just current in-memory state.
    """
    try:
        db = DatabaseService()

        with db.conn.cursor() as cur:
            # Fetch all jobs from database
            cur.execute("""
                SELECT
                    job_id, source, camera_id, display_mode, status,
                    priority, created_at, started_at, completed_at,
                    progress_pct, frames_processed, total_frames, detections_count,
                    error_message, video_metadata
                FROM video_queue
                ORDER BY priority DESC, created_at ASC
            """)
            
            rows = cur.fetchall()

        # สร้าง Group รอไว้สำหรับการจัดหมวดหมู่ (ใช้ Dictionary lookup ทำงานเร็วกว่า if/elif)
        current_job = None
        categorized = {
            "pending": [],
            "paused": [],
            "completed": [],
            "failed": [],
            "stopped": []
        }

        for row in rows:
            # ใช้ Index ในการอ้างอิงข้อมูล เร็วกว่า dict(zip(columns, row)) ในลูป
            # 0:job_id, 1:source, 2:camera_id, 3:display_mode, 4:status,
            # 5:priority, 6:created_at, 7:started_at, 8:completed_at,
            # 9:progress_pct, 10:frames_processed, 11:total_frames, 12:detections_count,
            # 13:error_message, 14:video_metadata

            # จัดการ metadata แบบป้องกัน error
            raw_meta = row[14]
            if raw_meta and isinstance(raw_meta, str):
                try:
                    metadata = json.loads(raw_meta)
                except json.JSONDecodeError:
                    metadata = {}
            else:
                metadata = raw_meta or {}

            status = row[4]

            # สร้าง Job Dictionary โดยเรียกใช้ Helper function สำหรับเวลา
            job = {
                "id": row[0],
                "source": row[1],
                "camera_id": row[2],
                "display_mode": row[3],
                "status": status,
                "priority": row[5],
                "created_at": parse_dt_to_timestamp(row[6]),
                "started_at": parse_dt_to_timestamp(row[7]),
                "completed_at": parse_dt_to_timestamp(row[8]),
                "progress_pct": row[9] or 0,
                "frames_processed": row[10] or 0,
                "total_frames": row[11] or 0,
                "detections_count": row[12] or 0,
                "error_message": row[13] or "",
                "original_filename": metadata.get("original_filename", ""),
                "width": metadata.get("width"),
                "height": metadata.get("height"),
                "fps": metadata.get("fps"),
                "duration_sec": metadata.get("duration_sec"),
            }

            # จัดกลุ่มตาม Status O(1)
            if status == "processing":
                current_job = job
            elif status in categorized:
                categorized[status].append(job)
        response_data = {
            "current_job": current_job,
            "queue": categorized["pending"],
            "paused": categorized["paused"],
            "completed": categorized["completed"],
            "failed": categorized["failed"],
            "stopped": categorized["stopped"],
            "stats": {
                "total_jobs": len(rows),
                "pending_count": len(categorized["pending"]),
                "processing_count": 1 if current_job else 0,
                "paused_count": len(categorized["paused"]),
                "completed_count": len(categorized["completed"]),
                "failed_count": len(categorized["failed"]),
                "stopped_count": len(categorized["stopped"]),
            }
        }

        # สรุปผลเตรียม Return
        return GlobalStatusResponse(**response_data)

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/job/{job_id}", response_model=Dict[str, Any])
async def get_job_details(job_id: str):
    """Get details of a specific job"""
    try:
        service = await _get_service()
        job = service.get_job(job_id)
        
        if not job:
            raise HTTPException(status_code=404, detail=f"Job {job_id} not found")
        
        return job.to_dict()
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/jobs", response_model=List[Dict[str, Any]])
async def get_all_jobs():
    """Get all jobs"""
    try:
        service = await _get_service()
        jobs = service.get_all_jobs()
        return [j.to_dict() for j in jobs]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/queue", response_model=List[Dict[str, Any]])
async def get_queue():
    """Get pending jobs in queue order"""
    try:
        service = await _get_service()
        queue = service.get_queue()
        return [j.to_dict() for j in queue]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/reorder")
async def reorder_queue(request: ReorderRequest):
    """
    Reorder a job in the queue by moving it to a new position.
    
    new_position: 0 = first in queue, 1 = second, etc.
    """
    try:
        service = await _get_service()
        success = await service.reorder_queue(request.job_id, request.new_position)
        
        if not success:
            raise HTTPException(
                status_code=400,
                detail=f"Failed to reorder job {request.job_id}. It may not exist or is not in a reorderable state."
            )
        
        return {
            "status": "reordered",
            "job_id": request.job_id,
            "new_position": request.new_position
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/pause")
async def pause_job(request: JobIdRequest):
    """Pause a currently processing job"""
    try:
        service = await _get_service()
        success = await service.pause_job(request.job_id)
        
        if not success:
            raise HTTPException(
                status_code=400,
                detail=f"Failed to pause job {request.job_id}. It may not exist or is not currently processing."
            )
        
        return {
            "status": "paused",
            "job_id": request.job_id
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/resume")
async def resume_job(request: JobIdRequest):
    """Resume a paused job"""
    try:
        service = await _get_service()
        success = await service.resume_job(request.job_id)
        
        if not success:
            raise HTTPException(
                status_code=400,
                detail=f"Failed to resume job {request.job_id}. It may not exist or is not paused."
            )
        
        return {
            "status": "resumed",
            "job_id": request.job_id
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/stop")
async def stop_job(request: JobIdRequest):
    """Stop a processing or pending job"""
    try:
        service = await _get_service()
        success = await service.stop_job(request.job_id)
        
        if not success:
            raise HTTPException(
                status_code=400,
                detail=f"Failed to stop job {request.job_id}. It may not exist."
            )
        
        return {
            "status": "stopped",
            "job_id": request.job_id
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/remove/{job_id}")
async def remove_job(job_id: str):
    """Remove a job from the queue (only pending or paused jobs)"""
    try:
        service = await _get_service()
        success = await service.remove_job(job_id)
        
        if not success:
            raise HTTPException(
                status_code=400,
                detail=f"Failed to remove job {job_id}. It may not exist, is currently processing, or has already completed."
            )
        
        return {
            "status": "removed",
            "job_id": job_id
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/clear-completed")
async def clear_completed_jobs():
    """Clear all completed, failed, and stopped jobs from the system"""
    try:
        service = await _get_service()
        
        removed_count = 0
        for job in list(service.get_all_jobs()):
            if job.status in [JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.STOPPED, JobStatus.CANCELLED]:
                if await service.remove_job(job.id):
                    removed_count += 1
        
        return {
            "status": "cleared",
            "removed_count": removed_count
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class StartImmediatelyRequest(BaseModel):
    job_id: str


class ReprocessRequest(BaseModel):
    job_id: str
    start_immediately: bool = False


@router.post("/start-immediately")
async def start_queue_job_immediately(request: StartImmediatelyRequest):
    """Stop current job and start this queue job immediately."""
    try:
        service = await _get_service()
        success = await service.start_queue_job_immediately(request.job_id)
        if not success:
            raise HTTPException(status_code=400, detail=f"Failed to start job {request.job_id}")
        return {"status": "started_immediately", "job_id": request.job_id}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/cancel-and-remove")
async def cancel_and_remove_job(request: JobIdRequest):
    """Cancel current processing and remove from queue."""
    try:
        service = await _get_service()
        success = await service.cancel_and_remove_job(request.job_id)
        if not success:
            raise HTTPException(status_code=400, detail=f"Failed to cancel job {request.job_id}")
        return {"status": "cancelled_and_removed", "job_id": request.job_id}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/reprocess")
async def reprocess_video(request: ReprocessRequest):
    """Reprocess a completed video by creating a new job."""
    try:
        service = await _get_service()
        new_job_id = await service.reprocess_video(request.job_id, request.start_immediately)
        if not new_job_id:
            raise HTTPException(status_code=400, detail=f"Failed to reprocess job {request.job_id}")
        return {"status": "reprocess_created", "original_job_id": request.job_id, "new_job_id": new_job_id}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/resume-and-replace")
async def resume_and_replace(request: JobIdRequest):
    """Resume a paused job and replace the current queue with it."""
    try:
        service = await _get_service()
        success = await service.resume_and_replace(request.job_id)
        if not success:
            raise HTTPException(status_code=400, detail=f"Failed to resume job {request.job_id}")
        return {"status": "resumed_and_replaced", "job_id": request.job_id}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/history")
async def get_processing_history(limit: int = 50):
    """
    Get processing history from database.
    
    This includes jobs that may have been persisted across server restarts.
    """
    try:
        db = DatabaseService()
        
        with db.conn.cursor() as cur:
            cur.execute("""
                SELECT 
                    job_id, source, camera_id, display_mode, status,
                    priority, created_at, started_at, completed_at,
                    progress_pct, frames_processed, total_frames, detections_count,
                    error_message, video_metadata
                FROM video_queue
                ORDER BY created_at DESC
                LIMIT %s
            """, (limit,))
            
            columns = [desc[0] for desc in cur.description]
            rows = cur.fetchall()
            
            history = []
            for row in rows:
                row_dict = dict(zip(columns, row))
                # Parse metadata
                metadata = row_dict.pop("video_metadata", {}) or {}
                if isinstance(metadata, str):
                    import json
                    metadata = json.loads(metadata)
                row_dict.update(metadata)
                history.append(row_dict)
            
            return {
                "history": history,
                "count": len(history)
            }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
