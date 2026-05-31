import json
from pathlib import Path
from typing import Any

from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, PlainTextResponse
from pydantic import BaseModel, Field

from src.config_loader import (
    get_json_storage_index,
    get_json_storage_root,
    get_storage_mode,
)
from src.services.json_investigation_service import JsonInvestigationService
from src.services.json_video_queue_service import get_json_video_queue_service

router = APIRouter(prefix="/api/json", tags=["JSON Storage"])


class JsonJobUpsert(BaseModel):
    id: str = Field(..., min_length=1)
    label: str | None = None
    source: str | None = None
    status: str = "pending"
    output_dir: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class JsonJobPatch(BaseModel):
    label: str | None = None
    source: str | None = None
    status: str | None = None
    output_dir: str | None = None
    metadata: dict[str, Any] | None = None


class JsonQueueAddRequest(BaseModel):
    source: str
    camera_id: str
    display_mode: str = "background"
    priority: int = 0
    original_filename: str | None = None
    width: int | None = None
    height: int | None = None
    fps: float | None = None
    duration_sec: float | None = None
    frame_skip: int = 2
    save_images: bool = False
    save_bbox_images: bool = False


class JsonQueueJobRequest(BaseModel):
    job_id: str


class JsonClearRequest(BaseModel):
    include_orphan_results: bool = False


class JsonQueueReprocessRequest(BaseModel):
    job_id: str
    start_immediately: bool = False


class JsonQueueReorderRequest(BaseModel):
    job_id: str
    new_position: int


def _json_root() -> Path:
    return Path(get_json_storage_root()).resolve()


def _index_path() -> Path:
    path = Path(get_json_storage_index())
    if not path.is_absolute():
        path = Path.cwd() / path
    return path.resolve()


def _safe_path(root: Path, *parts: str) -> Path:
    path = root.joinpath(*parts).resolve()
    if path != root and root not in path.parents:
        raise HTTPException(status_code=400, detail="Path escapes JSON storage root")
    return path


def _read_json(path: Path) -> Any:
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"JSON file not found: {path.name}")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise HTTPException(status_code=500, detail=f"Invalid JSON in {path.name}: {e}") from e
    except OSError as e:
        raise HTTPException(status_code=500, detail=f"Cannot read {path.name}: {e}") from e


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    try:
        tmp_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        tmp_path.replace(path)
    except OSError as e:
        raise HTTPException(status_code=500, detail=f"Cannot write {path.name}: {e}") from e


def _load_index() -> dict[str, Any]:
    path = _index_path()
    if not path.exists():
        return {"jobs": []}
    data = _read_json(path)
    if not isinstance(data, dict):
        raise HTTPException(status_code=500, detail="JSON job index must be an object")
    if not isinstance(data.get("jobs"), list):
        data["jobs"] = []
    return data


def _save_index(index: dict[str, Any]) -> None:
    _write_json(_index_path(), index)


def _job_dir(job_id: str) -> Path:
    root = _json_root()
    path = _safe_path(root, job_id)
    if not path.exists() or not path.is_dir():
        raise HTTPException(status_code=404, detail=f"JSON job not found: {job_id}")
    return path


def _job_files(path: Path) -> dict[str, dict[str, Any]]:
    known_files = [
        "prediction_results.json",
        "viewer_reid_summary.json",
        "timing_summary.json",
        "gpu_progress.json",
        "resource_progress.json",
        "timing_progress.json",
        "summary.md",
        "video_prediction_viewer.html",
    ]
    files: dict[str, dict[str, Any]] = {}
    for name in known_files:
        file_path = path / name
        files[name] = {
            "exists": file_path.exists(),
            "size_bytes": file_path.stat().st_size if file_path.exists() else 0,
        }
    return files


def _read_optional_metadata(path: Path) -> dict[str, Any] | None:
    results_path = path / "prediction_results.json"
    if not results_path.exists():
        return None
    data = _read_json(results_path)
    metadata = data.get("metadata") if isinstance(data, dict) else None
    return metadata if isinstance(metadata, dict) else None


