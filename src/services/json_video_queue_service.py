from __future__ import annotations

import asyncio
import json
import sys
import time
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from src.config_loader import get_json_storage_index, get_json_storage_root
from src.services.storage_adapter import JsonStorageAdapter


@dataclass
class JsonQueueJob:
    id: str
    source: str
    camera_id: str
    display_mode: str = "background"
    status: str = "pending"
    priority: int = 0
    created_at: float = 0.0
    started_at: float | None = None
    completed_at: float | None = None
    progress_pct: int = 0
    frames_processed: int = 0
    total_frames: int = 0
    detections_count: int = 0
    error_message: str | None = None
    original_filename: str | None = None
    width: int | None = None
    height: int | None = None
    fps: float | None = None
    duration_sec: float | None = None
    frame_skip: int = 2
    save_images: bool = False
    save_bbox_images: bool = False
    output_dir: str | None = None
    stdout_log: str | None = None
    stderr_log: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "JsonQueueJob":
        return cls(
            id=str(data["id"]),
            source=str(data["source"]),
            camera_id=str(data.get("camera_id") or "UNKNOWN"),
            display_mode=str(data.get("display_mode") or "background"),
            status=str(data.get("status") or "pending"),
            priority=int(data.get("priority") or 0),
            created_at=float(data.get("created_at") or time.time()),
            started_at=data.get("started_at"),
            completed_at=data.get("completed_at"),
            progress_pct=int(data.get("progress_pct") or 0),
            frames_processed=int(data.get("frames_processed") or 0),
            total_frames=int(data.get("total_frames") or 0),
            detections_count=int(data.get("detections_count") or 0),
            error_message=data.get("error_message"),
            original_filename=data.get("original_filename"),
            width=data.get("width"),
            height=data.get("height"),
            fps=data.get("fps"),
            duration_sec=data.get("duration_sec"),
            frame_skip=int(data.get("frame_skip") or 2),
            save_images=bool(data.get("save_images", False)),
            save_bbox_images=bool(data.get("save_bbox_images", False)),
            output_dir=data.get("output_dir"),
            stdout_log=data.get("stdout_log"),
            stderr_log=data.get("stderr_log"),
        )


