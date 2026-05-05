import os

# Configure FFmpeg before OpenCV opens streams.
os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = (
    "http_persistent;0|reconnect;1|reconnect_at_eof;1|reconnect_streamed;1|"
    "reconnect_delay_max;5|timeout;10000000|rw_timeout;10000000"
)

import asyncio
import time
import uuid


# Background processing state tracking
_BACKGROUND_PROCESSING_STATE: dict[str, dict] = {}


def _get_background_state(task_id: str) -> dict:
    """Get or create background processing state for a task."""
    if task_id not in _BACKGROUND_PROCESSING_STATE:
        _BACKGROUND_PROCESSING_STATE[task_id] = {
            "status": "starting",
            "frames_processed": 0,
            "total_frames": 0,
            "fps": 0.0,
            "start_time": None,
            "detections_count": 0,
            "error": None,
        }
    return _BACKGROUND_PROCESSING_STATE[task_id]


def _update_background_state(task_id: str, **updates) -> None:
    """Update background processing state."""
    state = _get_background_state(task_id)
    state.update(updates)


def _cleanup_background_state(task_id: str) -> None:
    """Clean up background processing state."""
    _BACKGROUND_PROCESSING_STATE.pop(task_id, None)


def get_background_task_status(task_id: str) -> dict | None:
    """Get the status of a background processing task."""
    return _BACKGROUND_PROCESSING_STATE.get(task_id)


