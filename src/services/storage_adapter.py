from __future__ import annotations

import json
import time
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

from src.config_loader import (
    get_json_storage_index,
    get_json_storage_root,
    get_storage_mode,
)


class StorageAdapter(ABC):
    """Small persistence boundary for job-oriented processing state."""

    @abstractmethod
    def register_job(
        self,
        job_id: str,
        *,
        label: str | None = None,
        source: str | None = None,
        status: str = "pending",
        output_dir: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def update_job(
        self,
        job_id: str,
        *,
        status: str | None = None,
        metadata: dict[str, Any] | None = None,
        **updates: Any,
    ) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def save_detection_batch(self, job_id: str, frames: list[dict[str, Any]]) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def finalize_job(
        self,
        job_id: str,
        *,
        status: str = "completed",
        metadata: dict[str, Any] | None = None,
        error_message: str | None = None,
    ) -> dict[str, Any]:
        raise NotImplementedError


class JsonStorageAdapter(StorageAdapter):
    def __init__(self, root: str | Path | None = None, index_path: str | Path | None = None) -> None:
        self.root = Path(root or get_json_storage_root()).resolve()
        index = Path(index_path or get_json_storage_index())
        self.index_path = (index if index.is_absolute() else Path.cwd() / index).resolve()

    def register_job(
        self,
        job_id: str,
        *,
        label: str | None = None,
        source: str | None = None,
        status: str = "pending",
        output_dir: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        output_dir = output_dir or job_id
        job_path = self._safe_path(self.root, output_dir)
        job_path.mkdir(parents=True, exist_ok=True)

        record = {
            "id": job_id,
            "label": label,
            "source": source,
            "status": status,
            "output_dir": output_dir,
            "path": str(job_path),
            "metadata": metadata or {},
            "created_at": time.time(),
            "updated_at": time.time(),
        }
        index = self._load_index()
        jobs = index["jobs"]
        for idx, existing in enumerate(jobs):
            if isinstance(existing, dict) and existing.get("id") == job_id:
                merged_metadata = {
                    **(existing.get("metadata") if isinstance(existing.get("metadata"), dict) else {}),
                    **record["metadata"],
                }
                record = {**existing, **record, "metadata": merged_metadata}
                jobs[idx] = record
                break
        else:
            jobs.append(record)
        self._save_index(index)
        return record

    def update_job(
        self,
        job_id: str,
        *,
        status: str | None = None,
        metadata: dict[str, Any] | None = None,
        **updates: Any,
    ) -> dict[str, Any]:
        index = self._load_index()
        for idx, existing in enumerate(index["jobs"]):
            if not isinstance(existing, dict) or existing.get("id") != job_id:
                continue
            merged = {**existing, **{k: v for k, v in updates.items() if v is not None}}
            if status is not None:
                merged["status"] = status
            if metadata:
                base_metadata = existing.get("metadata") if isinstance(existing.get("metadata"), dict) else {}
                merged["metadata"] = {**base_metadata, **metadata}
            merged["updated_at"] = time.time()
            index["jobs"][idx] = merged
            self._save_index(index)
            return merged
        return self.register_job(job_id, status=status or "pending", metadata=metadata or updates)

    def save_detection_batch(self, job_id: str, frames: list[dict[str, Any]]) -> dict[str, Any]:
        batch_path = self._job_path(job_id) / "detection_batches.jsonl"
        batch_path.parent.mkdir(parents=True, exist_ok=True)
        with batch_path.open("a", encoding="utf-8") as handle:
            for frame in frames:
                handle.write(json.dumps(frame, ensure_ascii=False) + "\n")
        return self.update_job(job_id, metadata={"frames_saved_to_batches": len(frames)})

    def finalize_job(
        self,
        job_id: str,
        *,
        status: str = "completed",
        metadata: dict[str, Any] | None = None,
        error_message: str | None = None,
    ) -> dict[str, Any]:
        final_metadata = dict(metadata or {})
        if error_message:
            final_metadata["error_message"] = error_message
        return self.update_job(job_id, status=status, metadata=final_metadata)

    def _job_path(self, job_id: str) -> Path:
        record = self.get_job(job_id)
        output_dir = record.get("output_dir") if record else job_id
        return self._safe_path(self.root, str(output_dir))

    def get_job(self, job_id: str) -> dict[str, Any] | None:
        for job in self._load_index()["jobs"]:
            if isinstance(job, dict) and job.get("id") == job_id:
                return job
        return None

    def list_jobs(self) -> list[dict[str, Any]]:
        return [job for job in self._load_index()["jobs"] if isinstance(job, dict)]

    def _load_index(self) -> dict[str, Any]:
        if not self.index_path.exists():
            return {"jobs": []}
        try:
            data = json.loads(self.index_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            data = {}
        if not isinstance(data, dict):
            data = {}
        if not isinstance(data.get("jobs"), list):
            data["jobs"] = []
        return data

    def _save_index(self, index: dict[str, Any]) -> None:
        self.index_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = self.index_path.with_suffix(self.index_path.suffix + ".tmp")
        tmp_path.write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp_path.replace(self.index_path)

    @staticmethod
    def _safe_path(root: Path, *parts: str) -> Path:
        path = root.joinpath(*parts).resolve()
        if path != root and root not in path.parents:
            raise ValueError(f"Path escapes JSON storage root: {path}")
        return path


class DbStorageAdapter(StorageAdapter):
    """Compatibility shim for the existing DB path.

    Queue and detection writes still live in the established DatabaseService
    flow; this adapter gives callers one factory point while DB migration stays
    incremental.
    """

    def register_job(self, job_id: str, **kwargs: Any) -> dict[str, Any]:
        return {"id": job_id, **kwargs}

    def update_job(self, job_id: str, **kwargs: Any) -> dict[str, Any]:
        return {"id": job_id, **kwargs}

    def save_detection_batch(self, job_id: str, frames: list[dict[str, Any]]) -> dict[str, Any]:
        return {"id": job_id, "frames": len(frames)}

    def finalize_job(self, job_id: str, **kwargs: Any) -> dict[str, Any]:
        return {"id": job_id, **kwargs}


def get_storage_adapter(mode: str | None = None) -> StorageAdapter:
    active_mode = (mode or get_storage_mode()).lower()
    if active_mode == "json":
        return JsonStorageAdapter()
    if active_mode == "db":
        return DbStorageAdapter()
    raise ValueError(f"Unsupported storage mode: {active_mode}")
