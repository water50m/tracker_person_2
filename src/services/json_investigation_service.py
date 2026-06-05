from __future__ import annotations

import json
import shutil
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.config_loader import get_json_storage_index, get_json_storage_root


CLASS_MAP = {
    "long_sleeve": "Long_sleeve",
    "short_sleeve": "Short_sleeve",
    "trousers": "Trousers",
    "shorts": "Shorts",
    "skirt": "skirt",
    "dress": "Dress",
}


class JsonInvestigationService:
    def __init__(self) -> None:
        self.root = Path(get_json_storage_root()).resolve()
        index_path = Path(get_json_storage_index())
        self.index_path = (index_path if index_path.is_absolute() else Path.cwd() / index_path).resolve()

    def search_persons(
        self,
        *,
        logic: str = "OR",
        threshold: float = 0.1,
        camera_id: str | None = None,
        video_id: str | None = None,
        start_time: str | None = None,
        end_time: str | None = None,
        page: int = 1,
        limit: int = 24,
        clothing: list[str] | None = None,
        colors: list[str] | None = None,
        brightness: str | None = None,
        temperature: str | None = None,
        vibrancy: str | None = None,
    ) -> dict[str, Any]:
        records = list(self._iter_detection_records())
        filtered = [
            record
            for record in records
            if self._record_matches(
                record,
                logic=logic,
                threshold=threshold,
                camera_id=camera_id,
                video_id=video_id,
                start_time=start_time,
                end_time=end_time,
                clothing=clothing or [],
                colors=colors or [],
                brightness=brightness,
                temperature=temperature,
                vibrancy=vibrancy,
            )
        ]
        filtered.sort(key=lambda row: row.get("timestamp") or "", reverse=True)
        total = len(filtered)
        start = (page - 1) * limit
        end = start + limit
        return {
            "results": filtered[start:end],
            "total": total,
            "page": page,
            "has_more": end < total,
            "storage_mode": "json",
        }

    def search_advanced(
        self,
        *,
        clothing_groups: list[dict[str, Any]],
        global_logic: str = "OR",
        threshold: float = 0.1,
        camera_id: str | None = None,
        video_id: str | None = None,
        start_time: str | None = None,
        end_time: str | None = None,
        page: int = 1,
        limit: int = 24,
    ) -> dict[str, Any]:
        records = list(self._iter_detection_records())
        filtered = []
        for record in records:
            if not self._record_matches(
                record,
                logic="OR",
                threshold=threshold,
                camera_id=camera_id,
                video_id=video_id,
                start_time=start_time,
                end_time=end_time,
                clothing=[],
                colors=[],
            ):
                continue
            checks = []
            for group in clothing_groups:
                cls = str(group.get("clothing") or "").lower()
                color_logic = str(group.get("color_logic") or "OR").upper()
                wanted_colors = [str(c).lower() for c in group.get("colors") or []]
                matching_items = [
                    item
                    for item in record.get("items", [])
                    if str(item.get("class_name") or "").lower() == cls
                ]
                if not matching_items:
                    checks.append(False)
                    continue
                if not wanted_colors:
                    checks.append(True)
                    continue
                item_color_hits = []
                for item in matching_items:
                    item_colors = self._item_color_names(item)
                    if color_logic == "AND":
                        item_color_hits.append(all(color in item_colors for color in wanted_colors))
                    else:
                        item_color_hits.append(any(color in item_colors for color in wanted_colors))
                checks.append(any(item_color_hits))
            if not clothing_groups:
                matched = True
            elif global_logic.upper() == "AND":
                matched = all(checks)
            else:
                matched = any(checks)
            if matched:
                filtered.append(record)
        filtered.sort(key=lambda row: row.get("timestamp") or "", reverse=True)
        total = len(filtered)
        start = (page - 1) * limit
        end = start + limit
        return {
            "results": filtered[start:end],
            "total": total,
            "page": page,
            "has_more": end < total,
            "storage_mode": "json",
        }

    def trace_person(self, person_id: str) -> dict[str, Any]:
        target = self._parse_json_detection_id(person_id)
        if not target:
            raise LookupError("JSON person not found")
        job_id, _, track_id = target
        detections = [
            record
            for record in self._iter_detection_records(job_filter=job_id)
            if int(record.get("track_id") or -1) == track_id
        ]
        if not detections:
            raise LookupError("JSON person not found")
        detections.sort(key=lambda row: (row.get("video_time_offset") or 0, row.get("timestamp") or ""))
        events = []
        for record in detections:
            bbox = record.get("bbox")
            events.append(
                {
                    "id": record["id"],
                    "camera_id": record["camera_id"],
                    "camera_name": record.get("camera_name") or record["camera_id"],
                    "timestamp": record["timestamp"],
                    "thumbnail_url": record.get("thumbnail_url"),
                    "confidence": record.get("confidence", 0.0),
                    "clothing_class": record.get("clothing_class"),
                    "color": record.get("primary_color") or record.get("color"),
                    "color_profile": self._primary_color_profile(record),
                    "video_id": record.get("video_id"),
                    "video_time_offset": record.get("video_time_offset"),
                    "bounding_box": self._bbox_dict(bbox) if bbox else None,
                }
            )
        first = detections[0]
        return {
            "person_id": person_id,
            "thumbnail_url": first.get("thumbnail_url"),
            "detections": events,
            "cameras": sorted({event["camera_id"] for event in events}),
            "attributes": {
                "track_id": str(track_id),
                "job": job_id,
                "clothing": first.get("clothing_class", "Unknown"),
                "color": str(first.get("primary_color") or first.get("color") or "Unknown"),
            },
            "storage_mode": "json",
        }

    def get_detection_detail(self, detection_id: str) -> dict[str, Any]:
        target = self._parse_json_detection_id(detection_id)
        if not target:
            raise LookupError("JSON detection not found")
        job_id, frame_no, track_id = target
        for record in self._iter_detection_records(job_filter=job_id):
            if int(record.get("frame") or -1) == frame_no and int(record.get("track_id") or -1) == track_id:
                return {
                    **record,
                    "image_url": record.get("thumbnail_url"),
                    "class_name": record.get("clothing_class"),
                    "category": record.get("color"),
                    "bbox": record.get("bbox"),
                    "storage_mode": "json",
                }
        raise LookupError("JSON detection not found")

    def list_video_detections(self, *, limit: int = 500) -> list[dict[str, Any]]:
        return list(self._iter_detection_records())[:limit]

    def stats(self) -> dict[str, Any]:
        jobs = list(self._iter_job_dirs())
        detections = sum(1 for _ in self._iter_detection_records())
        cameras = {
            record.get("camera_id")
            for record in self._iter_detection_records()
            if record.get("camera_id")
        }
        return {
            "storage_mode": "json",
            "json_root": str(self.root),
            "jobs": len(jobs),
            "detections": detections,
            "cameras": len(cameras),
        }

    def clear(self, *, include_orphan_results: bool = True) -> dict[str, Any]:
        deleted_dirs: list[str] = []
        deleted_files: list[str] = []
        index = self._load_index()
        indexed_ids = {
            str(job.get("output_dir") or job.get("id"))
            for job in index.get("jobs", [])
            if isinstance(job, dict) and (job.get("id") or job.get("output_dir"))
        }

        candidates: set[Path] = set()
        for output_dir in indexed_ids:
            candidates.add(self._safe_path(self.root, output_dir))
        if include_orphan_results:
            for job_dir in self._iter_job_dirs(include_orphans=True):
                candidates.add(job_dir)

        for path in sorted(candidates, key=lambda p: len(p.parts), reverse=True):
            if not path.exists() or path == self.root:
                continue
            if not self._is_deletable_json_result_dir(path):
                continue
            shutil.rmtree(path)
            deleted_dirs.append(str(path))

        if self.index_path.exists():
            self._write_json(self.index_path, {"jobs": []})
            deleted_files.append(str(self.index_path))

        queue_path = self._safe_path(self.root, "json_jobs", "queue.json")
        if queue_path.exists():
            self._write_json(queue_path, {"jobs": [], "queue_order": [], "current_job_id": None})
            deleted_files.append(str(queue_path))

        logs_dir = self._safe_path(self.root, "json_jobs", "logs")
        if logs_dir.exists():
            for child in logs_dir.iterdir():
                if child.is_file() and child.suffix == ".log":
                    child.unlink()
                    deleted_files.append(str(child))

        return {
            "status": "cleared",
            "storage_mode": "json",
            "deleted_dirs": len(deleted_dirs),
            "deleted_files": len(deleted_files),
            "deleted_dir_paths": deleted_dirs,
        }

    def _iter_detection_records(self, job_filter: str | None = None):
        for job_dir in self._iter_job_dirs():
            job_id = job_dir.name
            if job_filter and job_id != job_filter:
                continue
            results_path = job_dir / "prediction_results.json"
            data = self._read_json_file(results_path)
            if not isinstance(data, dict):
                continue
            metadata = data.get("metadata") if isinstance(data.get("metadata"), dict) else {}
            frames = data.get("frames") if isinstance(data.get("frames"), list) else []
            base_ts = self._base_timestamp(job_dir, metadata)
            camera_id = str(metadata.get("camera_id") or metadata.get("db_camera_id") or "UNKNOWN")
            video_id = job_id
            for frame in frames:
                if not isinstance(frame, dict):
                    continue
                frame_no = int(frame.get("frame") or 0)
                frame_time = float(frame.get("time") or 0.0)
                timestamp = datetime.fromtimestamp(base_ts + frame_time, timezone.utc).isoformat()
                persons = frame.get("persons") if isinstance(frame.get("persons"), list) else []
                for person in persons:
                    if not isinstance(person, dict):
                        continue
                    track_id = int(person.get("id") or -1)
                    if track_id < 0:
                        continue
                    items = self._items_from_person(job_id, frame_no, track_id, person)
                    if not items:
                        continue
                    first_item = items[0]
                    image_url = self._image_url(job_dir, job_id, person, track_id, frame_no)
                    record = {
                        "id": self._detection_id(job_id, frame_no, track_id),
                        "track_id": track_id,
                        "frame": frame_no,
                        "thumbnail_url": image_url,
                        "camera_id": camera_id,
                        "camera_name": camera_id,
                        "timestamp": timestamp,
                        "clothing_class": first_item.get("class_name") or "Unknown",
                        "color": first_item.get("category") or "Unknown",
                        "confidence": float(person.get("confidence") or first_item.get("confidence") or 0.0),
                        "primary_color": first_item.get("colors", {}).get("primary_color") or "Unknown",
                        "video_id": video_id,
                        "video_time_offset": frame_time,
                        "items": items,
                        "all_top_colors": self._all_top_colors(items),
                        "bbox": person.get("bbox"),
                    }
                    yield record

    def _record_matches(self, record: dict[str, Any], **kwargs: Any) -> bool:
        camera_id = kwargs.get("camera_id")
        video_id = kwargs.get("video_id")
        start_time = kwargs.get("start_time")
        end_time = kwargs.get("end_time")
        if camera_id and str(record.get("camera_id")) != camera_id:
            return False
        if video_id and str(record.get("video_id")) != video_id:
            return False
        ts = str(record.get("timestamp") or "")
        if start_time and ts < start_time:
            return False
        if end_time and ts > end_time:
            return False

        logic = str(kwargs.get("logic") or "OR").upper()
        threshold_pct = float(kwargs.get("threshold") or 0.0) * 100.0
        clothing = [str(c).lower() for c in kwargs.get("clothing") or []]
        colors = [str(c).lower() for c in kwargs.get("colors") or []]
        item_classes = [str(item.get("class_name") or "").lower() for item in record.get("items", [])]
        if clothing:
            if logic == "AND":
                if not all(cls in item_classes for cls in clothing):
                    return False
            elif not any(cls in item_classes for cls in clothing):
                return False
        if colors:
            checks = []
            for color in colors:
                checks.append(any(pct >= threshold_pct for item in record.get("items", []) for name, pct in self._item_color_pairs(item) if name == color))
            if logic == "AND":
                if not all(checks):
                    return False
            elif not any(checks):
                return False

        for filter_name, suffix in (("brightness", "_colors"), ("temperature", "_colors"), ("vibrancy", "_colors")):
            value = kwargs.get(filter_name)
            if not value:
                continue
            key = f"{value}{suffix}"
            if not any((item.get("colors", {}).get(f"{filter_name}_groups") or {}).get(key, 0) > 0 for item in record.get("items", [])):
                return False
        return True

    def _items_from_person(self, job_id: str, frame_no: int, track_id: int, person: dict[str, Any]) -> list[dict[str, Any]]:
        raw_items = person.get("result_clothing") or person.get("clothing") or []
        items = []
        for idx, item in enumerate(raw_items):
            if not isinstance(item, dict):
                continue
            class_name = self._normalize_class(str(item.get("class") or item.get("raw_class") or "Unknown"))
            category = self._category_for_class(class_name)
            detailed_colors = item.get("detailed_colors") if isinstance(item.get("detailed_colors"), dict) else {}
            color_groups = item.get("color_groups") if isinstance(item.get("color_groups"), dict) else {}
            primary = str(item.get("primary_detailed_color") or self._top_color_name(detailed_colors) or "Unknown")
            items.append(
                {
                    "id": f"{job_id}:{frame_no}:{track_id}:{idx}",
                    "item_index": idx,
                    "class_name": class_name,
                    "category": category,
                    "confidence": float(item.get("confidence") or 0.0),
                    "bbox": item.get("bbox"),
                    "colors": {
                        "top_colors": [{"name": name, "percentage": pct} for name, pct in self._sorted_color_pairs(detailed_colors)],
                        "primary_color": primary,
                        "primary_tone_group": item.get("primary_color_group"),
                        "brightness_groups": self._filter_group(color_groups, ["light_colors", "dark_colors", "medium_colors"]),
                        "temperature_groups": self._filter_group(color_groups, ["warm_colors", "cool_colors", "neutral_colors"]),
                        "vibrancy_groups": self._filter_group(color_groups, ["vibrant_colors", "muted_colors", "pastel_colors"]),
                        "clothing_groups": self._filter_group(color_groups, ["common_shirt_colors", "common_pants_colors", "formal_colors", "casual_colors"]),
                    },
                }
            )
        return items

    def _iter_job_dirs(self, *, include_orphans: bool = False):
        if not self.root.exists():
            return
        seen: set[Path] = set()
        for job in self._load_index().get("jobs", []):
            if not isinstance(job, dict):
                continue
            output_dir = str(job.get("output_dir") or job.get("id") or "")
            if not output_dir:
                continue
            path = self._safe_path(self.root, output_dir)
            if path.exists() and path not in seen and (path / "prediction_results.json").exists():
                seen.add(path)
                yield path
        if include_orphans:
            for child in self.root.iterdir():
                if child.name == "json_jobs" or not child.is_dir() or child in seen:
                    continue
                if (child / "prediction_results.json").exists():
                    seen.add(child)
                    yield child

    def _image_url(
        self,
        job_dir: Path,
        job_id: str,
        person: dict[str, Any],
        track_id: int,
        frame_no: int = 0,
    ) -> str | None:
        """
        Build a thumbnail URL for a detection.

        Primary strategy: generate a /frame-crop URL so FastAPI dynamically
        extracts the bbox region from the source video at the exact frame.

        Fallback (when bbox is missing): serve a pre-saved image file.
        """
        # Prefer saved image_path (live stream jobs always have this)
        image_path = person.get("image_path")
        if image_path:
            path = Path(str(image_path))
            if not path.is_absolute():
                path = (job_dir / path).resolve()
            if path.exists():
                try:
                    relative = path.resolve().relative_to(job_dir.resolve()).as_posix()
                    return f"/api/json/jobs/{job_id}/files/{relative}"
                except ValueError:
                    pass

        # For video jobs: dynamically crop from source video via bbox
        bbox = person.get("bbox")
        if bbox and len(bbox) == 4:
            try:
                x1, y1, x2, y2 = [float(v) for v in bbox]
                return (
                    f"/api/json/jobs/{job_id}/frame-crop"
                    f"?frame={frame_no}&x1={x1:.1f}&y1={y1:.1f}&x2={x2:.1f}&y2={y2:.1f}"
                )
            except (TypeError, ValueError):
                pass

        # Last fallback: json_id pre-saved image
        fallback = self._json_id_image_path(job_dir, track_id)
        if not fallback:
            return None
        path = Path(str(fallback))
        if not path.is_absolute():
            path = (job_dir / path).resolve()
        try:
            relative = path.resolve().relative_to(job_dir.resolve()).as_posix()
        except ValueError:
            return None
        return f"/api/json/jobs/{job_id}/files/{relative}"

    def _json_id_image_path(self, job_dir: Path, track_id: int) -> str | None:
        image_dir = job_dir / "images" / "json_id" / f"id_{track_id}"
        if not image_dir.exists():
            return None
        images = sorted(image_dir.glob("*.jpg"), key=lambda p: p.stat().st_mtime, reverse=True)
        return str(images[0]) if images else None

    def _load_index(self) -> dict[str, Any]:
        if not self.index_path.exists():
            return {"jobs": []}
        data = self._read_json_file(self.index_path)
        if not isinstance(data, dict):
            return {"jobs": []}
        if not isinstance(data.get("jobs"), list):
            data["jobs"] = []
        return data

    def _read_json_file(self, path: Path) -> Any:
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None

    def _write_json(self, path: Path, payload: Any) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = path.with_suffix(path.suffix + ".tmp")
        tmp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp_path.replace(path)

    def _is_deletable_json_result_dir(self, path: Path) -> bool:
        path = path.resolve()
        return path != self.root and self.root in path.parents and (path / "prediction_results.json").exists()

    def _safe_path(self, root: Path, *parts: str) -> Path:
        path = root.joinpath(*parts).resolve()
        if path != root and root not in path.parents:
            raise ValueError(f"Path escapes JSON storage root: {path}")
        return path

    @staticmethod
    def _detection_id(job_id: str, frame_no: int, track_id: int) -> str:
        return f"json:{job_id}:{frame_no}:{track_id}"

    @staticmethod
    def _parse_json_detection_id(value: str) -> tuple[str, int, int] | None:
        parts = value.split(":")
        if len(parts) != 4 or parts[0] != "json":
            return None
        try:
            return parts[1], int(parts[2]), int(parts[3])
        except ValueError:
            return None

    @staticmethod
    def _base_timestamp(job_dir: Path, metadata: dict[str, Any]) -> float:
        source = metadata.get("source_video") or metadata.get("source")
        if source and Path(str(source)).exists():
            return Path(str(source)).stat().st_mtime
        results_path = job_dir / "prediction_results.json"
        return results_path.stat().st_mtime if results_path.exists() else time.time()

    @staticmethod
    def _normalize_class(value: str) -> str:
        return CLASS_MAP.get(value.lower(), value if value else "Unknown")

    @staticmethod
    def _category_for_class(class_name: str) -> str:
        cls = class_name.lower()
        if cls in {"trousers", "shorts", "skirt"}:
            return "BOTTOM"
        if cls == "dress":
            return "DRESS"
        if cls in {"long_sleeve", "short_sleeve"}:
            return "TOP"
        return "UNKNOWN"

    @staticmethod
    def _filter_group(groups: dict[str, Any], keys: list[str]) -> dict[str, float]:
        return {key: float(groups.get(key) or 0.0) for key in keys}

    @staticmethod
    def _sorted_color_pairs(colors: dict[str, Any]) -> list[tuple[str, float]]:
        return sorted(((str(k), float(v or 0.0)) for k, v in colors.items()), key=lambda row: row[1], reverse=True)

    def _item_color_pairs(self, item: dict[str, Any]) -> list[tuple[str, float]]:
        return [(str(c.get("name")).lower(), float(c.get("percentage") or 0.0)) for c in item.get("colors", {}).get("top_colors", []) if c.get("name")]

    def _item_color_names(self, item: dict[str, Any]) -> set[str]:
        names = {name for name, _ in self._item_color_pairs(item)}
        primary = item.get("colors", {}).get("primary_color")
        if primary:
            names.add(str(primary).lower())
        return names

    def _all_top_colors(self, items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        best: dict[str, float] = {}
        for item in items:
            for name, pct in self._item_color_pairs(item):
                best[name] = max(best.get(name, 0.0), pct)
        return [{"name": name, "percentage": pct} for name, pct in sorted(best.items(), key=lambda row: row[1], reverse=True)[:5]]

    @staticmethod
    def _top_color_name(colors: dict[str, Any]) -> str | None:
        if not colors:
            return None
        return max(colors.items(), key=lambda row: float(row[1] or 0.0))[0]

    def _primary_color_profile(self, record: dict[str, Any]) -> dict[str, float] | None:
        items = record.get("items") or []
        if not items:
            return None
        colors = items[0].get("colors", {}).get("top_colors", [])
        return {str(color.get("name")): float(color.get("percentage") or 0.0) for color in colors if color.get("name")}

    @staticmethod
    def _bbox_dict(bbox: Any) -> dict[str, float] | None:
        if not isinstance(bbox, list) or len(bbox) != 4:
            return None
        x1, y1, x2, y2 = [float(v) for v in bbox]
        return {"x": x1, "y": y1, "w": max(0.0, x2 - x1), "h": max(0.0, y2 - y1)}