async def process_video_background_task(
    video_path: str,
    camera_id: str | None = None,
    frame_skip: int = 5,
    save_to_db: bool = True,
    task_id: str | None = None,
    save_images: bool = True,
    save_bbox_images: bool = True,
    stop_event: asyncio.Event | None = None,
) -> dict:
    """
    Process video in background without display output.

    This is a thin orchestration wrapper around the refactored pipeline:
        VideoProcessor -> ThreadPoolProcessor -> FrameProcessor

    save_bbox_images is kept for API compatibility. Background mode does not
    render or stream annotated video output.
    """
    if task_id is None:
        task_id = f"bg_{uuid.uuid4().hex[:8]}"

    start_time = time.time()
    _update_background_state(
        task_id,
        status="processing",
        start_time=start_time,
        frames_processed=0,
        total_frames=0,
        detections_count=0,
        fps=0.0,
        error=None,
    )

    print(f"[BACKGROUND] Starting background processing: {video_path}")
    print(f"   Task ID: {task_id}")
    print(f"   Camera ID: {camera_id or 'auto-generated'}")
    print(f"   Frame skip: {frame_skip}")
    print(f"   Save to DB: {save_to_db}, save_images={save_images}, save_bbox_images={save_bbox_images}")

    db = None
    video_id = None
    effective_camera_id = camera_id or f"bg_{int(time.time())}"
    total_frames = 0
    fps = 0.0
    detections_count = 0
    frames_processed = 0

    try:
        import cv2

        cap_info = cv2.VideoCapture(video_path)
        if not cap_info.isOpened():
            raise ValueError(f"Cannot open video: {video_path}")

        width = int(cap_info.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap_info.get(cv2.CAP_PROP_FRAME_HEIGHT))
        total_frames = int(cap_info.get(cv2.CAP_PROP_FRAME_COUNT))
        fps = cap_info.get(cv2.CAP_PROP_FPS) or 30.0
        cap_info.release()

        _update_background_state(task_id, total_frames=total_frames, fps=fps)

        if save_to_db:
            try:
                from src.services.database import DatabaseService

                db = DatabaseService()
                if camera_id:
                    effective_camera_id = str(db.resolve_camera_id(camera_id))

                video_id = db.register_video(
                    camera_id=effective_camera_id,
                    label=f"Background {task_id}",
                    filename=os.path.basename(video_path),
                    file_path=video_path,
                    width=width,
                    height=height,
                )
                _update_background_state(task_id, video_id=str(video_id) if video_id else None)
                print(f"[BACKGROUND] Database saving enabled - Video ID: {video_id}")
            except Exception as e:
                print(f"[BACKGROUND] Database setup failed, continuing without DB save: {e}")
                save_to_db = False
                db = None
                video_id = None

        try:
            from src.services.thread_pool_processor import ThreadPoolProcessor
            from src.services.video_processor import VideoProcessor
        except ImportError:
            from services.thread_pool_processor import ThreadPoolProcessor
            from services.video_processor import VideoProcessor

        def on_progress(percentage: int, current_frame: int, current_total: int) -> None:
            _update_background_state(
                task_id,
                frames_processed=current_frame,
                total_frames=current_total,
            )
            print(f"[BACKGROUND] Progress: {current_frame}/{current_total} frames ({percentage}%)")

        def on_detection(_person, frame_number: int) -> None:
            nonlocal detections_count, frames_processed
            detections_count += 1
            frames_processed = max(frames_processed, frame_number)
            _update_background_state(
                task_id,
                frames_processed=frames_processed,
                detections_count=detections_count,
            )

        pool = ThreadPoolProcessor(max_workers=4)
        await pool.initialize()

        try:
            processor = VideoProcessor(
                thread_pool=pool,
                frame_skip=frame_skip,
                save_to_db=save_to_db,
                save_images=save_images,
                use_reader_thread=False,
            )

            stats = await processor.process_video(
                source=video_path,
                camera_id=effective_camera_id,
                video_id=str(video_id) if video_id else None,
                on_progress=on_progress,
                on_detection=on_detection,
                stop_event=stop_event,
                save_to_db=save_to_db,
                save_images=save_images,
                frame_skip=frame_skip,
            )
        finally:
            await pool.shutdown()

        status_value = getattr(stats.status, "value", str(stats.status)).lower()
        if "stopped" in status_value:
            current_status = "stopped"
        elif "error" in status_value or stats.error_message:
            current_status = "failed"
        else:
            current_status = "completed"

        if current_status == "completed" and (stats.total_frames or total_frames):
            frames_processed = stats.total_frames or total_frames
        else:
            frames_processed = max(frames_processed, stats.processed_frames)
        detections_count = max(detections_count, stats.num_persons_detected)
        elapsed_time = time.time() - start_time

        _update_background_state(
            task_id,
            status=current_status,
            frames_processed=frames_processed,
            total_frames=stats.total_frames or total_frames,
            detections_count=detections_count,
            fps=stats.fps or fps,
            elapsed_time=elapsed_time,
            error=stats.error_message,
        )

        if current_status == "completed":
            print(
                f"[BACKGROUND] Analysis completed: {frames_processed} frames, "
                f"{detections_count} detections in {elapsed_time:.1f}s"
            )
        elif current_status == "stopped":
            print(
                f"[BACKGROUND] Analysis stopped: {frames_processed} frames, "
                f"{detections_count} detections in {elapsed_time:.1f}s"
            )
        else:
            print(f"[BACKGROUND] Analysis failed: {stats.error_message}")

        return {
            "status": current_status,
            "task_id": task_id,
            "frames_processed": frames_processed,
            "total_frames": stats.total_frames or total_frames,
            "detections_count": detections_count,
            "elapsed_time": elapsed_time,
            "video_id": str(video_id) if video_id else None,
            "error": stats.error_message,
        }

    except Exception as e:
        elapsed_time = time.time() - start_time
        error_msg = f"[BACKGROUND] Processing error: {e}"
        print(error_msg)
        _update_background_state(
            task_id,
            status="failed",
            error=error_msg,
            elapsed_time=elapsed_time,
            frames_processed=frames_processed,
            total_frames=total_frames,
            detections_count=detections_count,
        )
        if save_to_db and db and video_id:
            try:
                db.update_video_status(video_id, "failed")
            except Exception:
                pass
        return {
            "status": "failed",
            "error": error_msg,
            "task_id": task_id,
            "frames_processed": frames_processed,
            "total_frames": total_frames,
            "detections_count": detections_count,
            "elapsed_time": elapsed_time,
            "video_id": str(video_id) if video_id else None,
        }