class JsonVideoQueueService:
    def __init__(self) -> None:
        self.root = Path(get_json_storage_root()).resolve()
        self.queue_path = (self.root / "json_jobs" / "queue.json").resolve()
        self.adapter = JsonStorageAdapter(root=self.root, index_path=get_json_storage_index())
        self._jobs: dict[str, JsonQueueJob] = {}
        self._queue_order: list[str] = []
        self._current_job_id: str | None = None
        self._current_process: asyncio.subprocess.Process | None = None
        self._lock = asyncio.Lock()
        self._processing_task: asyncio.Task | None = None
        self._load()

    async def start_processing(self) -> None:
        if self._processing_task and not self._processing_task.done():
            return
        self._processing_task = asyncio.create_task(self._processing_loop())

    async def add_video(
        self,
        *,
        source: str,
        camera_id: str,
        display_mode: str = "background",
        priority: int = 0,
        original_filename: str | None = None,
        width: int | None = None,
        height: int | None = None,
        fps: float | None = None,
        duration_sec: float | None = None,
        frame_skip: int = 2,
        save_images: bool = False,
        save_bbox_images: bool = False,
    ) -> str:
        job_id = str(uuid.uuid4())
        job = JsonQueueJob(
            id=job_id,
            source=source,
            camera_id=camera_id,
            display_mode=display_mode,
            priority=priority,
            created_at=time.time(),
            original_filename=original_filename or Path(source).name,
            width=width,
            height=height,
            fps=fps,
            duration_sec=duration_sec,
            frame_skip=frame_skip,
            save_images=save_images,
            save_bbox_images=save_bbox_images,
            output_dir=job_id,
        )
        async with self._lock:
            self._jobs[job_id] = job
            self._insert_queue_order(job_id)
            self._save()
        self._sync_index(job)
        await self.start_processing()
        return job_id

    def get_global_status(self) -> dict[str, Any]:
        current_job = None
        queue: list[JsonQueueJob] = []
        paused: list[JsonQueueJob] = []
        completed: list[JsonQueueJob] = []
        failed: list[JsonQueueJob] = []
        stopped: list[JsonQueueJob] = []

        for job in self._jobs.values():
            if job.status == "processing":
                current_job = job
            elif job.status == "pending":
                queue.append(job)
            elif job.status == "paused":
                paused.append(job)
            elif job.status == "completed":
                completed.append(job)
            elif job.status == "failed":
                failed.append(job)
            elif job.status == "stopped":
                stopped.append(job)

        queue.sort(key=lambda j: (-j.priority, j.created_at))
        completed.sort(key=lambda j: j.completed_at or 0, reverse=True)
        failed.sort(key=lambda j: j.completed_at or 0, reverse=True)
        stopped.sort(key=lambda j: j.completed_at or 0, reverse=True)
        return {
            "current_job": current_job.to_dict() if current_job else None,
            "queue": [job.to_dict() for job in queue],
            "paused": [job.to_dict() for job in paused],
            "completed": [job.to_dict() for job in completed],
            "failed": [job.to_dict() for job in failed],
            "stopped": [job.to_dict() for job in stopped],
            "stats": {
                "total_jobs": len(self._jobs),
                "pending_count": len(queue),
                "processing_count": 1 if current_job else 0,
                "paused_count": len(paused),
                "completed_count": len(completed),
                "failed_count": len(failed),
                "stopped_count": len(stopped),
            },
        }

    async def pause_job(self, job_id: str) -> bool:
        async with self._lock:
            job = self._jobs.get(job_id)
            if not job or job.status not in {"pending", "processing"}:
                return False
            if job.status == "processing" and self._current_process is not None:
                self._current_process.terminate()
            job.status = "paused"
            job.completed_at = time.time()
            if job_id in self._queue_order:
                self._queue_order.remove(job_id)
            self._save()
        self._sync_index(job)
        return True

    async def resume_job(self, job_id: str, *, front: bool = False) -> bool:
        async with self._lock:
            job = self._jobs.get(job_id)
            if not job or job.status not in {"paused", "stopped", "failed", "completed"}:
                return False
            job.status = "pending"
            job.started_at = None
            job.completed_at = None
            job.error_message = None
            if front:
                job.priority = max(job.priority, 9999)
            if job_id in self._queue_order:
                self._queue_order.remove(job_id)
            self._insert_queue_order(job_id)
            self._save()
        self._sync_index(job)
        await self.start_processing()
        return True

    async def start_job_immediately(self, job_id: str) -> bool:
        async with self._lock:
            job = self._jobs.get(job_id)
            if not job or job.status not in {"pending", "paused", "stopped", "failed", "completed"}:
                return False
            if self._current_job_id and self._current_job_id != job_id:
                current = self._jobs.get(self._current_job_id)
                if current and current.status == "processing":
                    if self._current_process is not None:
                        self._current_process.terminate()
                    current.status = "paused"
                    current.completed_at = time.time()
                    if current.id not in self._queue_order:
                        self._queue_order.insert(0, current.id)
            job.status = "pending"
            job.started_at = None
            job.completed_at = None
            job.error_message = None
            job.priority = max(job.priority, 9999)
            if job_id in self._queue_order:
                self._queue_order.remove(job_id)
            self._queue_order.insert(0, job_id)
            self._save()
        self._sync_index(job)
        await self.start_processing()
        return True

    async def reprocess_job(self, job_id: str, *, front: bool = False) -> str | None:
        async with self._lock:
            old = self._jobs.get(job_id)
            if not old:
                return None
        return await self.add_video(
            source=old.source,
            camera_id=old.camera_id,
            display_mode=old.display_mode,
            priority=9999 if front else old.priority,
            original_filename=f"[RE] {old.original_filename or Path(old.source).name}",
            width=old.width,
            height=old.height,
            fps=old.fps,
            duration_sec=old.duration_sec,
            frame_skip=old.frame_skip,
            save_images=old.save_images,
            save_bbox_images=old.save_bbox_images,
        )

    async def stop_job(self, job_id: str) -> bool:
        async with self._lock:
            job = self._jobs.get(job_id)
            if not job or job.status not in {"pending", "processing", "paused"}:
                return False
            if job.status == "processing" and self._current_process is not None:
                self._current_process.terminate()
            job.status = "stopped"
            job.completed_at = time.time()
            if job_id in self._queue_order:
                self._queue_order.remove(job_id)
            self._save()
        self._sync_index(job)
        return True

    async def remove_job(self, job_id: str) -> bool:
        async with self._lock:
            job = self._jobs.get(job_id)
            if not job:
                return False
            if job.status == "processing" and self._current_process is not None:
                self._current_process.terminate()
            self._jobs.pop(job_id, None)
            if job_id in self._queue_order:
                self._queue_order.remove(job_id)
            self._save()
        return True

    async def clear_completed(self) -> int:
        async with self._lock:
            removable = [
                job_id
                for job_id, job in self._jobs.items()
                if job.status in {"completed", "failed", "stopped"}
            ]
            for job_id in removable:
                self._jobs.pop(job_id, None)
                if job_id in self._queue_order:
                    self._queue_order.remove(job_id)
            self._save()
        return len(removable)

    async def reorder_queue(self, job_id: str, new_position: int) -> bool:
        async with self._lock:
            job = self._jobs.get(job_id)
            if not job or job.status != "pending":
                return False
            if job_id in self._queue_order:
                self._queue_order.remove(job_id)
            position = max(0, min(new_position, len(self._queue_order)))
            self._queue_order.insert(position, job_id)
            for idx, queued_id in enumerate(self._queue_order):
                queued = self._jobs.get(queued_id)
                if queued and queued.status == "pending":
                    queued.priority = len(self._queue_order) - idx
            self._save()
        self._sync_index(job)
        return True

    async def _processing_loop(self) -> None:
        while True:
            async with self._lock:
                next_id = next(
                    (
                        job_id
                        for job_id in self._queue_order
                        if job_id in self._jobs and self._jobs[job_id].status == "pending"
                    ),
                    None,
                )
            if next_id is None:
                await asyncio.sleep(1.0)
                continue
            await self._process_job(next_id)

    async def _process_job(self, job_id: str) -> None:
        async with self._lock:
            job = self._jobs.get(job_id)
            if not job or job.status != "pending":
                return
            job.status = "processing"
            job.started_at = time.time()
            job.progress_pct = 0
            job.error_message = None
            self._current_job_id = job_id
            if job_id in self._queue_order:
                self._queue_order.remove(job_id)
            self._save()
        self._sync_index(job)

        logs_dir = self.root / "json_jobs" / "logs"
        logs_dir.mkdir(parents=True, exist_ok=True)
        job.stdout_log = str((logs_dir / f"{job_id}.stdout.log").resolve())
        job.stderr_log = str((logs_dir / f"{job_id}.stderr.log").resolve())
        script_path = Path.cwd() / "scripts" / "predict_video_full_pipeline.py"
        command = [
            sys.executable,
            str(script_path),
            "--video",
            job.source,
            "--output-dir",
            str(Path(get_json_storage_root()) / (job.output_dir or job.id)),
            "--job-id",
            job.id,
            "--json-index",
            str(Path(get_json_storage_index()).resolve()),
            "--json-only-output",
            "--camera-id",
            job.camera_id,
            "--db-video-label",
            job.original_filename or job.id,
            "--frame-stride",
            str(max(1, job.frame_skip)),
        ]
        if job.save_images:
            command.append("--save-local-images")

        stdout_handle = Path(job.stdout_log).open("w", encoding="utf-8")
        stderr_handle = Path(job.stderr_log).open("w", encoding="utf-8")
        try:
            process = await asyncio.create_subprocess_exec(
                *command,
                cwd=str(Path.cwd()),
                stdout=stdout_handle,
                stderr=stderr_handle,
            )
            self._current_process = process
            while process.returncode is None:
                await self._refresh_job_from_index(job)
                try:
                    await asyncio.wait_for(process.wait(), timeout=1.0)
                except asyncio.TimeoutError:
                    pass
            await self._refresh_job_from_index(job)
            if process.returncode == 0 and job.status not in {"stopped", "paused"}:
                job.status = "completed"
                job.progress_pct = 100
                job.completed_at = time.time()
            elif job.status not in {"stopped", "paused"}:
                job.status = "failed"
                job.error_message = f"Pipeline exited with code {process.returncode}"
                job.completed_at = time.time()
        except Exception as exc:
            job.status = "failed"
            job.error_message = str(exc)
            job.completed_at = time.time()
        finally:
            stdout_handle.close()
            stderr_handle.close()
            self._current_process = None
            self._current_job_id = None
            async with self._lock:
                self._jobs[job_id] = job
                self._save()
            self._sync_index(job)

    async def _refresh_job_from_index(self, job: JsonQueueJob) -> None:
        record = self.adapter.get_job(job.id)
        metadata = record.get("metadata", {}) if isinstance(record, dict) else {}
        if isinstance(metadata, dict):
            job.frames_processed = int(metadata.get("frames_processed") or job.frames_processed or 0)
            job.total_frames = int(metadata.get("total_frames") or job.total_frames or 0)
            job.detections_count = int(metadata.get("detections_count") or job.detections_count or 0)
            if job.total_frames:
                job.progress_pct = min(100, int(job.frames_processed * 100 / max(job.total_frames, 1)))
        if isinstance(record, dict) and record.get("status"):
            job.status = str(record["status"])
        async with self._lock:
            self._jobs[job.id] = job
            self._save()

    def _sync_index(self, job: JsonQueueJob) -> None:
        metadata = {
            "camera_id": job.camera_id,
            "priority": job.priority,
            "frames_processed": job.frames_processed,
            "total_frames": job.total_frames,
            "progress_pct": job.progress_pct,
            "detections_count": job.detections_count,
            "original_filename": job.original_filename,
            "width": job.width,
            "height": job.height,
            "fps": job.fps,
            "duration_sec": job.duration_sec,
            "stdout_log": job.stdout_log,
            "stderr_log": job.stderr_log,
            "error_message": job.error_message,
        }
        self.adapter.register_job(
            job.id,
            label=job.original_filename or job.id,
            source=job.source,
            status=job.status,
            output_dir=job.output_dir or job.id,
            metadata={key: value for key, value in metadata.items() if value is not None},
        )

    def _insert_queue_order(self, job_id: str) -> None:
        job = self._jobs[job_id]
        for idx, existing_id in enumerate(self._queue_order):
            existing = self._jobs.get(existing_id)
            if existing and job.priority > existing.priority:
                self._queue_order.insert(idx, job_id)
                return
        self._queue_order.append(job_id)

    def _load(self) -> None:
        if not self.queue_path.exists():
            return
        try:
            data = json.loads(self.queue_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return
        for raw in data.get("jobs", []):
            if not isinstance(raw, dict) or not raw.get("id"):
                continue
            job = JsonQueueJob.from_dict(raw)
            if job.status == "processing":
                job.status = "paused"
                job.error_message = "Server restarted while job was processing; resume reruns the JSON pipeline."
            self._jobs[job.id] = job
        self._queue_order = [
            str(job_id)
            for job_id in data.get("queue_order", [])
            if str(job_id) in self._jobs
        ]

    def _save(self) -> None:
        self.queue_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "jobs": [job.to_dict() for job in self._jobs.values()],
            "queue_order": self._queue_order,
            "updated_at": time.time(),
        }
        tmp_path = self.queue_path.with_suffix(self.queue_path.suffix + ".tmp")
        tmp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp_path.replace(self.queue_path)


_global_json_queue_service: JsonVideoQueueService | None = None
_global_lock = asyncio.Lock()


async def get_json_video_queue_service() -> JsonVideoQueueService:
    global _global_json_queue_service
    if _global_json_queue_service is None:
        async with _global_lock:
            if _global_json_queue_service is None:
                _global_json_queue_service = JsonVideoQueueService()
                await _global_json_queue_service.start_processing()
    return _global_json_queue_service
