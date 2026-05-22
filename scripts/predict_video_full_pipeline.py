from __future__ import annotations

import argparse
import json
import math
import os
import sqlite3
import subprocess
import sys
import time
import uuid
import copy
import queue
import threading
from collections import Counter, defaultdict, deque
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import cv2
import torch
import psutil

WORKSPACE = Path(__file__).resolve().parents[1]
os.environ.setdefault("YOLO_CONFIG_DIR", str(WORKSPACE / ".ultralytics"))
os.environ.setdefault("MPLCONFIGDIR", str(WORKSPACE / ".matplotlib"))

from ultralytics import YOLO

EVAL_DIR = WORKSPACE / "tests" / "evaluation"
if str(EVAL_DIR) not in sys.path:
    sys.path.insert(0, str(EVAL_DIR))

SCRIPT_DIR = WORKSPACE / "scripts"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from apply_viewer_reid import compare_segment, color_distribution, profile_from_person
from evaluate_clothing_model import TARGET_CLASSES, YoloPredictor, prediction_result
from src.ai.color_system import (
    analyze_detailed_colors,
    get_color_groups,
    get_primary_color_group,
    get_primary_detailed_color,
)
from src.config_loader import get_storage_mode
from src.services.storage_adapter import JsonStorageAdapter
from predict_video_clothing_viewer import (
    CLASS_COLORS,
    CLASS_DISPLAY_ORDER,
    VOTE_WINDOW,
    clamp_bbox,
    cut_clips,
    dedupe_persons_by_iou,
    file_url,
    id_color,
    update_track_votes,
    write_viewer,
)


RESULT_RULE_TEXT = (
    "max 2 objects: dress/top/bottom groups; top+top and bottom+bottom impossible; "
    "dress companion only trousers or top>=0.76; skirt confidence x3 against dress; "
    "dress-only observations vote as none_companion so noisy top/bottom flashes do not force a companion"
)


def now() -> float:
    return time.perf_counter()


class Timings:
    def __init__(self) -> None:
        self.seconds: dict[str, float] = defaultdict(float)
        self.counts: dict[str, int] = defaultdict(int)

    def add(self, name: str, elapsed: float, count: int = 1) -> None:
        self.seconds[name] += elapsed
        self.counts[name] += count

    def as_dict(self) -> dict[str, Any]:
        return {
            name: {
                "seconds": round(seconds, 6),
                "count": self.counts.get(name, 0),
                "avg_ms": round(seconds * 1000.0 / self.counts[name], 4) if self.counts.get(name) else None,
            }
            for name, seconds in sorted(self.seconds.items())
        }


def add_yolo_speed_timings(timings: Timings, prefix: str, results: Any) -> None:
    if results is None:
        return
    if not isinstance(results, list):
        results = [results]
    count = len(results)
    if count == 0:
        return
    first_speed = getattr(results[0], "speed", None) or {}
    for key in ("preprocess", "inference", "postprocess"):
        value_ms = first_speed.get(key)
        if value_ms is None:
            continue
        timings.add(f"{prefix}_{key}", float(value_ms) * count / 1000.0, count)


def class_summary(detections: list[dict[str, Any]]) -> str:
    classes = []
    seen = set()
    for name in CLASS_DISPLAY_ORDER:
        if any(det.get("class") == name for det in detections):
            classes.append(name)
            seen.add(name)
    for det in detections:
        name = det.get("class")
        if name and name not in seen:
            classes.append(name)
            seen.add(name)
    return ", ".join(classes) if classes else "unknown"


def clothing_slot(class_name: str) -> str | None:
    if class_name in {"short_sleeve", "long_sleeve"}:
        return "top"
    if class_name == "dress":
        return "dress"
    if class_name in {"shorts", "trousers", "skirt"}:
        return "bottom"
    return None


def outfit_item_from_votes(slot: str, votes: list[dict[str, Any]], total_observations: int) -> dict[str, Any] | None:
    if not votes:
        return None
    by_class: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for vote in votes:
        by_class[vote["class"]].append(vote)
    best_class, best_items = max(
        by_class.items(),
        key=lambda item: (
            len(item[1]),
            sum(float(v.get("confidence") or 0.0) for v in item[1]) / max(len(item[1]), 1),
            -CLASS_DISPLAY_ORDER.index(item[0]) if item[0] in CLASS_DISPLAY_ORDER else -999,
        ),
    )
    avg_conf = sum(float(v.get("confidence") or 0.0) for v in best_items) / max(len(best_items), 1)
    return {
        "slot": slot,
        "class": best_class,
        "votes": len(best_items),
        "slot_observations": len(votes),
        "total_observations": total_observations,
        "ratio": round(len(best_items) / max(total_observations, 1), 4),
        "slot_ratio": round(len(best_items) / max(len(votes), 1), 4),
        "avg_confidence": round(avg_conf, 4),
    }


def choose_final_outfit(slot_results: dict[str, dict[str, Any] | None]) -> list[dict[str, Any]]:
    top = slot_results.get("top")
    dress = slot_results.get("dress")
    bottom = slot_results.get("bottom")
    no_companion = slot_results.get("none_companion")

    def strength(item: dict[str, Any] | None) -> tuple[int, float]:
        if not item:
            return (0, 0.0)
        return (int(item.get("votes") or 0), float(item.get("avg_confidence") or 0.0))

    if dress and strength(dress) >= max(strength(top), strength(bottom)):
        allowed_companions = []
        if top and float(top.get("avg_confidence") or 0.0) >= 0.76:
            allowed_companions.append(top)
        if bottom and bottom.get("class") == "trousers":
            allowed_companions.append(bottom)
        companion = max(allowed_companions, key=strength, default=None)
        selected = [dress]
        # Dress-only observations are real evidence. If "dress + nothing else"
        # wins against noisy top/bottom votes, keep the final outfit as dress only.
        if companion and strength(companion) > strength(no_companion):
            selected.append(companion)
    else:
        selected = [item for item in (top, bottom) if item]

    order = {"top": 0, "dress": 1, "bottom": 2}
    return sorted(selected[:2], key=lambda item: order.get(item.get("slot"), 99))


def apply_final_outfit_votes(data: dict[str, Any], lost_timeout_frames: int = 30) -> dict[str, Any]:
    tracks: dict[int, dict[str, Any]] = {}
    for frame in data.get("frames", []):
        frame_no = int(frame["frame"])
        for person in frame.get("persons", []):
            track_id = int(person["id"])
            if track_id < 0:
                person.pop("final_outfit", None)
                person.pop("final_label", None)
                continue
            track = tracks.setdefault(
                track_id,
                {
                    "id": track_id,
                    "first_frame": frame_no,
                    "last_frame": frame_no,
                    "observations": 0,
                    "slot_votes": {"top": [], "dress": [], "bottom": [], "none_companion": []},
                    "original_ids": set(),
                },
            )
            track["first_frame"] = min(track["first_frame"], frame_no)
            track["last_frame"] = max(track["last_frame"], frame_no)
            track["observations"] += 1
            track["original_ids"].add(int(person.get("original_id", person["id"])))
            frame_items = person.get("result_clothing") or person.get("clothing") or []
            frame_slots = set()
            for item in frame_items:
                slot = clothing_slot(item.get("class", ""))
                if not slot:
                    continue
                frame_slots.add(slot)
                track["slot_votes"][slot].append(
                    {
                        "frame": frame_no,
                        "class": item.get("class"),
                        "confidence": float(item.get("confidence") or 0.0),
                    }
                )
            if "dress" in frame_slots and not ({"top", "bottom"} & frame_slots):
                track["slot_votes"]["none_companion"].append(
                    {
                        "frame": frame_no,
                        "class": "none",
                        "confidence": 1.0,
                    }
                )

    final_by_id: dict[int, dict[str, Any]] = {}
    for track_id, track in tracks.items():
        slot_results = {
            slot: outfit_item_from_votes(slot, votes, int(track["observations"]))
            for slot, votes in track["slot_votes"].items()
        }
        final_items = choose_final_outfit(slot_results)
        label = class_summary(final_items)
        final_by_id[track_id] = {
            "id": track_id,
            "first_frame": track["first_frame"],
            "last_frame": track["last_frame"],
            "observations": track["observations"],
            "original_ids": sorted(track["original_ids"]),
            "lost_timeout_frames": lost_timeout_frames,
            "finalized_reason": "track_ended_or_reid_window_closed",
            "slot_votes": {
                slot: {
                    "observations": len(votes),
                    "class_counts": dict(Counter(vote["class"] for vote in votes)),
                }
                for slot, votes in track["slot_votes"].items()
            },
            "slot_results": slot_results,
            "items": final_items,
            "classes": [item["class"] for item in final_items],
            "label": label,
        }

    for frame in data.get("frames", []):
        for person in frame.get("persons", []):
            final = final_by_id.get(int(person["id"]))
            if final:
                person["final_outfit"] = {
                    "label": final["label"],
                    "classes": final["classes"],
                    "items": final["items"],
                }
                person["final_label"] = final["label"]

    summary = {
        "enabled": True,
        "lost_timeout_frames": lost_timeout_frames,
        "source": "all_result_clothing_observations_after_reid",
        "rule": RESULT_RULE_TEXT,
        "track_count": len(final_by_id),
        "tracks": {str(track_id): final for track_id, final in sorted(final_by_id.items())},
    }
    data.setdefault("metadata", {})["final_outfit_votes"] = summary
    data["metadata"]["result_rule"] = RESULT_RULE_TEXT
    data["metadata"]["display_label_source"] = "final_outfit_votes"
    return summary


def crop_path(root: Path, kind: str, frame_no: int, track_id: int, suffix: str = "") -> Path:
    safe_suffix = f"_{suffix}" if suffix else ""
    return root / kind / f"frame_{frame_no:05d}_id_{track_id}{safe_suffix}.jpg"


def save_jpeg(path: Path, image, quality: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(path), image, [int(cv2.IMWRITE_JPEG_QUALITY), quality])


def add_item_colors(frame, item: dict[str, Any], width: int, height: int) -> None:
    bbox = item.get("bbox")
    if not bbox:
        item["reid_colors"] = {}
        return
    x1, y1, x2, y2 = clamp_bbox([int(v) for v in bbox], width, height) or [0, 0, 0, 0]
    item["reid_colors"] = color_distribution(frame[y1:y2, x1:x2])


def resized_for_color(crop, max_size: int):
    if not max_size or max_size <= 0 or crop is None or crop.size == 0:
        return crop
    h, w = crop.shape[:2]
    longest = max(h, w)
    if longest <= max_size:
        return crop
    scale = max_size / float(longest)
    return cv2.resize(crop, (max(1, int(w * scale)), max(1, int(h * scale))), interpolation=cv2.INTER_AREA)