@router.get("/status")
async def json_storage_status():
    root = _json_root()
    index_path = _index_path()
    return {
        "storage_mode": get_storage_mode(),
        "json_root": str(root),
        "json_root_exists": root.exists(),
        "json_index": str(index_path),
        "json_index_exists": index_path.exists(),
    }


@router.get("/stats")
async def json_storage_stats():
    return JsonInvestigationService().stats()


@router.delete("/clear")
async def clear_json_storage(include_orphan_results: bool = Query(False)):
    return JsonInvestigationService().clear(include_orphan_results=include_orphan_results)


@router.post("/clear")
async def clear_json_storage_post(request: JsonClearRequest):
    return JsonInvestigationService().clear(include_orphan_results=request.include_orphan_results)


@router.get("/queue/status")
async def get_json_queue_status():
    service = await get_json_video_queue_service()
    return service.get_global_status()


@router.post("/queue/add")
async def add_json_queue_job(request: JsonQueueAddRequest):
    service = await get_json_video_queue_service()
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
        frame_skip=request.frame_skip,
        save_images=request.save_images,
        save_bbox_images=request.save_bbox_images,
    )
    return {
        "status": "added",
        "job_id": job_id,
        "message": f"Video added to JSON queue with job ID: {job_id}",
    }


@router.post("/queue/upload-add")
async def upload_and_add_json_queue_job(
    file: UploadFile = File(...),
    camera_id: str = Form(...),
    display_mode: str = Form("background"),
    priority: int = Form(0),
    save_images: bool = Form(False),
    save_bbox_images: bool = Form(False),
    frame_skip: int = Form(2),
):
    import os
    import shutil
    import uuid

    import cv2

    upload_dir = Path("temp_queue_videos")
    upload_dir.mkdir(parents=True, exist_ok=True)
    temp_id = uuid.uuid4().hex[:12]
    temp_filename = f"json_queue_{temp_id}_{file.filename}"
    file_path = Path(os.path.abspath(upload_dir / temp_filename))

    try:
        with file_path.open("wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        cap = cv2.VideoCapture(str(file_path))
        if not cap.isOpened():
            file_path.unlink(missing_ok=True)
            raise HTTPException(status_code=400, detail=f"Cannot open video file: {file.filename}")
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        duration_sec = total_frames / fps if fps > 0 else None
        cap.release()

        service = await get_json_video_queue_service()
        job_id = await service.add_video(
            source=str(file_path),
            camera_id=camera_id,
            display_mode=display_mode,
            priority=priority,
            original_filename=file.filename,
            width=width,
            height=height,
            fps=fps,
            duration_sec=duration_sec,
            frame_skip=frame_skip,
            save_images=save_images,
            save_bbox_images=save_bbox_images,
        )
        return {
            "status": "added",
            "job_id": job_id,
            "file_path": str(file_path),
            "video_info": {
                "width": width,
                "height": height,
                "fps": fps,
                "total_frames": total_frames,
                "duration_sec": duration_sec,
            },
        }
    except HTTPException:
        raise
    except Exception as e:
        file_path.unlink(missing_ok=True)
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/queue/pause")
async def pause_json_queue_job(request: JsonQueueJobRequest):
    service = await get_json_video_queue_service()
    if not await service.pause_job(request.job_id):
        raise HTTPException(status_code=400, detail=f"Failed to pause job {request.job_id}")
    return {"status": "paused", "job_id": request.job_id}


@router.post("/queue/resume")
async def resume_json_queue_job(request: JsonQueueJobRequest):
    service = await get_json_video_queue_service()
    if not await service.resume_job(request.job_id):
        raise HTTPException(status_code=400, detail=f"Failed to resume job {request.job_id}")
    return {"status": "resumed", "job_id": request.job_id}


@router.post("/queue/stop")
async def stop_json_queue_job(request: JsonQueueJobRequest):
    service = await get_json_video_queue_service()
    if not await service.stop_job(request.job_id):
        raise HTTPException(status_code=400, detail=f"Failed to stop job {request.job_id}")
    return {"status": "stopped", "job_id": request.job_id}


@router.delete("/queue/remove/{job_id}")
async def remove_json_queue_job(job_id: str):
    service = await get_json_video_queue_service()
    if not await service.remove_job(job_id):
        raise HTTPException(status_code=400, detail=f"Failed to remove job {job_id}")
    return {"status": "removed", "job_id": job_id}


@router.delete("/queue/clear-completed")
async def clear_completed_json_queue_jobs():
    service = await get_json_video_queue_service()
    removed_count = await service.clear_completed()
    return {"status": "cleared", "removed_count": removed_count}


@router.post("/queue/reorder")
async def reorder_json_queue_job(request: JsonQueueReorderRequest):
    service = await get_json_video_queue_service()
    if not await service.reorder_queue(request.job_id, request.new_position):
        raise HTTPException(status_code=400, detail=f"Failed to reorder job {request.job_id}")
    return {"status": "reordered", "job_id": request.job_id, "new_position": request.new_position}


@router.post("/queue/start-immediately")
async def start_json_queue_job_immediately(request: JsonQueueJobRequest):
    service = await get_json_video_queue_service()
    if not await service.start_job_immediately(request.job_id):
        raise HTTPException(status_code=400, detail=f"Failed to start job {request.job_id}")
    return {"status": "started_immediately", "job_id": request.job_id}


@router.post("/queue/cancel-and-remove")
async def cancel_and_remove_json_queue_job(request: JsonQueueJobRequest):
    service = await get_json_video_queue_service()
    stopped = await service.stop_job(request.job_id)
    removed = await service.remove_job(request.job_id)
    if not (stopped or removed):
        raise HTTPException(status_code=400, detail=f"Failed to cancel job {request.job_id}")
    return {"status": "cancelled_and_removed", "job_id": request.job_id}


@router.post("/queue/reprocess")
async def reprocess_json_queue_job(request: JsonQueueReprocessRequest):
    service = await get_json_video_queue_service()
    new_job_id = await service.reprocess_job(request.job_id, front=request.start_immediately)
    if not new_job_id:
        raise HTTPException(status_code=400, detail=f"Failed to reprocess job {request.job_id}")
    return {"status": "reprocess_created", "original_job_id": request.job_id, "new_job_id": new_job_id}


@router.post("/queue/resume-and-replace")
async def resume_and_replace_json_queue_job(request: JsonQueueJobRequest):
    service = await get_json_video_queue_service()
    if not await service.start_job_immediately(request.job_id):
        raise HTTPException(status_code=400, detail=f"Failed to resume job {request.job_id}")
    return {"status": "resumed_and_replaced", "job_id": request.job_id}


@router.get("/jobs")
async def list_json_jobs(include_metadata: bool = Query(False)):
    root = _json_root()
    if not root.exists():
        return {"jobs": [], "json_root": str(root)}

    index_path = _index_path()
    indexed_jobs: dict[str, Any] = {}
    if index_path.exists():
        index_data = _read_json(index_path)
        if isinstance(index_data, dict):
            raw_jobs = index_data.get("jobs", [])
            if isinstance(raw_jobs, list):
                indexed_jobs = {
                    str(job.get("id")): job
                    for job in raw_jobs
                    if isinstance(job, dict) and job.get("id")
                }

    jobs = []
    for child in sorted(root.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True):
        if not child.is_dir():
            continue
        files = _job_files(child)
        if not any(info["exists"] for info in files.values()):
            continue

        job = {
            "id": child.name,
            "path": str(child),
            "updated_at": child.stat().st_mtime,
            "files": files,
            "index": indexed_jobs.get(child.name),
        }
        if include_metadata:
            job["metadata"] = _read_optional_metadata(child)
        jobs.append(job)

    return {
        "storage_mode": get_storage_mode(),
        "json_root": str(root),
        "jobs": jobs,
    }


@router.post("/jobs")
async def upsert_json_job(body: JsonJobUpsert):
    root = _json_root()
    output_dir = body.output_dir or body.id
    job_path = _safe_path(root, output_dir)
    job_path.mkdir(parents=True, exist_ok=True)

    index = _load_index()
    jobs = index["jobs"]
    new_record = body.model_dump()
    new_record["output_dir"] = output_dir
    new_record["path"] = str(job_path)

    for idx, job in enumerate(jobs):
        if isinstance(job, dict) and job.get("id") == body.id:
            jobs[idx] = {**job, **new_record}
            break
    else:
        jobs.append(new_record)

    _save_index(index)
    return {"status": "saved", "job": new_record}


@router.get("/jobs/{job_id}")
async def get_json_job(job_id: str, include_metadata: bool = Query(True)):
    path = _job_dir(job_id)
    payload: dict[str, Any] = {
        "id": job_id,
        "path": str(path),
        "updated_at": path.stat().st_mtime,
        "files": _job_files(path),
    }
    if include_metadata:
        payload["metadata"] = _read_optional_metadata(path)
    return payload


@router.patch("/jobs/{job_id}")
async def patch_json_job(job_id: str, body: JsonJobPatch):
    index = _load_index()
    updates = body.model_dump(exclude_none=True)

    for idx, job in enumerate(index["jobs"]):
        if isinstance(job, dict) and job.get("id") == job_id:
            merged = {**job, **updates}
            if body.metadata is not None:
                base_metadata = job.get("metadata", {})
                if not isinstance(base_metadata, dict):
                    base_metadata = {}
                merged["metadata"] = {**base_metadata, **body.metadata}
            index["jobs"][idx] = merged
            _save_index(index)
            return {"status": "saved", "job": merged}

    raise HTTPException(status_code=404, detail=f"JSON job index record not found: {job_id}")


@router.get("/jobs/{job_id}/results")
async def get_json_results(
    job_id: str,
    frame_start: int | None = Query(None),
    frame_end: int | None = Query(None),
    limit: int | None = Query(500, ge=1, le=5000),
):
    data = _read_json(_job_dir(job_id) / "prediction_results.json")
    if not isinstance(data, dict):
        raise HTTPException(status_code=500, detail="prediction_results.json must be an object")

    frames = data.get("frames", [])
    if not isinstance(frames, list):
        frames = []

    if frame_start is not None:
        frames = [f for f in frames if isinstance(f, dict) and f.get("frame", -1) >= frame_start]
    if frame_end is not None:
        frames = [f for f in frames if isinstance(f, dict) and f.get("frame", -1) <= frame_end]

    total_frames = len(frames)
    if limit is not None:
        frames = frames[:limit]

    return {
        "metadata": data.get("metadata", {}),
        "total_matching_frames": total_frames,
        "returned_frames": len(frames),
        "frames": frames,
    }


@router.get("/jobs/{job_id}/reid-summary")
async def get_json_reid_summary(job_id: str):
    return _read_json(_job_dir(job_id) / "viewer_reid_summary.json")


@router.get("/jobs/{job_id}/timing")
async def get_json_timing(job_id: str):
    return _read_json(_job_dir(job_id) / "timing_summary.json")


@router.get("/jobs/{job_id}/summary", response_class=PlainTextResponse)
async def get_json_summary(job_id: str):
    summary_path = _job_dir(job_id) / "summary.md"
    if not summary_path.exists():
        raise HTTPException(status_code=404, detail="summary.md not found")
    return summary_path.read_text(encoding="utf-8")


@router.get("/jobs/{job_id}/files/{file_path:path}")
async def get_json_job_file(job_id: str, file_path: str):
    job_path = _job_dir(job_id)
    path = _safe_path(job_path, file_path)
    if not path.exists() or not path.is_file():
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(path)
