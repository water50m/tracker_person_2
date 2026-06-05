import os
import time
import asyncio
from contextlib import asynccontextmanager
from pathlib import Path
from typing import TYPE_CHECKING, List

WORKSPACE = Path(__file__).resolve().parents[2]
os.environ.setdefault("YOLO_CONFIG_DIR", str(WORKSPACE / ".ultralytics"))
os.environ.setdefault("MPLCONFIGDIR", str(WORKSPACE / ".matplotlib"))

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi import UploadFile, File, Form
from fastapi.responses import StreamingResponse
from src.api.schemas import (
    DetectionResponse, SearchCriteria, PersonTimeline,
    DailyStats, ClothingStats, AdvancedSearchRequest
)
from fastapi.middleware.cors import CORSMiddleware

if TYPE_CHECKING:
    from src.api.controllers import DetectionController

from src.api.video_controller import router as video_router
from src.api.routes.realtime import router as realtime_router
from src.api.routes.camera_relationships import router as camera_relationships_router
from src.api.routes.cameras_api import router as cameras_api_router
from src.api.routes.relationships_api import router as relationships_api_router
from src.api.routes.settings_api import router as settings_api_router
from src.api.routes.log_manager import router as log_manager_router
from src.api.routes.dashboard_api import router as dashboard_api_router
from src.api.routes.video_queue import router as video_queue_router
from src.api.routes.json_controller import router as json_controller_router
from src.api.routes.test_api import router as test_api_router
from src.config_loader import get_storage_mode
from src.services.json_investigation_service import JsonInvestigationService
from src.services.database import DatabaseService


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Run startup tasks then yield for normal operations."""
    # ── Startup: revert any videos stuck in 'processing' to 'paused' ──────────
    # This handles abrupt server restarts / crashes where the finally block
    # in background_processor.py never had a chance to run.
    if get_storage_mode() == "db":
        try:
            db = DatabaseService()
            if db.conn is not None:
                with db.conn.cursor() as cur:
                    cur.execute(
                        "UPDATE processed_videos SET status = 'paused' "
                        "WHERE status = 'processing'"
                    )
                    count = cur.rowcount
                db.conn.commit()
                if count > 0:
                    print(f"⚠️ [Startup] Marked {count} interrupted video(s) as 'paused' (server was likely restarted mid-process).")
        except Exception as e:
            print(f"⚠️ [Startup] Could not clean up stuck videos: {e}")
    else:
        print("ℹ️ [Startup] JSON storage mode active; skipped database startup cleanup.")

    # ── Start camera health monitor (TCP reachability every 10 min) ───────────
    from src.services import camera_health
    health_stop = asyncio.Event()
    health_task = asyncio.create_task(camera_health.monitor_loop(health_stop))

    yield  # Application runs here

    # ── Shutdown: stop camera health monitor ──────────────────────────────────
    health_stop.set()
    health_task.cancel()
    try:
        await health_task
    except (asyncio.CancelledError, Exception):
        pass

    # ── Shutdown: stop all active live-prediction streams ─────────────────────
    try:
        from src.api.video_controller import _ACTIVE_STREAMS
        if _ACTIVE_STREAMS:
            print(f"[Shutdown] Stopping {len(_ACTIVE_STREAMS)} active stream(s)…")
            for event in list(_ACTIVE_STREAMS.values()):
                try:
                    event.set()
                except Exception:
                    pass
    except Exception as e:
        print(f"[Shutdown] Error stopping streams: {e}")

    # Unblock any MJPEG relay coroutines waiting on frame queues
    try:
        from src.api.routes.dashboard_api import _FRAME_QUEUES
        for q in list(_FRAME_QUEUES.values()):
            try:
                q.put_nowait(b"")  # sentinel to unblock awaiting relays
            except Exception:
                pass
    except Exception:
        pass


app = FastAPI(title="CCTV AI Analytics System", lifespan=lifespan)


@app.middleware("http")
async def log_api_duration(request: Request, call_next):
    start = time.perf_counter()
    response = None
    try:
        response = await call_next(request)
        return response
    finally:
        duration_ms = (time.perf_counter() - start) * 1000
        status_code = response.status_code if response is not None else 500
        if request.url.path.startswith("/api"):
            print(
                f"[API-TIME] {request.method} {request.url.path} "
                f"status={status_code} duration={duration_ms:.1f}ms",
                flush=True,
            )
        if response is not None:
            response.headers["X-Process-Time-Ms"] = f"{duration_ms:.1f}"


class LazyDetectionController:
    """Delay database-backed controller creation until a DB endpoint is used."""

    def __init__(self):
        self._controller: "DetectionController | None" = None

    def _get(self) -> "DetectionController":
        if self._controller is None:
            from src.api.controllers import DetectionController

            self._controller = DetectionController()
        return self._controller

    def __getattr__(self, name: str):
        return getattr(self._get(), name)


# Setup CORS (ให้ Next.js เรียกได้)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# 1. ลงทะเบียน Router สำหรับรับ Video
app.include_router(video_router, prefix="/api/video", tags=["Video Input"])

# 2. ลงทะเบียน Router สำหรับ Real-time Events
app.include_router(realtime_router, tags=["Real-time Events"])

# 3. ลงทะเบียน Router สำหรับ Camera Relationships
app.include_router(camera_relationships_router, prefix="/api", tags=["Camera Relationships"])

# 4. ลงทะเบียน Router สำหรับ Camera Management
app.include_router(cameras_api_router, prefix="/api", tags=["Camera Management"])

# 5. ลงทะเบียน Router สำหรับ Camera Relationships Management
app.include_router(relationships_api_router, prefix="/api", tags=["Relationships Management"])

# 6. ลงทะเบียน Router สำหรับ System Settings
app.include_router(settings_api_router, prefix="/api", tags=["System Settings"])

# 7. ลงทะเบียน Router สำหรับ Log Manager
app.include_router(log_manager_router, prefix="/api/logs", tags=["Log Manager"])

# 7. Dashboard API (MJPEG relay, cameras, latest-detections)
app.include_router(dashboard_api_router, prefix="/api/dashboard", tags=["Dashboard"])

# 8. Video Queue API (Multi-video processing with queue management)
app.include_router(video_queue_router, tags=["Video Queue"])

# 9. JSON Storage API (file-backed result mode)
app.include_router(json_controller_router)

# 10. Test / Debug API
app.include_router(test_api_router, tags=["Test"])

# 2. ลงทะเบียน Router เดิม (Search, Stats, etc.)
# (สมมติว่าคุณแยก route ของ detection ไว้ในไฟล์อื่นก็ include มาแบบเดียวกัน)
# แต่ถ้าเขียนรวมใน main ก็เขียนต่อได้เลย เช่น:
controller = LazyDetectionController()


def _json_mode_empty_search(page: int = 1):
    return {"results": [], "total": 0, "page": page, "has_more": False, "storage_mode": "json"}


def _json_investigation() -> JsonInvestigationService:
    return JsonInvestigationService()


# --- กลุ่มข้อมูลดิบ (Data List) ---
@app.get("/api/detections", response_model=List[DetectionResponse])
async def list_detections(limit: int = 20, offset: int = 0):
    if get_storage_mode() == "json":
        return []
    return controller.get_all(limit, offset)

@app.post("/api/search", response_model=List[DetectionResponse])
async def search(criteria: SearchCriteria):
    if get_storage_mode() == "json":
        return []
    return controller.search(criteria)

@app.get("/api/search/persons")
async def search_persons(
    logic: str = Query("OR"),
    threshold: float = Query(0.7),
    camera_id: str | None = Query(None),
    video_id: str | None = Query(None),
    start_time: str | None = Query(None),
    end_time: str | None = Query(None),
    page: int = Query(1, ge=1),
    limit: int = Query(24, ge=1, le=100),
    clothing: list[str] = Query(default=[], alias="clothing[]"),
    colors: list[str] = Query(default=[], alias="colors[]"),
    brightness: str | None = Query(None),
    temperature: str | None = Query(None),
    vibrancy: str | None = Query(None),
):
    if get_storage_mode() == "json":
        return _json_investigation().search_persons(
            logic=logic,
            threshold=threshold,
            camera_id=camera_id,
            video_id=video_id,
            start_time=start_time,
            end_time=end_time,
            page=page,
            limit=limit,
            clothing=clothing,
            colors=colors,
            brightness=brightness,
            temperature=temperature,
            vibrancy=vibrancy,
        )

    try:
        return controller.search_persons(
            logic=logic,
            threshold=threshold,
            camera_id=camera_id,
            video_id=video_id,
            start_time=start_time,
            end_time=end_time,
            page=page,
            limit=limit,
            clothing=clothing,
            colors=colors,
            brightness=brightness,
            temperature=temperature,
            vibrancy=vibrancy,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))

# --- กลุ่มติดตามรายคน (Tracking) ---
@app.get("/api/person/{track_id}", response_model=PersonTimeline)
async def person_detail(track_id: int):
    if get_storage_mode() == "json":
        try:
            return _json_investigation().trace_person(person_id=person_id)
        except LookupError as e:
            raise HTTPException(status_code=404, detail=str(e))

    result = controller.get_person_timeline(track_id)
    if not result.history:
        raise HTTPException(status_code=404, detail="Track ID not found")
    return result

@app.get("/api/persons/{person_id}/trace")
async def trace_person(person_id: str):
    if get_storage_mode() == "json":
        try:
            return _json_investigation().trace_person(person_id=person_id)
        except LookupError as e:
            raise HTTPException(status_code=404, detail=str(e))

    try:
        return controller.trace_person(person_id=person_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/persons/{person_id}")
async def get_person_by_id(person_id: str):
    """Get person by UUID person_id"""
    if get_storage_mode() == "json":
        try:
            return _json_investigation().trace_person(person_id=person_id)
        except LookupError as e:
            raise HTTPException(status_code=404, detail=str(e))

    try:
        return controller.trace_person(person_id=person_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/detections/{detection_id}")
async def get_detection_detail(detection_id: str):
    """Get all details of a specific detection by ID"""
    if get_storage_mode() == "json":
        try:
            return _json_investigation().get_detection_detail(detection_id)
        except LookupError as e:
            raise HTTPException(status_code=404, detail=str(e))

    try:
        return controller.get_detection_detail(detection_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))

# --- กลุ่มสถิติ (Analytics) ---
@app.get("/api/stats/hourly", response_model=List[DailyStats])
async def hourly_metrics():
    if get_storage_mode() == "json":
        return []
    return controller.get_hourly_stats()

@app.get("/api/stats/clothing", response_model=List[ClothingStats])
async def clothing_metrics():
    if get_storage_mode() == "json":
        return []
    return controller.get_clothing_distribution()

@app.get("/api/stats/unique-persons")
async def unique_persons_metrics():
    if get_storage_mode() == "json":
        return {"count": 0, "storage_mode": "json"}
    return {"count": controller.get_unique_persons_today()}

# --- การจัดการข้อมูล ---
@app.delete("/api/detections/{id}")
async def remove_record(id: str):
    if get_storage_mode() == "json":
        raise HTTPException(status_code=409, detail="Detection database is disabled in JSON storage mode")

    controller.delete_detection(id)
    return {"status": "deleted", "id": id}


@app.post("/api/search/detect-attributes")
async def detect_attributes_from_image(file: UploadFile = File(...)):
    """
    API สำหรับรับรูปแล้วบอกว่า 'นี่คือชุดอะไร สีอะไร'
    เพื่อให้ Frontend เอาไป Auto-fill ในช่องค้นหา
    """
    start_time = time.time()
    file_size_kb = 0
    file_type = "unknown"

    try:
        # Read file and get metadata
        image_bytes = await file.read()
        file_size_kb = len(image_bytes) / 1024
        file_type = file.content_type or "unknown"

        print(f"[API] /api/search/detect-attributes called, file: {file_size_kb:.1f}KB, type: {file_type}")

        # Process image
        result = controller.analyze_image_for_search(image_bytes)

        # Log response summary
        elapsed_ms = (time.time() - start_time) * 1000
        status = result.get("status", "unknown")
        detected_class = result.get("detected_attributes", {}).get("class_name", "N/A")
        detected_color = result.get("detected_attributes", {}).get("color_name", "N/A")
        all_items_count = len(result.get("all_items", []))

        print(f"[API] Response sent to frontend - status: {status}, class: {detected_class}, color: {detected_color}, items: {all_items_count}, time: {elapsed_ms:.1f}ms")

        return result

    except Exception as e:
        elapsed_ms = (time.time() - start_time) * 1000
        print(f"[API] Error processing image: {e}, time: {elapsed_ms:.1f}ms")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/search/advanced")
async def search_advanced(
    request: AdvancedSearchRequest,
    page: int = Query(1, ge=1),
    limit: int = Query(24, ge=1, le=100),
):
    """
    Advanced search with clothing-specific color selection.

    Each clothing type can have its own color set and OR/AND logic.
    Global OR/AND controls relationship between clothing items.

    Example:
    {
        "clothing_groups": [
            {"clothing": "Long_sleeve", "colors": ["red", "dark_red"], "color_logic": "OR"},
            {"clothing": "Trousers", "colors": ["blue", "navy"], "color_logic": "AND"}
        ],
        "global_logic": "OR",
        "threshold": 0.1
    }
    """
    if get_storage_mode() == "json":
        return _json_investigation().search_advanced(
            clothing_groups=[g.model_dump() for g in request.clothing_groups],
            global_logic=request.global_logic,
            threshold=request.threshold,
            camera_id=request.camera_id,
            video_id=request.video_id,
            start_time=request.start_time,
            end_time=request.end_time,
            page=page,
            limit=limit,
        )

    try:
        result = controller.search_advanced(
            clothing_groups=[g.model_dump() for g in request.clothing_groups],
            global_logic=request.global_logic,
            threshold=request.threshold,
            camera_id=request.camera_id,
            video_id=request.video_id,
            start_time=request.start_time,
            end_time=request.end_time,
            page=page,
            limit=limit,
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/video")
async def video_stream():
    """
    Simple MJPEG video stream endpoint for camera 11 (YouTube stream).
    Access via: http://[ip]:8002/video
    """
    from src.services.stream_manager import stream_manager
    from src.api.video_controller import _ACTIVE_STREAMS
    import asyncio
    import time
    
    camera_id = "11"
    
    async def generate_mjpeg():
        """Generate MJPEG stream from stream manager"""
        while camera_id in _ACTIVE_STREAMS:
            frame_bytes = stream_manager.get_frame(camera_id)
            if frame_bytes:
                yield (
                    b"--frame\r\n"
                    b"Content-Type: image/jpeg\r\n\r\n"
                    + frame_bytes
                    + b"\r\n"
                )
            else:
                # No frame available, wait briefly
                await asyncio.sleep(0.033)  # ~30fps
                continue
            
            await asyncio.sleep(0.033)  # ~30fps
        
        # Stream ended
        yield (
            b"--frame\r\n"
            b"Content-Type: text/plain\r\n\r\n"
            b"Stream ended"
            + b"\r\n"
        )
    
    return StreamingResponse(
        generate_mjpeg(),
        media_type="multipart/x-mixed-replace; boundary=frame",
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate, max-age=0",
            "Pragma": "no-cache",
            "Expires": "0",
            "Connection": "close",
        }
    )