def add_item_detailed_colors(frame, item: dict[str, Any], width: int, height: int, max_size: int = 0) -> None:
    bbox = item.get("bbox")
    if not bbox:
        item["detailed_colors"] = {}
        item["color_groups"] = {}
        item["primary_detailed_color"] = "unknown"
        item["primary_color_group"] = "unknown"
        return
    x1, y1, x2, y2 = clamp_bbox([int(v) for v in bbox], width, height) or [0, 0, 0, 0]
    detailed_colors = analyze_detailed_colors(resized_for_color(frame[y1:y2, x1:x2], max_size))
    color_groups = get_color_groups(detailed_colors)
    item["detailed_colors"] = detailed_colors
    item["color_groups"] = color_groups
    item["primary_detailed_color"] = get_primary_detailed_color(detailed_colors)
    item["primary_color_group"] = get_primary_color_group(color_groups)


def apply_detailed_color_with_cache(
    frame,
    item: dict[str, Any],
    width: int,
    height: int,
    track_id: int,
    frame_no: int,
    stride: int,
    cache: dict[tuple[int, str], dict[str, Any]],
    timings: Timings,
    color_resize: int = 0,
) -> None:
    slot = clothing_slot(item.get("class", ""))
    if slot is None:
        add_item_detailed_colors(frame, item, width, height, color_resize)
        item["detailed_color_source"] = "analyzed_no_slot"
        return

    stride = max(1, int(stride))
    key = (track_id, slot)
    cached = cache.get(key)
    seen_count = int(cached.get("seen_count", 0)) + 1 if cached else 1
    class_changed = bool(cached and cached.get("class") != item.get("class"))
    if class_changed:
        seen_count = 1
    should_analyze = cached is None or class_changed or stride == 1 or ((seen_count - 1) % stride == 0)

    if should_analyze:
        detail_start = now()
        add_item_detailed_colors(frame, item, width, height, color_resize)
        timings.add("detailed_color_analysis", now() - detail_start, 1)
        item["detailed_color_source"] = "analyzed"
        cache[key] = {
            "class": item.get("class"),
            "slot": slot,
            "seen_count": seen_count,
            "frame": frame_no,
            "detailed_colors": item.get("detailed_colors") or {},
            "color_groups": item.get("color_groups") or {},
            "primary_detailed_color": item.get("primary_detailed_color") or "unknown",
            "primary_color_group": item.get("primary_color_group") or "unknown",
        }
        return

    item["detailed_colors"] = dict(cached.get("detailed_colors") or {})
    item["color_groups"] = dict(cached.get("color_groups") or {})
    item["primary_detailed_color"] = cached.get("primary_detailed_color") or "unknown"
    item["primary_color_group"] = cached.get("primary_color_group") or "unknown"
    item["detailed_color_source"] = "cache"
    item["detailed_color_cached_from_frame"] = cached.get("frame")
    cached["seen_count"] = seen_count
    timings.add("detailed_color_cache_reuse", 0.0, 1)


class OnlineReID:
    def __init__(self, args: argparse.Namespace) -> None:
        self.args = args
        self.compare_args = SimpleNamespace(
            color_threshold=args.reid_color_threshold,
            confirmation_frames=args.reid_confirmation_frames,
            min_hits=args.reid_min_hits,
            max_gap_frames=args.reid_max_gap_frames,
            aggregate_slot_history=args.reid_aggregate_slot_history,
        )
        self.observations_by_id: dict[int, list[dict[str, Any]]] = defaultdict(list)
        self.first_frame: dict[int, int] = {}
        self.last_frame: dict[int, int] = {}
        self.parent: dict[int, int] = {}
        self.finished_ids: list[int] = []
        self.active_ids: set[int] = set()
        self.pending: dict[int, list[int]] = {}
        self.recovered_events: list[dict[str, Any]] = []
        self.remapped_person_rows = 0
        self.attempts = 0
        self.comparisons = 0

    def canonical(self, track_id: int) -> int:
        while self.parent.get(track_id, track_id) != track_id:
            track_id = self.parent[track_id]
        return self.parent.get(track_id, track_id)

    def update(self, frame_no: int, persons: list[dict[str, Any]]) -> list[dict[str, Any]]:
        current_byte_ids = {
            int(person.get("original_id", person["id"]))
            for person in persons
            if int(person.get("original_id", person["id"])) >= 0
        }
        newly_lost = sorted(self.active_ids - current_byte_ids)
        for lost_id in newly_lost:
            if lost_id not in self.finished_ids:
                self.finished_ids.append(lost_id)

        new_ids: list[int] = []
        for person in persons:
            byte_id = int(person.get("original_id", person["id"]))
            if byte_id < 0:
                continue
            person["original_id"] = byte_id
            if byte_id not in self.parent:
                self.parent[byte_id] = byte_id
                self.first_frame[byte_id] = frame_no
                new_ids.append(byte_id)
            self.last_frame[byte_id] = frame_no
            self.observations_by_id[byte_id].append(
                {
                    "frame": frame_no,
                    "profile": person.get("reid_profile", {}),
                    "bbox": person.get("bbox", []),
                }
            )

        for new_id in new_ids:
            start = self.first_frame[new_id]
            candidates = [
                old_id
                for old_id in self.finished_ids
                if old_id != new_id and 0 < start - self.last_frame.get(old_id, start) <= self.args.reid_max_gap_frames
            ]
            if candidates:
                self.pending[new_id] = candidates
                self.attempts += 1

        events = self._update_pending(frame_no)
        for person in persons:
            original_id = int(person.get("original_id", person["id"]))
            canonical_id = self.canonical(original_id)
            if canonical_id != original_id:
                person["id"] = canonical_id
                person["color"] = id_color(canonical_id)
                person["reid_recovered"] = True
                self.remapped_person_rows += 1
            else:
                person["id"] = original_id
                person["reid_recovered"] = False

        self.active_ids = current_byte_ids
        return events

    def _update_pending(self, frame_no: int) -> list[dict[str, Any]]:
        events: list[dict[str, Any]] = []
        for new_id, candidates in list(self.pending.items()):
            new_observations = self.observations_by_id.get(new_id, [])
            if not new_observations:
                continue
            if frame_no - self.first_frame[new_id] > self.args.reid_max_gap_frames + self.args.reid_confirmation_frames:
                self.pending.pop(new_id, None)
                continue

            best_event = None
            for old_id in candidates:
                self.comparisons += 1
                result = compare_segment(self.observations_by_id[old_id], new_observations, self.compare_args)
                if not result["recover"]:
                    continue
                event = {
                    "new_id": new_id,
                    "recovered_id": self.canonical(old_id),
                    "candidate_id": old_id,
                    "start_frame": self.first_frame[new_id],
                    "lost_last_frame": self.last_frame[old_id],
                    "gap_frames": self.first_frame[new_id] - self.last_frame[old_id],
                    "recovered_at_frame": frame_no,
                    "online": True,
                    **result,
                }
                if best_event is None or (event.get("final_score") or 0) > (best_event.get("final_score") or 0):
                    best_event = event
            if best_event:
                self.parent[new_id] = best_event["recovered_id"]
                self.recovered_events.append(best_event)
                events.append(best_event)
                self.pending.pop(new_id, None)
                continue

            if len(new_observations) >= self.args.reid_confirmation_frames:
                self.pending.pop(new_id, None)
        return events

    def summary(self) -> dict[str, Any]:
        return {
            "enabled": True,
            "mode": "online_realtime",
            "color_threshold": self.args.reid_color_threshold,
            "confirmation_frames": self.args.reid_confirmation_frames,
            "min_hits": self.args.reid_min_hits,
            "max_gap_frames": self.args.reid_max_gap_frames,
            "aggregate_slot_history": self.args.reid_aggregate_slot_history,
            "attempts": self.attempts,
            "comparisons": self.comparisons,
            "recovered_tracks": len(self.recovered_events),
            "remapped_person_rows": self.remapped_person_rows,
            "pending_candidates_left": sum(len(items) for items in self.pending.values()),
            "events": self.recovered_events,
        }


def remap_existing_frames(frames: list[dict[str, Any]], event: dict[str, Any]) -> int:
    new_id = int(event["new_id"])
    recovered_id = int(event["recovered_id"])
    remapped = 0
    for frame in frames:
        for person in frame.get("persons", []):
            original_id = int(person.get("original_id", person["id"]))
            if original_id != new_id:
                continue
            person["id"] = recovered_id
            person["color"] = id_color(recovered_id)
            person["reid_recovered"] = True
            remapped += 1
    return remapped


def ensure_sqlite(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS metadata (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS frames (
            frame INTEGER PRIMARY KEY,
            time REAL NOT NULL,
            person_count INTEGER NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS detections (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            frame INTEGER NOT NULL,
            time REAL NOT NULL,
            display_track_id INTEGER NOT NULL,
            original_track_id INTEGER NOT NULL,
            person_confidence REAL NOT NULL,
            bbox_json TEXT NOT NULL,
            label TEXT NOT NULL,
            image_path TEXT,
            reid_recovered INTEGER NOT NULL DEFAULT 0
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS clothing_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            detection_id INTEGER NOT NULL,
            source TEXT NOT NULL,
            item_index INTEGER NOT NULL,
            class_name TEXT NOT NULL,
            confidence REAL NOT NULL,
            bbox_json TEXT,
            colors_json TEXT,
            detailed_colors_json TEXT,
            color_groups_json TEXT,
            primary_detailed_color TEXT,
            primary_color_group TEXT,
            image_path TEXT
        )
        """
    )
    for column_sql in (
        "ALTER TABLE clothing_items ADD COLUMN detailed_colors_json TEXT",
        "ALTER TABLE clothing_items ADD COLUMN color_groups_json TEXT",
        "ALTER TABLE clothing_items ADD COLUMN primary_detailed_color TEXT",
        "ALTER TABLE clothing_items ADD COLUMN primary_color_group TEXT",
    ):
        try:
            conn.execute(column_sql)
        except sqlite3.OperationalError:
            pass
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS reid_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            new_id INTEGER NOT NULL,
            recovered_id INTEGER NOT NULL,
            candidate_id INTEGER NOT NULL,
            start_frame INTEGER NOT NULL,
            lost_last_frame INTEGER NOT NULL,
            gap_frames INTEGER NOT NULL,
            final_score REAL,
            top_hits INTEGER,
            bottom_hits INTEGER,
            event_json TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS timings (
            section TEXT PRIMARY KEY,
            seconds REAL NOT NULL,
            count INTEGER NOT NULL,
            avg_ms REAL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS track_outfits (
            track_id INTEGER PRIMARY KEY,
            first_frame INTEGER NOT NULL,
            last_frame INTEGER NOT NULL,
            observations INTEGER NOT NULL,
            label TEXT NOT NULL,
            classes_json TEXT NOT NULL,
            outfit_json TEXT NOT NULL
        )
        """
    )
    return conn


def save_sqlite(data: dict[str, Any], db_path: Path, timings: Timings) -> None:
    conn = ensure_sqlite(db_path)
    with conn:
        for table in ("metadata", "frames", "detections", "clothing_items", "reid_events", "timings", "track_outfits"):
            conn.execute(f"DELETE FROM {table}")

        for key, value in data.get("metadata", {}).items():
            conn.execute(
                "INSERT INTO metadata(key, value) VALUES(?, ?)",
                (key, json.dumps(value, ensure_ascii=False)),
            )

        for frame in data.get("frames", []):
            conn.execute(
                "INSERT INTO frames(frame, time, person_count) VALUES(?, ?, ?)",
                (frame["frame"], frame["time"], len(frame.get("persons", []))),
            )
            for person in frame.get("persons", []):
                original_id = int(person.get("original_id", person["id"]))
                cursor = conn.execute(
                    """
                    INSERT INTO detections(
                        frame, time, display_track_id, original_track_id, person_confidence,
                        bbox_json, label, image_path, reid_recovered
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        frame["frame"],
                        frame["time"],
                        int(person["id"]),
                        original_id,
                        float(person.get("confidence") or 0.0),
                        json.dumps(person.get("bbox", []), ensure_ascii=False),
                        person.get("label") or person.get("result_label") or "",
                        person.get("image_path"),
                        1 if person.get("reid_recovered") else 0,
                    ),
                )
                detection_id = cursor.lastrowid
                for source_name, items in (
                    ("result", person.get("result_clothing") or person.get("clothing") or []),
                    ("raw", person.get("raw_clothing") or []),
                ):
                    for item_index, item in enumerate(items):
                        conn.execute(
                            """
                            INSERT INTO clothing_items(
                                detection_id, source, item_index, class_name, confidence,
                                bbox_json, colors_json, detailed_colors_json, color_groups_json,
                                primary_detailed_color, primary_color_group, image_path
                            )
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                            """,
                            (
                                detection_id,
                                source_name,
                                item_index,
                                item.get("class", ""),
                                float(item.get("confidence") or 0.0),
                                json.dumps(item.get("bbox"), ensure_ascii=False),
                                json.dumps(item.get("reid_colors") or {}, ensure_ascii=False),
                                json.dumps(item.get("detailed_colors") or {}, ensure_ascii=False),
                                json.dumps(item.get("color_groups") or {}, ensure_ascii=False),
                                item.get("primary_detailed_color") or "unknown",
                                item.get("primary_color_group") or "unknown",
                                item.get("image_path"),
                            ),
                        )

        for event in data.get("metadata", {}).get("viewer_reid", {}).get("events", []):
            hits = event.get("hits") or {}
            conn.execute(
                """
                INSERT INTO reid_events(
                    new_id, recovered_id, candidate_id, start_frame, lost_last_frame,
                    gap_frames, final_score, top_hits, bottom_hits, event_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    int(event["new_id"]),
                    int(event["recovered_id"]),
                    int(event["candidate_id"]),
                    int(event["start_frame"]),
                    int(event["lost_last_frame"]),
                    int(event["gap_frames"]),
                    event.get("final_score"),
                    hits.get("top"),
                    hits.get("bottom"),
                    json.dumps(event, ensure_ascii=False),
                ),
            )

        for track_id, outfit in data.get("metadata", {}).get("final_outfit_votes", {}).get("tracks", {}).items():
            conn.execute(
                """
                INSERT INTO track_outfits(
                    track_id, first_frame, last_frame, observations, label, classes_json, outfit_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    int(track_id),
                    int(outfit.get("first_frame") or 0),
                    int(outfit.get("last_frame") or 0),
                    int(outfit.get("observations") or 0),
                    outfit.get("label") or "",
                    json.dumps(outfit.get("classes") or [], ensure_ascii=False),
                    json.dumps(outfit, ensure_ascii=False),
                ),
            )

        for name, row in timings.as_dict().items():
            conn.execute(
                "INSERT INTO timings(section, seconds, count, avg_ms) VALUES(?, ?, ?, ?)",
                (name, row["seconds"], row["count"], row["avg_ms"]),
            )
    conn.close()


def top_colors_from_distribution(colors: dict[str, float], limit: int = 3) -> list[dict[str, Any]]:
    return [
        {"name": name, "percentage": round(float(value), 4)}
        for name, value in sorted((colors or {}).items(), key=lambda item: float(item[1]), reverse=True)[:limit]
    ]


def item_category(class_name: str) -> str:
    slot = clothing_slot(class_name)
    if slot == "top":
        return "TOP"
    if slot == "bottom":
        return "BOTTOM"
    if slot == "dress":
        return "DRESS"
    return "UNKNOWN"


class GpuSampler:
    def __init__(self, enabled: bool, interval_frames: int, output_dir: Path | None = None) -> None:
        self.enabled = enabled
        self.interval_frames = max(1, int(interval_frames))
        self.progress_path = output_dir / "gpu_progress.json" if output_dir else None
        self.samples: list[dict[str, Any]] = []
        self.errors: list[str] = []

    def maybe_sample(self, frame_no: int, timings: Timings) -> None:
        if not self.enabled or frame_no % self.interval_frames != 0:
            return
        sample_start = now()
        try:
            proc = subprocess.run(
                [
                    "nvidia-smi",
                    "--query-gpu=timestamp,index,name,utilization.gpu,utilization.memory,memory.used,memory.total,power.draw",
                    "--format=csv,noheader,nounits",
                ],
                check=True,
                capture_output=True,
                text=True,
                timeout=5,
            )
            for line in proc.stdout.splitlines():
                parts = [part.strip() for part in line.split(",")]
                if len(parts) < 8:
                    continue
                self.samples.append(
                    {
                        "frame": frame_no,
                        "timestamp": parts[0],
                        "gpu_index": int(parts[1]),
                        "name": parts[2],
                        "gpu_util_pct": float(parts[3]),
                        "memory_util_pct": float(parts[4]),
                        "memory_used_mb": float(parts[5]),
                        "memory_total_mb": float(parts[6]),
                        "power_draw_w": float(parts[7]) if parts[7] not in {"[Not Supported]", "N/A"} else None,
                    }
                )
        except Exception as exc:
            self.errors.append(str(exc))
        finally:
            timings.add("gpu_monitor_sample", now() - sample_start, 1)
            self.write_progress()

    def write_progress(self) -> None:
        if not self.progress_path:
            return
        try:
            self.progress_path.write_text(json.dumps(self.summary(), ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            pass

    def summary(self) -> dict[str, Any]:
        if not self.samples:
            return {"enabled": self.enabled, "samples": 0, "errors": self.errors}
        util = [float(sample["gpu_util_pct"]) for sample in self.samples]
        mem_util = [float(sample["memory_util_pct"]) for sample in self.samples]
        mem_used = [float(sample["memory_used_mb"]) for sample in self.samples]
        power = [float(sample["power_draw_w"]) for sample in self.samples if sample.get("power_draw_w") is not None]
        return {
            "enabled": self.enabled,
            "samples": len(self.samples),
            "avg_gpu_util_pct": round(sum(util) / len(util), 3),
            "max_gpu_util_pct": round(max(util), 3),
            "min_gpu_util_pct": round(min(util), 3),
            "avg_memory_util_pct": round(sum(mem_util) / len(mem_util), 3),
            "max_memory_used_mb": round(max(mem_used), 3),
            "avg_power_draw_w": round(sum(power) / len(power), 3) if power else None,
            "samples_detail": self.samples,
            "errors": self.errors,
        }


class ResourceSampler:
    def __init__(self, enabled: bool, interval_frames: int, output_dir: Path | None = None) -> None:
        self.enabled = enabled
        self.interval_frames = max(1, int(interval_frames))
        self.progress_path = output_dir / "resource_progress.json" if output_dir else None
        self.process = psutil.Process()
        self.samples: list[dict[str, Any]] = []
        self.errors: list[str] = []

    def maybe_sample(self, frame_no: int, timings: Timings) -> None:
        if not self.enabled or frame_no % self.interval_frames != 0:
            return
        sample_start = now()
        try:
            vm = psutil.virtual_memory()
            proc_mem = self.process.memory_info()
            self.samples.append(
                {
                    "frame": frame_no,
                    "cpu_percent": psutil.cpu_percent(interval=None),
                    "ram_total_gb": round(vm.total / (1024 ** 3), 4),
                    "ram_available_gb": round(vm.available / (1024 ** 3), 4),
                    "ram_used_pct": round(vm.percent, 4),
                    "process_rss_mb": round(proc_mem.rss / (1024 ** 2), 4),
                    "process_vms_mb": round(proc_mem.vms / (1024 ** 2), 4),
                }
            )
        except Exception as exc:
            self.errors.append(str(exc))
        finally:
            timings.add("resource_monitor_sample", now() - sample_start, 1)
            self.write_progress()

    def summary(self) -> dict[str, Any]:
        if not self.samples:
            return {"enabled": self.enabled, "samples": 0, "errors": self.errors}
        cpu = [float(sample["cpu_percent"]) for sample in self.samples]
        ram = [float(sample["ram_used_pct"]) for sample in self.samples]
        avail = [float(sample["ram_available_gb"]) for sample in self.samples]
        rss = [float(sample["process_rss_mb"]) for sample in self.samples]
        return {
            "enabled": self.enabled,
            "samples": len(self.samples),
            "avg_cpu_percent": round(sum(cpu) / len(cpu), 3),
            "max_cpu_percent": round(max(cpu), 3),
            "avg_ram_used_pct": round(sum(ram) / len(ram), 3),
            "min_ram_available_gb": round(min(avail), 3),
            "max_process_rss_mb": round(max(rss), 3),
            "samples_detail": self.samples,
            "errors": self.errors,
        }

    def write_progress(self) -> None:
        if not self.progress_path:
            return
        try:
            self.progress_path.write_text(json.dumps(self.summary(), ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            pass


class PrefetchFrameReader:
    def __init__(self, video_path: Path, max_frames: int, queue_size: int) -> None:
        self.video_path = video_path
        self.max_frames = max_frames
        self.queue: queue.Queue[tuple[int, Any] | None] = queue.Queue(maxsize=max(1, queue_size))
        self.thread = threading.Thread(target=self._run, name="frame-prefetch", daemon=True)
        self.thread.start()

    def _run(self) -> None:
        cap = cv2.VideoCapture(str(self.video_path))
        frame_index = -1
        try:
            while frame_index + 1 < self.max_frames:
                ok, frame = cap.read()
                if not ok:
                    break
                frame_index += 1
                self.queue.put((frame_index, frame))
        finally:
            cap.release()
            self.queue.put(None)

    def __iter__(self):
        while True:
            item = self.queue.get()
            if item is None:
                break
            yield item
        self.thread.join(timeout=2.0)


def iter_frames_sequential(cap, max_frames: int):
    frame_index = -1
    while frame_index + 1 < max_frames:
        ok, frame = cap.read()
        if not ok:
            break
        frame_index += 1
        yield frame_index, frame


class ProgressReporter:
    def __init__(self, output_dir: Path, timings: Timings, interval_frames: int) -> None:
        self.output_dir = output_dir
        self.timings = timings
        self.interval_frames = max(1, int(interval_frames))
        self.progress_path = output_dir / "timing_progress.json"
        self.rows: list[dict[str, Any]] = []
        self.last_seconds: dict[str, float] = defaultdict(float)
        self.last_counts: dict[str, int] = defaultdict(int)

    def maybe_report(
        self,
        frame_no: int,
        processed_frames: int,
        realtime_display_frames: int,
        real_db: dict[str, Any],
        gpu: dict[str, Any],
        resources: dict[str, Any] | None = None,
    ) -> None:
        if frame_no < 0 or frame_no % self.interval_frames != 0:
            return
        current_seconds = dict(self.timings.seconds)
        current_counts = dict(self.timings.counts)
        batch: dict[str, Any] = {}
        for name in sorted(current_seconds):
            delta_seconds = current_seconds.get(name, 0.0) - self.last_seconds.get(name, 0.0)
            delta_count = current_counts.get(name, 0) - self.last_counts.get(name, 0)
            if delta_seconds <= 0 and delta_count <= 0:
                continue
            batch[name] = {
                "seconds": round(delta_seconds, 6),
                "count": delta_count,
                "avg_ms": round(delta_seconds * 1000.0 / delta_count, 4) if delta_count else None,
            }

        elapsed = sum(current_seconds.values())
        row = {
            "frame": frame_no,
            "processed_frames": processed_frames,
            "realtime_display_frames": realtime_display_frames,
            "processed_frame_fps_partial": round(processed_frames / max(elapsed, 0.0001), 4),
            "realtime_display_fps_partial": round(realtime_display_frames / max(elapsed, 0.0001), 4),
            "batch_timings": batch,
            "total_timings": self.timings.as_dict(),
            "real_db_progress": dict(real_db or {}),
            "gpu_summary": {
                key: value
                for key, value in (gpu or {}).items()
                if key != "samples_detail"
            },
            "resource_summary": {
                key: value
                for key, value in (resources or {}).items()
                if key != "samples_detail"
            },
        }
        self.rows.append(row)
        self.last_seconds = current_seconds
        self.last_counts = current_counts
        self.write()

        gpu_text = ""
        if gpu.get("samples"):
            gpu_text = f", gpu avg/max {gpu.get('avg_gpu_util_pct')}%/{gpu.get('max_gpu_util_pct')}%"
        db_text = ""
        if real_db.get("enabled"):
            db_text = (
                f", db {real_db.get('detections_saved', 0)} det, "
                f"minio {real_db.get('minio_uploads', 0)}"
            )
        print(
            f"[progress] frame={frame_no} processed={processed_frames} "
            f"display={realtime_display_frames} fps={row['realtime_display_fps_partial']}{db_text}{gpu_text}",
            flush=True,
        )

    def write(self) -> None:
        payload = {
            "interval_frames": self.interval_frames,
            "batches": self.rows,
        }
        self.progress_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


class JsonJobReporter:
    def __init__(self, args: argparse.Namespace, output_dir: Path, video_path: Path) -> None:
        self.args = args
        self.job_id = getattr(args, "job_id", "") or ""
        self.output_dir = output_dir
        self.last_frame_reported = -1
        self.adapter: JsonStorageAdapter | None = None
        if not self.job_id:
            return
        index_path = getattr(args, "json_index", "") or None
        self.adapter = JsonStorageAdapter(index_path=index_path)
        self.adapter.register_job(
            self.job_id,
            label=getattr(args, "db_video_label", None) or self.job_id,
            source=str(video_path),
            status="processing",
            output_dir=output_dir.name,
            metadata={
                "camera_id": getattr(args, "camera_id", None),
                "frame_stride": getattr(args, "frame_stride", None),
                "person_conf": getattr(args, "person_conf", None),
                "clothing_conf": getattr(args, "clothing_conf", None),
                "output_dir": str(output_dir),
            },
        )

    def update(
        self,
        *,
        frame_no: int,
        frames_processed: int,
        total_frames: int,
        detections_count: int,
        fps_output: float | None = None,
        extra_metadata: dict[str, Any] | None = None,
    ) -> None:
        if self.adapter is None or not self.job_id:
            return
        if frame_no == self.last_frame_reported:
            return
        self.last_frame_reported = frame_no
        progress_pct = int(frames_processed * 100 / max(total_frames, 1)) if total_frames else 0
        metadata = {
            "frames_processed": frames_processed,
            "total_frames": total_frames,
            "progress_pct": min(100, progress_pct),
            "detections_count": detections_count,
            "fps_output": fps_output,
        }
        if extra_metadata:
            metadata.update(extra_metadata)
        self.adapter.update_job(self.job_id, status="processing", metadata=metadata)

    def finalize(self, status: str, metadata: dict[str, Any] | None = None, error_message: str | None = None) -> None:
        if self.adapter is None or not self.job_id:
            return
        self.adapter.finalize_job(
            self.job_id,
            status=status,
            metadata=metadata or {},
            error_message=error_message,
        )


class StreamingRealDbSaver:
    def __init__(
        self,
        args: argparse.Namespace,
        timings: Timings,
        video_path: Path,
        width: int,
        height: int,
        output_dir: Path,
    ) -> None:
        self.args = args
        self.timings = timings
        self.pending_frames: list[dict[str, Any]] = []
        self.last_flush_frame = -1
        self.db = None
        self.storage = None
        self.progress_path = output_dir / "real_db_progress.json"
        self.summary_data: dict[str, Any] = {
            "enabled": bool(args.save_real_db and args.stream_real_db),
            "mode": "streaming_every_n_source_frames",
            "flush_frame_interval": args.real_db_flush_frame_interval,
            "status": "skipped",
            "video_id": None,
            "flushes": 0,
            "detections_saved": 0,
            "items_saved": 0,
            "minio_uploads": 0,
            "errors": [],
        }
        if not self.summary_data["enabled"]:
            return

        try:
            from src.services.database import DatabaseService
            from src.services.storage import StorageService
        except Exception as exc:
            self.summary_data["status"] = "import_failed"
            self.summary_data["errors"].append(str(exc))
            return

        connect_start = now()
        self.db = DatabaseService()
        self.timings.add("postgres_connect_setup", now() - connect_start)
        if self.db.conn is None:
            self.summary_data["status"] = "postgres_connection_failed"
            return

        if args.save_real_db_images:
            storage_start = now()
            try:
                self.storage = StorageService()
                self.summary_data["minio_enabled"] = True
            except Exception as exc:
                self.summary_data["errors"].append(f"MinIO init failed: {exc}")
                self.summary_data["minio_enabled"] = False
            self.timings.add("minio_connect_setup", now() - storage_start)

        register_start = now()
        video_id = self.db.register_video(
            camera_id=args.camera_id,
            label=args.db_video_label,
            filename=video_path.name,
            file_path=str(video_path),
            width=width,
            height=height,
        )
        self.timings.add("postgres_register_video", now() - register_start)
        self.summary_data["video_id"] = str(video_id) if video_id else None
        self.summary_data["status"] = "active" if video_id else "video_register_failed"
        self.write_progress()

    def write_progress(self) -> None:
        try:
            self.progress_path.write_text(json.dumps(self.summary_data, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            pass

    def enqueue(self, frame_row: dict[str, Any], frame_no: int) -> None:
        if self.summary_data.get("status") != "active":
            return
        self.pending_frames.append(frame_row)
        if self.last_flush_frame < 0:
            self.last_flush_frame = frame_no
        if frame_no - self.last_flush_frame >= self.args.real_db_flush_frame_interval:
            self.flush(frame_no)

    def flush(self, frame_no: int | None = None) -> None:
        if self.summary_data.get("status") not in {"active", "completed"} or not self.pending_frames or self.db is None:
            return
        flush_start = now()
        frames_to_save = self.pending_frames
        self.pending_frames = []
        self.summary_data["flushes"] += 1
        if frame_no is not None:
            self.last_flush_frame = frame_no

        run_prefix = f"detections/{self.args.camera_id}/{self.summary_data.get('video_id')}"
        for frame in frames_to_save:
            for person in frame.get("persons", []):
                image_path = None
                local_image_path = person.get("image_path")
                if self.storage is not None and local_image_path and Path(local_image_path).exists():
                    upload_start = now()
                    image = cv2.imread(local_image_path)
                    object_name = f"{run_prefix}/{int(frame['frame']):05d}_{int(person['id'])}_{uuid.uuid4().hex[:8]}.jpg"
                    image_path = self.storage.upload_image(image, object_name) if image is not None else None
                    self.timings.add("minio_upload", now() - upload_start, 1)
                    if image_path:
                        self.summary_data["minio_uploads"] += 1

                result_items = person.get("result_clothing") or person.get("clothing") or []
                label = person.get("final_label") or person.get("result_label") or person.get("label") or class_summary(result_items)
                insert_start = now()
                detection_id = self.db.insert_detection(
                    camera_id=self.args.camera_id,
                    track_id=int(person["id"]),
                    class_name=label,
                    image_path=image_path or local_image_path,
                    category="person",
                    video_time_offset=float(frame.get("time") or 0.0),
                    video_id=str(self.summary_data.get("video_id")),
                    bbox=person.get("bbox"),
                    embedding=None,
                )
                self.timings.add("postgres_insert_detection", now() - insert_start, 1)
                if not detection_id:
                    self.summary_data["errors"].append(f"insert_detection failed frame={frame.get('frame')} id={person.get('id')}")
                    continue
                self.summary_data["detections_saved"] += 1

                db_items = [
                    {
                        "item_index": item_index,
                        "class_name": item.get("class", ""),
                        "category": item_category(item.get("class", "")),
                        "confidence": float(item.get("confidence") or 0.0),
                        "bbox": item.get("bbox"),
                    }
                    for item_index, item in enumerate(result_items)
                ]
                if db_items:
                    item_start = now()
                    item_ids = self.db.insert_detection_items(str(detection_id), db_items)
                    self.timings.add("postgres_insert_items", now() - item_start, len(db_items))
                    self.summary_data["items_saved"] += len(item_ids)
                    for item_id, item in zip(item_ids, result_items):
                        color_start = now()
                        self.db.insert_detection_colors(
                            detection_id=str(detection_id),
                            detection_item_id=str(item_id),
                            top_colors=top_colors_from_distribution(item.get("detailed_colors") or {}),
                            clothing_groups=item.get("color_groups") or {},
                            primary_color=item.get("primary_detailed_color") or "unknown",
                            primary_tone_group=item.get("primary_color_group") or "unknown",
                        )
                        self.timings.add("postgres_insert_item_colors", now() - color_start, 1)

        self.timings.add("stream_real_db_flush", now() - flush_start, 1)
        self.write_progress()

    def close(self) -> dict[str, Any]:
        if self.summary_data.get("status") == "active":
            self.flush()
            if self.db is not None and self.summary_data.get("video_id"):
                status_start = now()
                self.db.update_video_status(self.summary_data["video_id"], "completed")
                self.timings.add("postgres_update_video_status", now() - status_start)
            self.summary_data["status"] = "completed"
            self.write_progress()
        if self.db is not None:
            self.db.close()
        return self.summary_data


def save_real_db(data: dict[str, Any], args: argparse.Namespace, timings: Timings) -> dict[str, Any]:
    summary = {
        "enabled": bool(args.save_real_db),
        "status": "skipped",
        "video_id": None,
        "detections_saved": 0,
        "items_saved": 0,
        "minio_uploads": 0,
        "errors": [],
    }
    if not args.save_real_db:
        return summary

    try:
        from src.services.database import DatabaseService
        from src.services.storage import StorageService
    except Exception as exc:
        summary["status"] = "import_failed"
        summary["errors"].append(str(exc))
        return summary

    metadata = data.get("metadata", {})
    db_start = now()
    db = DatabaseService()
    timings.add("postgres_connect_setup", now() - db_start)
    if db.conn is None:
        summary["status"] = "postgres_connection_failed"
        return summary

    storage = None
    if args.save_real_db_images:
        storage_start = now()
        try:
            storage = StorageService()
            summary["minio_enabled"] = True
        except Exception as exc:
            summary["errors"].append(f"MinIO init failed: {exc}")
            summary["minio_enabled"] = False
        timings.add("minio_connect_setup", now() - storage_start)

    register_start = now()
    video_id = db.register_video(
        camera_id=args.camera_id,
        label=args.db_video_label,
        filename=Path(metadata.get("source_video") or args.video).name,
        file_path=metadata.get("source_video") or args.video,
        width=metadata.get("width"),
        height=metadata.get("height"),
    )
    timings.add("postgres_register_video", now() - register_start)
    summary["video_id"] = str(video_id) if video_id else None
    if not video_id:
        summary["status"] = "video_register_failed"
        db.close()
        return summary

    run_prefix = f"detections/{args.camera_id}/{video_id}"
    for frame in data.get("frames", []):
        for person in frame.get("persons", []):
            image_path = None
            local_image_path = person.get("image_path")
            if storage is not None and local_image_path and Path(local_image_path).exists():
                upload_start = now()
                image = cv2.imread(local_image_path)
                object_name = f"{run_prefix}/{int(frame['frame']):05d}_{int(person['id'])}_{uuid.uuid4().hex[:8]}.jpg"
                image_path = storage.upload_image(image, object_name) if image is not None else None
                timings.add("minio_upload", now() - upload_start, 1)
                if image_path:
                    summary["minio_uploads"] += 1

            result_items = person.get("result_clothing") or person.get("clothing") or []
            label = person.get("final_label") or person.get("result_label") or person.get("label") or class_summary(result_items)
            insert_start = now()
            detection_id = db.insert_detection(
                camera_id=args.camera_id,
                track_id=int(person["id"]),
                class_name=label,
                image_path=image_path or local_image_path,
                category="person",
                video_time_offset=float(frame.get("time") or 0.0),
                video_id=str(video_id),
                bbox=person.get("bbox"),
                embedding=None,
            )
            timings.add("postgres_insert_detection", now() - insert_start, 1)
            if not detection_id:
                summary["errors"].append(f"insert_detection failed frame={frame.get('frame')} id={person.get('id')}")
                continue
            summary["detections_saved"] += 1

            db_items = [
                {
                    "item_index": item_index,
                    "class_name": item.get("class", ""),
                    "category": item_category(item.get("class", "")),
                    "confidence": float(item.get("confidence") or 0.0),
                    "bbox": item.get("bbox"),
                }
                for item_index, item in enumerate(result_items)
            ]
            if not db_items:
                continue
            item_start = now()
            item_ids = db.insert_detection_items(str(detection_id), db_items)
            timings.add("postgres_insert_items", now() - item_start, len(db_items))
            summary["items_saved"] += len(item_ids)

            for item_id, item in zip(item_ids, result_items):
                color_start = now()
                db.insert_detection_colors(
                    detection_id=str(detection_id),
                    detection_item_id=str(item_id),
                    top_colors=top_colors_from_distribution(item.get("detailed_colors") or {}),
                    clothing_groups=item.get("color_groups") or {},
                    primary_color=item.get("primary_detailed_color") or "unknown",
                    primary_tone_group=item.get("primary_color_group") or "unknown",
                )
                timings.add("postgres_insert_item_colors", now() - color_start, 1)

    status_start = now()
    db.update_video_status(video_id, "completed")
    timings.add("postgres_update_video_status", now() - status_start)
    db.close()
    summary["status"] = "completed"
    return summary


def save_outputs(data: dict[str, Any], output_dir: Path, clips: dict[str, str]) -> None:
    (output_dir / "prediction_results.json").write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    (output_dir / "prediction_results_compact.json").write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    (output_dir / "prediction_data.js").write_text(
        "window.PREDICTION_DATA = " + json.dumps(data, ensure_ascii=False) + ";\n",
        encoding="utf-8",
    )
    write_viewer(
        output_dir / "video_prediction_viewer.html",
        file_url(Path(clips["first_clip"])),
        file_url(Path(clips["frame_clip"])),
        int(data["metadata"].get("frame_clip_start", 1000)),
    )


def save_json_only(data: dict[str, Any], output_dir: Path) -> None:
    (output_dir / "prediction_results.json").write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


def load_baseline(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    metadata = data.get("metadata", {})
    return {
        "path": str(path),
        "person_conf": metadata.get("person_conf"),
        "person_rows_after_iou_dedupe": metadata.get("person_rows_after_iou_dedupe"),
        "unique_person_ids_after_iou_dedupe": metadata.get("unique_person_ids_after_iou_dedupe"),
        "recovered_tracks": (metadata.get("viewer_reid") or {}).get("recovered_tracks"),
    }


def write_summary(output_dir: Path, data: dict[str, Any], timings: Timings) -> None:
    metadata = data["metadata"]
    reid = metadata.get("viewer_reid", {})
    baseline = metadata.get("baseline_compare", {})
    class_counts = Counter()
    raw_class_counts = Counter()
    labels = Counter()
    original_ids = set()
    display_ids = set()
    recovered_ids = Counter()
    for frame in data.get("frames", []):
        for person in frame.get("persons", []):
            original_ids.add(int(person.get("original_id", person["id"])))
            display_ids.add(int(person["id"]))
            labels[person.get("label") or "unknown"] += 1
            if person.get("reid_recovered"):
                recovered_ids[int(person.get("original_id", person["id"]))] += 1
            for item in person.get("result_clothing") or person.get("clothing") or []:
                class_counts[item.get("class", "unknown")] += 1
            for item in person.get("raw_clothing") or []:
                raw_class_counts[item.get("class", "unknown")] += 1

    recovered_events = reid.get("events", [])
    final_outfits = metadata.get("final_outfit_votes", {})
    lines = [
        "# YOLO11s person_conf 0.45 full pipeline summary",
        "",
        "## Config",
        f"- Source video: `{metadata['source_video']}`",
        f"- Detector: `{metadata['detector_model']}`",
        f"- Clothing model: `{metadata['clothing_model']}`",
        f"- Device: `{metadata['device']}`",
        f"- Person conf: `{metadata['person_conf']}`",
        f"- Clothing conf: `{metadata['clothing_conf']}`",
        f"- IoU dedupe threshold: `{metadata['person_iou_dedupe_threshold']}`",
        f"- Re-ID: clothing class + color only, threshold `{reid.get('color_threshold')}`, confirm `{reid.get('min_hits')}/{reid.get('confirmation_frames')}`",
        "",
        "## Result",
        f"- Processed frames: `{metadata['processed_frames']}`",
        f"- Realtime display frames including skipped frames: `{metadata.get('realtime_display_frames')}`",
        f"- Skipped display frames using previous processed result: `{metadata.get('skipped_display_frames')}`",
        f"- Processed-frame FPS excluding final file writes: `{metadata.get('processed_output_fps_excluding_file_db_write')}`",
        f"- Realtime display FPS excluding final file writes: `{metadata.get('realtime_display_fps_excluding_file_db_write')}`",
        f"- Note: streaming DB/MinIO time is included in these FPS numbers when `stream_real_db` is enabled.",
        f"- Realtime display FPS including exports/DB writes: `{metadata.get('realtime_display_fps_including_exports', metadata.get('output_fps'))}`",
        f"- Person rows before IoU dedupe: `{metadata['person_rows_before_iou_dedupe']}`",
        f"- Person rows after IoU dedupe: `{metadata['person_rows_after_iou_dedupe']}`",
        f"- Suppressed by IoU dedupe: `{metadata['person_rows_suppressed_by_iou_dedupe']}`",
        f"- New ByteTrack IDs after IoU dedupe: `{len(original_ids)}`",
        f"- Display IDs after Re-ID: `{len(display_ids)}`",
        f"- Recovered track events: `{reid.get('recovered_tracks', 0)}`",
        f"- Recovered person rows: `{reid.get('remapped_person_rows', 0)}`",
        f"- Final outfit voted IDs: `{final_outfits.get('track_count', 0)}`",
        f"- SQLite DB: `{metadata['sqlite_db']}`",
        f"- Images dir: `{metadata['images_dir']}`",
        f"- Viewer: `{output_dir / 'video_prediction_viewer.html'}`",
        "",
        "## Person Conf 0.45 vs Baseline 0.25",
    ]
    if baseline:
        old_rows = baseline.get("person_rows_after_iou_dedupe")
        old_ids = baseline.get("unique_person_ids_after_iou_dedupe")
        new_rows = metadata["person_rows_after_iou_dedupe"]
        new_ids = len(original_ids)
        row_drop = old_rows - new_rows if isinstance(old_rows, int) else None
        id_drop = old_ids - new_ids if isinstance(old_ids, int) else None
        lines.extend(
            [
                f"- Baseline file: `{baseline.get('path')}`",
                f"- Baseline person rows after IoU: `{old_rows}` -> new `{new_rows}`"
                + (f" ลดลง `{row_drop}` (`{row_drop / old_rows * 100:.2f}%`)" if old_rows and row_drop is not None else ""),
                f"- Baseline unique IDs after IoU: `{old_ids}` -> new `{new_ids}`"
                + (f" ลดลง `{id_drop}` (`{id_drop / old_ids * 100:.2f}%`)" if old_ids and id_drop is not None else ""),
            ]
        )
    else:
        lines.append("- No baseline file found.")

    lines.extend(["", "## Re-ID Summary"])
    lines.append(f"- ByteTrack new ID count: `{len(original_ids)}`")
    lines.append(f"- System recovered count: `{reid.get('recovered_tracks', 0)}`")
    lines.append(f"- Recovered person rows: `{reid.get('remapped_person_rows', 0)}`")
    lines.append(f"- Re-ID mode: `{reid.get('mode', 'unknown')}`")
    lines.append(f"- Re-ID attempts: `{reid.get('attempts', 0)}`")
    lines.append(f"- Re-ID comparisons: `{reid.get('comparisons', 0)}`")
    lines.append(f"- Color feature source: `{metadata.get('reid_color_feature_source', 'unknown')}`")

    lines.extend(["", "## Final Outfit Votes"])
    tracks = final_outfits.get("tracks", {})
    if tracks:
        for track_id, outfit in sorted(tracks.items(), key=lambda item: int(item[0]))[:80]:
            lines.append(
                f"- ID `{track_id}`: `{outfit.get('label')}` "
                f"(frames `{outfit.get('first_frame')}-{outfit.get('last_frame')}`, "
                f"observations `{outfit.get('observations')}`)"
            )
        if len(tracks) > 80:
            lines.append(f"- ...อีก `{len(tracks) - 80}` IDs ดูเต็มใน `prediction_results.json` metadata.final_outfit_votes")
    else:
        lines.append("- No final outfit votes.")

    lines.extend(["", "## Result Clothing Counts"])
    for name in TARGET_CLASSES:
        lines.append(f"- {name}: `{class_counts.get(name, 0)}`")

    lines.extend(["", "## Raw Clothing Counts"])
    for name in TARGET_CLASSES:
        lines.append(f"- {name}: `{raw_class_counts.get(name, 0)}`")

    requested_timing_names = [
        "model_load",
        "frame_prefetch_enabled",
        "person_detect_track",
        "person_detect_predict",
        "person_yolo_preprocess",
        "person_yolo_inference",
        "person_yolo_postprocess",
        "person_boxes_extract_crop",
        "iou_dedupe",
        "clothing_cache_eval",
        "clothing_disabled_persons",
        "clothing_predict",
        "clothing_yolo_preprocess",
        "clothing_yolo_inference",
        "clothing_yolo_postprocess",
        "clothing_temporal_cache_hit",
        "clothing_rule_postprocess",
        "clothing_basic_color",
        "detailed_color_analysis",
        "reid_online_step",
        "reid_disabled_step",
        "final_outfit_vote",
        "postgres_connect_setup",
        "minio_connect_setup",
        "postgres_register_video",
        "minio_upload",
        "postgres_insert_detection",
        "postgres_insert_items",
        "postgres_insert_item_colors",
        "postgres_update_video_status",
        "stream_real_db_flush",
        "real_db_save",
        "gpu_monitor_sample",
        "resource_monitor_sample",
    ]
    timing_rows = timings.as_dict()
    lines.extend(["", "## Timings"])
    lines.append("| Step | Total time (sec) | Runs | Avg time |")
    lines.append("|---|---:|---:|---:|")
    for name in requested_timing_names:
        row = timing_rows.get(name)
        if not row:
            continue
        lines.append(f"| {name} | {row['seconds']} | {row['count']} | {row['avg_ms']} ms |")

    real_db = metadata.get("real_db_save", {})
    lines.extend(["", "## Real DB / MinIO Save"])
    lines.append(f"- Enabled: `{real_db.get('enabled', False)}`")
    lines.append(f"- Status: `{real_db.get('status', 'unknown')}`")
    lines.append(f"- Video ID: `{real_db.get('video_id')}`")
    lines.append(f"- Detections saved: `{real_db.get('detections_saved', 0)}`")
    lines.append(f"- Clothing items saved: `{real_db.get('items_saved', 0)}`")
    lines.append(f"- MinIO uploads: `{real_db.get('minio_uploads', 0)}`")
    if real_db.get("errors"):
        lines.append(f"- Errors: `{len(real_db.get('errors') or [])}` ดูรายละเอียดใน `prediction_results.json`")

    gpu = metadata.get("gpu_monitor", {})
    lines.extend(["", "## GPU Monitor"])
    lines.append(f"- Enabled: `{gpu.get('enabled', False)}`")
    lines.append(f"- Samples: `{gpu.get('samples', 0)}`")
    if gpu.get("samples"):
        lines.append(f"- Avg GPU util: `{gpu.get('avg_gpu_util_pct')}`%")
        lines.append(f"- Max GPU util: `{gpu.get('max_gpu_util_pct')}`%")
        lines.append(f"- Min GPU util: `{gpu.get('min_gpu_util_pct')}`%")
        lines.append(f"- Avg memory util: `{gpu.get('avg_memory_util_pct')}`%")
        lines.append(f"- Max memory used: `{gpu.get('max_memory_used_mb')}` MB")
        if gpu.get("avg_power_draw_w") is not None:
            lines.append(f"- Avg power draw: `{gpu.get('avg_power_draw_w')}` W")

    resources = metadata.get("resource_monitor", {})
    lines.extend(["", "## Resource Monitor"])
    lines.append(f"- Enabled: `{resources.get('enabled', False)}`")
    lines.append(f"- Samples: `{resources.get('samples', 0)}`")
    if resources.get("samples"):
        lines.append(f"- Avg CPU: `{resources.get('avg_cpu_percent')}`%")
        lines.append(f"- Max CPU: `{resources.get('max_cpu_percent')}`%")
        lines.append(f"- Avg RAM used: `{resources.get('avg_ram_used_pct')}`%")
        lines.append(f"- Min RAM available: `{resources.get('min_ram_available_gb')}` GB")
        lines.append(f"- Max process RSS: `{resources.get('max_process_rss_mb')}` MB")

    (output_dir / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def predict_full(args: argparse.Namespace) -> tuple[dict[str, Any], Timings]:
    timings = Timings()
    total_start = now()

    output_dir = (WORKSPACE / args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    image_root = output_dir / "images"
    for subdir in ("person", "clothing"):
        (image_root / subdir).mkdir(parents=True, exist_ok=True)

    video_path = Path(args.video).resolve()
    if args.skip_clip_cut:
        clips = {"first_clip": str(video_path), "frame_clip": str(video_path)}
        timings.add("clip_cut_skipped", 0.0, 1)
    else:
        clip_start = now()
        clips = cut_clips(video_path, output_dir, args.seconds, args.frame_start, args.frame_end)
        timings.add("clip_cut", now() - clip_start)

    device = args.device
    if device == "auto":
        device = "cuda" if torch.cuda.is_available() else "cpu"

    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise RuntimeError(f"Could not open video: {video_path}")
    fps = float(cap.get(cv2.CAP_PROP_FPS) or 30.0)
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    max_frames = min(total_frames, int(math.floor(args.seconds * fps)))
    if args.max_source_frames:
        max_frames = min(max_frames, int(args.max_source_frames))
    json_job_reporter = JsonJobReporter(args, output_dir, video_path)
    json_job_reporter.update(
        frame_no=0,
        frames_processed=0,
        total_frames=max_frames,
        detections_count=0,
        extra_metadata={
            "source_total_frames": total_frames,
            "width": width,
            "height": height,
            "fps": fps,
        },
    )

    model_start = now()
    detector = YOLO(str(Path(args.detector).resolve()))
    detector.to(device)
    clothing = YoloPredictor(
        Path(args.model).resolve(),
        device=device,
        imgsz=args.imgsz_clothing,
        conf=args.clothing_conf,
        half=args.fp16,
    )
    timings.add("model_load", now() - model_start)

    frames: list[dict[str, Any]] = []
    vote_history: dict[int, dict[str, deque[str]]] = defaultdict(dict)
    detailed_color_cache: dict[tuple[int, str], dict[str, Any]] = {}
    clothing_temporal_cache: dict[int, dict[str, Any]] = {}
    online_reid = OnlineReID(args)
    gpu_sampler = GpuSampler(args.monitor_gpu, args.gpu_sample_interval_frames, output_dir)
    resource_sampler = ResourceSampler(args.monitor_resources, args.resource_sample_interval_frames, output_dir)
    streaming_db = StreamingRealDbSaver(args, timings, video_path, width, height, output_dir)
    progress_reporter = ProgressReporter(output_dir, timings, args.progress_report_interval_frames)
    detections_count = 0
    person_rows_before_iou = 0
    person_rows_after_iou = 0
    suppressed_by_iou = 0

    if args.frame_prefetch:
        cap.release()
        frame_iter = PrefetchFrameReader(video_path, max_frames, args.frame_prefetch_size)
        timings.add("frame_prefetch_enabled", 0.0, 1)
    else:
        frame_iter = iter_frames_sequential(cap, max_frames)

    frame_index = -1
    for frame_index, frame in frame_iter:
        if frame_index % max(args.frame_stride, 1) != 0:
            continue
        if frame_index % args.log_every == 0:
            print(f"[full-predict] frame {frame_index}/{max_frames} ({frame_index / fps:.2f}s)", flush=True)
        gpu_sampler.maybe_sample(frame_index, timings)
        resource_sampler.maybe_sample(frame_index, timings)

        detect_start = now()
        if args.person_inference_mode == "predict":
            result = detector.predict(
                frame,
                classes=[0],
                conf=args.person_conf,
                imgsz=args.imgsz_person,
                device=device,
                half=args.fp16 if str(device).startswith("cuda") else False,
                verbose=False,
            )[0]
        else:
            result = detector.track(
                frame,
                persist=True,
                tracker="bytetrack.yaml",
                classes=[0],
                conf=args.person_conf,
                imgsz=args.imgsz_person,
                device=device,
                half=args.fp16 if str(device).startswith("cuda") else False,
                verbose=False,
            )[0]
        add_yolo_speed_timings(timings, "person_yolo", result)
        person_timer_name = "person_detect_predict" if args.person_inference_mode == "predict" else "person_detect_track"
        timings.add(person_timer_name, now() - detect_start)

        persons: list[dict[str, Any]] = []
        crops: list[Any] = []
        crop_meta: list[dict[str, Any]] = []
        boxes_start = now()
        boxes = getattr(result, "boxes", None)
        if boxes is not None and len(boxes) > 0:
            ids = boxes.id
            if ids is None:
                if args.person_inference_mode == "predict":
                    ids = [None] * len(boxes)
                else:
                    timings.add("untracked_person_boxes_skipped", 0.0, len(boxes))
                    boxes = []
            for det_idx, box in enumerate(boxes):
                bbox = clamp_bbox([int(v) for v in box.xyxy[0].tolist()], width, height)
                if bbox is None:
                    continue
                x1, y1, x2, y2 = bbox
                crop = None
                if not (args.disable_clothing and not args.save_local_images):
                    crop = frame[y1:y2, x1:x2]
                    if crop.size == 0:
                        continue
                track_id = int(ids[det_idx].item()) if ids[det_idx] is not None else int(frame_index * 10000 + det_idx)
                if track_id < 0:
                    timings.add("untracked_person_boxes_skipped", 0.0, 1)
                    continue
                person = {
                    "_order": len(persons),
                    "id": track_id,
                    "bbox": bbox,
                    "confidence": float(box.conf.item()),
                    "color": id_color(track_id),
                    "clothing": [],
                    "raw_clothing": [],
                    "label": "",
                }
                persons.append(person)
                if crop is not None:
                    crops.append(crop)
                    crop_meta.append({"person": person, "offset": (x1, y1), "crop": crop})
        timings.add("person_boxes_extract_crop", now() - boxes_start, max(len(persons), 1))

        predict_metas: list[dict[str, Any]] = []
        predict_crops: list[Any] = []
        if args.disable_clothing:
            for person in persons:
                person["raw_clothing"] = []
                person["clothing"] = []
                person["result_clothing"] = []
                person["result_label"] = ""
                person["frame_label"] = ""
                person["stable_clothing"] = {"label": "", "classes": []}
                person["stable_label"] = ""
                person["label"] = ""
                person["reid_profile"] = {}
            timings.add("clothing_disabled_persons", 0.0, len(persons))
        else:
            cache_eval_start = now()
            for meta in crop_meta:
                person = meta["person"]
                track_id = int(person["id"])
                cached = clothing_temporal_cache.get(track_id)
                cache_age = frame_index - int(cached.get("frame", -10**9)) if cached else 10**9
                use_cache = bool(
                    args.clothing_temporal_cache_frames > 0
                    and cached
                    and cache_age < args.clothing_temporal_cache_frames
                )
                if use_cache:
                    raw_items = copy.deepcopy(cached.get("raw_clothing") or [])
                    final_items = copy.deepcopy(cached.get("result_clothing") or [])
                    for item in raw_items + final_items:
                        item["bbox"] = None
                        item["temporal_cache_from_frame"] = cached.get("frame")
                        item["source"] = "temporal_cache"
                    person["raw_clothing"] = raw_items
                    person["clothing"] = final_items
                    person["result_clothing"] = final_items
                    person["result_label"] = class_summary(final_items)
                    person["frame_label"] = person["result_label"]
                    person["stable_clothing"] = update_track_votes(vote_history, person["id"], final_items)
                    person["stable_label"] = person["stable_clothing"]["label"]
                    person["label"] = person["result_label"]
                    person["reid_profile"] = profile_from_person(person)
                    timings.add("clothing_temporal_cache_hit", 0.0, 1)
                    continue
                predict_metas.append(meta)
                predict_crops.append(meta["crop"])
            timings.add("clothing_cache_eval", now() - cache_eval_start, max(len(crop_meta), 1))

        if predict_crops:
            clothing_start = now()
            predictions = clothing.predict_batch_top_n(predict_crops, args.top_k, args.batch_size)
            add_yolo_speed_timings(timings, "clothing_yolo", clothing.last_results)
            timings.add("clothing_predict", now() - clothing_start, len(predict_crops))

            post_start = now()
            detailed_before = timings.seconds.get("detailed_color_analysis", 0.0)
            basic_color_before = timings.seconds.get("clothing_basic_color", 0.0)
            for meta, top_predictions in zip(predict_metas, predictions):
                processed = prediction_result(top_predictions, args.clothing_conf, "outfit")
                x_offset, y_offset = meta["offset"]
                person = meta["person"]
                raw_items = []
                final_items = []
                for source, target in (
                    (processed["raw_detections"], raw_items),
                    (processed["final_detections"], final_items),
                ):
                    for det in source:
                        item = dict(det)
                        if item.get("bbox"):
                            cx1, cy1, cx2, cy2 = item["bbox"]
                            item["bbox"] = clamp_bbox(
                                [cx1 + x_offset, cy1 + y_offset, cx2 + x_offset, cy2 + y_offset],
                                width,
                                height,
                            )
                        if target is final_items:
                            basic_color_start = now()
                            add_item_colors(frame, item, width, height)
                            timings.add("clothing_basic_color", now() - basic_color_start, 1)
                            apply_detailed_color_with_cache(
                                frame,
                                item,
                                width,
                                height,
                                int(person["id"]),
                                frame_index,
                                args.detailed_color_stride,
                                detailed_color_cache,
                                timings,
                                args.color_analysis_resize,
                            )
                        target.append(item)
                person["raw_clothing"] = raw_items
                person["clothing"] = final_items
                person["result_clothing"] = final_items
                person["result_label"] = class_summary(final_items)
                person["frame_label"] = person["result_label"]
                person["stable_clothing"] = update_track_votes(vote_history, person["id"], final_items)
                person["stable_label"] = person["stable_clothing"]["label"]
                person["label"] = person["result_label"]
                person["reid_profile"] = profile_from_person(person)
                clothing_temporal_cache[int(person["id"])] = {
                    "frame": frame_index,
                    "raw_clothing": copy.deepcopy(raw_items),
                    "result_clothing": copy.deepcopy(final_items),
                }
            detailed_delta = timings.seconds.get("detailed_color_analysis", 0.0) - detailed_before
            basic_color_delta = timings.seconds.get("clothing_basic_color", 0.0) - basic_color_before
            timings.add(
                "clothing_rule_postprocess",
                max(0.0, now() - post_start - detailed_delta - basic_color_delta),
                len(predict_crops),
            )

        person_rows_before_iou += len(persons)
        dedupe_start = now()
        persons = dedupe_persons_by_iou(persons, args.person_iou_dedupe_threshold)
        timings.add("iou_dedupe", now() - dedupe_start, 1)
        person_rows_after_iou += len(persons)
        suppressed_by_iou += max(0, person_rows_before_iou - person_rows_after_iou - suppressed_by_iou)

        image_start = now()
        visible_persons = []
        for person in persons:
            person.pop("_order", None)
            final_items = person.get("result_clothing") or person.get("clothing") or []
            should_save_images = args.save_local_images and (
                args.crop_save_interval <= 1 or frame_index % args.crop_save_interval == 0
            )
            if not final_items or not should_save_images:
                visible_persons.append(person)
                continue
            x1, y1, x2, y2 = person["bbox"]
            person_image_path = crop_path(image_root, "person", frame_index, int(person["id"]))
            save_jpeg(person_image_path, frame[y1:y2, x1:x2], args.jpeg_quality)
            person["image_path"] = str(person_image_path)
            for item_index, item in enumerate(final_items):
                bbox = item.get("bbox")
                if not bbox:
                    continue
                cx1, cy1, cx2, cy2 = bbox
                item_path = crop_path(image_root, "clothing", frame_index, int(person["id"]), f"{item_index}_{item.get('class', 'item')}")
                save_jpeg(item_path, frame[cy1:cy2, cx1:cx2], args.jpeg_quality)
                item["image_path"] = str(item_path)
            visible_persons.append(person)
        timings.add("image_save", now() - image_start, len(visible_persons))

        if args.disable_reid:
            for person in visible_persons:
                person["original_id"] = int(person["id"])
                person["reid_recovered"] = False
            timings.add("reid_disabled_step", 0.0, 1)
        else:
            reid_start = now()
            reid_events = online_reid.update(frame_index, visible_persons)
            timings.add("reid_online_step", now() - reid_start, 1)
            for event in reid_events:
                online_reid.remapped_person_rows += remap_existing_frames(frames, event)

        frame_row = {"frame": frame_index, "time": frame_index / fps, "persons": visible_persons}
        frames.append(frame_row)
        detections_count += len(visible_persons)
        streaming_db.enqueue(frame_row, frame_index)
        progress_reporter.maybe_report(
            frame_index,
            len(frames),
            frame_index + 1,
            streaming_db.summary_data,
            gpu_sampler.summary(),
            resource_sampler.summary(),
        )
        if frame_index % max(args.progress_report_interval_frames, 1) == 0:
            elapsed = sum(timings.seconds.values())
            json_job_reporter.update(
                frame_no=frame_index,
                frames_processed=len(frames),
                total_frames=max_frames,
                detections_count=detections_count,
                fps_output=round(len(frames) / max(elapsed, 0.0001), 4),
            )

    if not args.frame_prefetch:
        cap.release()
    real_db_summary = streaming_db.close()
    progress_reporter.maybe_report(
        frame_index,
        len(frames),
        max_frames,
        real_db_summary,
        gpu_sampler.summary(),
        resource_sampler.summary(),
    )
    json_job_reporter.update(
        frame_no=frame_index,
        frames_processed=len(frames),
        total_frames=max_frames,
        detections_count=detections_count,
        fps_output=round(len(frames) / max(sum(timings.seconds.values()), 0.0001), 4),
    )

    metadata = {
        "source_video": str(video_path),
        "fps": fps,
        "width": width,
        "height": height,
        "source_total_frames": total_frames,
        "processed_frames": len(frames),
        "realtime_display_frames": max_frames,
        "skipped_display_frames": max(0, max_frames - len(frames)),
        "processed_seconds": args.seconds,
        "frame_stride": args.frame_stride,
        "device": device,
        "detector_model": str(Path(args.detector).resolve()),
        "clothing_model": str(Path(args.model).resolve()),
        "person_conf": args.person_conf,
        "clothing_conf": args.clothing_conf,
        "person_iou_dedupe_threshold": args.person_iou_dedupe_threshold,
        "classes": TARGET_CLASSES,
        "class_colors": CLASS_COLORS,
        "class_display_order": CLASS_DISPLAY_ORDER,
        "vote_window": VOTE_WINDOW,
        "display_label_source": "result_clothing",
        "reid_color_feature_source": "detailed_colors_63",
        "detailed_color_stride": args.detailed_color_stride,
        "detailed_color_cache_mode": "analyze first observation for each track/slot, then every N observations; reuse cached detailed color between analyses",
        "result_rule": RESULT_RULE_TEXT,
        "hide_person_without_result_clothing": True,
        "person_iou_dedupe_applied": True,
        "person_rows_before_iou_dedupe": person_rows_before_iou,
        "person_rows_after_iou_dedupe": person_rows_after_iou,
        "person_rows_suppressed_by_iou_dedupe": person_rows_before_iou - person_rows_after_iou,
        "clips": clips,
        "frame_clip_start": args.frame_start,
        "frame_clip_end": args.frame_end,
        "images_dir": str(image_root),
        "sqlite_db": str(output_dir / "prediction_results.sqlite"),
        "real_db_save": real_db_summary,
        "gpu_monitor": gpu_sampler.summary(),
        "resource_monitor": resource_sampler.summary(),
        "fp16": args.fp16,
        "clothing_temporal_cache_frames": args.clothing_temporal_cache_frames,
        "color_analysis_resize": args.color_analysis_resize,
        "save_local_images": args.save_local_images,
        "json_only_output": args.json_only_output,
        "frame_prefetch": args.frame_prefetch,
        "frame_prefetch_size": args.frame_prefetch_size,
    }
    data = {"metadata": metadata, "frames": frames}

    metadata["viewer_reid"] = (
        {
            "enabled": False,
            "mode": "disabled",
            "recovered_tracks": 0,
            "remapped_person_rows": 0,
            "attempts": 0,
            "comparisons": 0,
            "events": [],
        }
        if args.disable_reid
        else online_reid.summary()
    )
    metadata["display_id_source"] = "viewer_reid_clothing_color"

    outfit_vote_start = now()
    apply_final_outfit_votes(data, args.final_outfit_lost_timeout_frames)
    timings.add("final_outfit_vote", now() - outfit_vote_start)

    original_ids = {
        int(person.get("original_id", person["id"]))
        for frame in data.get("frames", [])
        for person in frame.get("persons", [])
    }
    display_ids = {
        int(person["id"])
        for frame in data.get("frames", [])
        for person in frame.get("persons", [])
    }
    metadata["unique_person_ids_after_iou_dedupe"] = len(original_ids)
    metadata["display_ids_after_reid"] = len(display_ids)
    metadata["new_track_events"] = len(original_ids)

    baseline_path = Path(args.baseline_json).resolve() if args.baseline_json else Path()
    metadata["baseline_compare"] = load_baseline(baseline_path) if args.baseline_json else {}

    timings.add("total_without_file_db_write", now() - total_start)
    metadata["timings"] = timings.as_dict()
    metadata["pipeline_runtime_sec_excluding_file_db_write"] = round(timings.seconds["total_without_file_db_write"], 6)
    metadata["processed_output_fps_excluding_file_db_write"] = round(
        len(frames) / max(timings.seconds["total_without_file_db_write"], 0.0001),
        4,
    )
    metadata["realtime_display_fps_excluding_file_db_write"] = round(
        max_frames / max(timings.seconds["total_without_file_db_write"], 0.0001),
        4,
    )
    metadata["output_fps"] = metadata["realtime_display_fps_excluding_file_db_write"]

    file_start = now()
    if args.json_only_output:
        save_json_only(data, output_dir)
    else:
        save_outputs(data, output_dir, clips)
    write_summary(output_dir, data, timings)
    (output_dir / "timing_summary.json").write_text(json.dumps(timings.as_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    (output_dir / "viewer_reid_summary.json").write_text(
        json.dumps(metadata["viewer_reid"], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    timings.add("file_write", now() - file_start)

    if args.save_sqlite:
        db_start = now()
        save_sqlite(data, output_dir / "prediction_results.sqlite", timings)
        timings.add("sqlite_save", now() - db_start)

    if args.save_real_db and not args.stream_real_db:
        real_db_start = now()
        metadata["real_db_save"] = save_real_db(data, args, timings)
        timings.add("real_db_save", now() - real_db_start)

    metadata["timings"] = timings.as_dict()
    metadata["total_runtime_sec_including_exports"] = round(now() - total_start, 6)
    metadata["processed_output_fps_including_exports"] = round(len(frames) / max(now() - total_start, 0.0001), 4)
    metadata["realtime_display_fps_including_exports"] = round(max_frames / max(now() - total_start, 0.0001), 4)
    metadata["output_fps"] = metadata["realtime_display_fps_including_exports"]

    final_file_start = now()
    if args.json_only_output:
        save_json_only(data, output_dir)
    else:
        save_outputs(data, output_dir, clips)
    write_summary(output_dir, data, timings)
    (output_dir / "timing_summary.json").write_text(json.dumps(timings.as_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    timings.add("final_file_refresh", now() - final_file_start)

    json_job_reporter.finalize(
        "completed",
        {
            "camera_id": args.camera_id,
            "processed_frames": metadata["processed_frames"],
            "total_frames": metadata["realtime_display_frames"],
            "progress_pct": 100,
            "detections_count": detections_count,
            "fps_output": metadata["output_fps"],
            "recovered_tracks": metadata["viewer_reid"]["recovered_tracks"],
            "summary_path": str(output_dir / "summary.md"),
            "viewer_path": str(output_dir / "video_prediction_viewer.html"),
        },
    )

    return data, timings


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--video", required=True)
    parser.add_argument("--output-dir", default="track_result/bangkok_earthquake_predict_2min_yolo11s_pc045_full")
    parser.add_argument("--job-id", default="")
    parser.add_argument("--json-index", default="")
    parser.add_argument("--model", default="models/prepare_dataset.pt")
    parser.add_argument("--detector", default="yolo11s.pt")
    parser.add_argument("--seconds", type=float, default=120.0)
    parser.add_argument("--skip-clip-cut", action="store_true")
    parser.add_argument("--frame-start", type=int, default=1000)
    parser.add_argument("--frame-end", type=int, default=1999)
    parser.add_argument("--person-conf", type=float, default=0.45)
    parser.add_argument("--clothing-conf", type=float, default=0.25)
    parser.add_argument("--imgsz-person", type=int, default=640)
    parser.add_argument("--imgsz-clothing", type=int, default=224)
    parser.add_argument("--top-k", type=int, default=20)
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument("--frame-stride", type=int, default=1)
    parser.add_argument("--frame-prefetch", action="store_true")
    parser.add_argument("--frame-prefetch-size", type=int, default=16)
    parser.add_argument("--person-inference-mode", choices=["track", "predict"], default="track")
    parser.add_argument("--disable-clothing", action="store_true")
    parser.add_argument("--disable-reid", action="store_true")
    parser.add_argument("--max-source-frames", type=int, default=0)
    parser.add_argument("--detailed-color-stride", type=int, default=1)
    parser.add_argument("--color-analysis-resize", type=int, default=0)
    parser.add_argument("--clothing-temporal-cache-frames", type=int, default=0)
    parser.add_argument("--fp16", action="store_true")
    parser.add_argument("--save-local-images", action="store_true")
    parser.add_argument("--crop-save-interval", type=int, default=1)
    parser.add_argument("--save-sqlite", action="store_true")
    parser.add_argument("--json-only-output", action="store_true")
    parser.add_argument("--person-iou-dedupe-threshold", type=float, default=0.50)
    parser.add_argument("--reid-color-threshold", type=float, default=0.70)
    parser.add_argument("--reid-confirmation-frames", type=int, default=30)
    parser.add_argument("--reid-min-hits", type=int, default=10)
    parser.add_argument("--reid-max-gap-frames", type=int, default=45)
    parser.add_argument("--reid-aggregate-slot-history", type=int, default=10)
    parser.add_argument("--final-outfit-lost-timeout-frames", type=int, default=30)
    parser.add_argument("--jpeg-quality", type=int, default=85)
    parser.add_argument("--save-real-db", action="store_true")
    parser.add_argument("--save-real-db-images", action="store_true")
    parser.add_argument("--stream-real-db", action="store_true")
    parser.add_argument("--real-db-flush-frame-interval", type=int, default=60)
    parser.add_argument("--camera-id", default="CAM-TEST")
    parser.add_argument("--db-video-label", default="bangkok_earthquake_realtime_reid_test")
    parser.add_argument("--monitor-gpu", action="store_true")
    parser.add_argument("--gpu-sample-interval-frames", type=int, default=30)
    parser.add_argument("--monitor-resources", action="store_true")
    parser.add_argument("--resource-sample-interval-frames", type=int, default=30)
    parser.add_argument("--baseline-json", default="track_result/bangkok_earthquake_predict_2min_yolo11s/prediction_results.json")
    parser.add_argument("--log-every", type=int, default=100)
    parser.add_argument("--progress-report-interval-frames", type=int, default=100)
    parser.add_argument("--device", default="auto")
    args = parser.parse_args()

    if get_storage_mode() == "json" and not args.job_id:
        args.save_real_db = False
        args.save_real_db_images = False
        args.stream_real_db = False

    try:
        data, timings = predict_full(args)
    except Exception as exc:
        if args.job_id:
            output_dir = (WORKSPACE / args.output_dir).resolve()
            JsonJobReporter(args, output_dir, Path(args.video).resolve()).finalize("failed", error_message=str(exc))
        raise
    output_dir = (WORKSPACE / args.output_dir).resolve()
    print(
        json.dumps(
            {
                "output_dir": str(output_dir),
                "viewer": str(output_dir / "video_prediction_viewer.html"),
                "summary": str(output_dir / "summary.md"),
                "sqlite_db": data["metadata"]["sqlite_db"],
                "processed_frames": data["metadata"]["processed_frames"],
                "person_rows_after_iou_dedupe": data["metadata"]["person_rows_after_iou_dedupe"],
                "new_track_events": data["metadata"]["new_track_events"],
                "recovered_tracks": data["metadata"]["viewer_reid"]["recovered_tracks"],
                "output_fps": data["metadata"]["output_fps"],
                "timings": timings.as_dict(),
            },
            ensure_ascii=False,
            indent=2,
        ),
        flush=True,
    )


if __name__ == "__main__":
    main()
