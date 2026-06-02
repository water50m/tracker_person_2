"""
pipeline_shared.py — shared helpers used by both predict_video_full_pipeline.py
and the streaming API (video_controller.py).

Importing this file is safe: no top-level model loading, no argparse, no
heavy one-time startup code.
"""
from __future__ import annotations

import time
from collections import Counter, defaultdict
from types import SimpleNamespace
from typing import Any

import cv2

from apply_viewer_reid import color_distribution, compare_segment, profile_from_person  # noqa: F401
from predict_video_clothing_viewer import (
    CLASS_DISPLAY_ORDER,
    clamp_bbox,
    id_color,  # noqa: F401
)


def clothing_slot(class_name: str) -> str | None:
    if class_name in {"short_sleeve", "long_sleeve"}:
        return "top"
    if class_name == "dress":
        return "dress"
    if class_name in {"shorts", "trousers", "skirt"}:
        return "bottom"
    return None
from src.ai.clothing_predictor import TARGET_CLASSES  # noqa: F401 (re-exported for pipeline use)
from src.ai.color_system import (
    analyze_detailed_colors,
    get_color_groups,
    get_primary_color_group,
    get_primary_detailed_color,
)
from src.config_loader import get_color_remove_background as _get_color_remove_background


# ── Timing helper (no-op version safe for streaming) ────────────────────────

class DummyTimings:
    """Drop-in replacement for the Timings class when timing is not needed."""
    def add(self, *args: Any, **kwargs: Any) -> None:
        pass


# ── class_summary ────────────────────────────────────────────────────────────

def class_summary(detections: list[dict[str, Any]]) -> str:
    classes: list[str] = []
    seen: set[str] = set()
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


# ── Color analysis helpers ────────────────────────────────────────────────────

def resized_for_color(crop, max_size: int):
    if not max_size or max_size <= 0 or crop is None or crop.size == 0:
        return crop
    h, w = crop.shape[:2]
    longest = max(h, w)
    if longest <= max_size:
        return crop
    scale = max_size / float(longest)
    return cv2.resize(
        crop,
        (max(1, int(w * scale)), max(1, int(h * scale))),
        interpolation=cv2.INTER_AREA,
    )


def add_item_colors(frame, item: dict[str, Any], width: int, height: int) -> None:
    bbox = item.get("bbox")
    if not bbox:
        item["reid_colors"] = {}
        return
    x1, y1, x2, y2 = clamp_bbox([int(v) for v in bbox], width, height) or [0, 0, 0, 0]
    item["reid_colors"] = color_distribution(frame[y1:y2, x1:x2])


def add_item_detailed_colors(
    frame, item: dict[str, Any], width: int, height: int, max_size: int = 0,
    remove_bg: bool | None = None,
) -> None:
    bbox = item.get("bbox")
    if not bbox:
        item["detailed_colors"] = {}
        item["color_groups"] = {}
        item["primary_detailed_color"] = "unknown"
        item["primary_color_group"] = "unknown"
        return
    if remove_bg is None:
        remove_bg = _get_color_remove_background()
    x1, y1, x2, y2 = clamp_bbox([int(v) for v in bbox], width, height) or [0, 0, 0, 0]
    detailed_colors = analyze_detailed_colors(
        resized_for_color(frame[y1:y2, x1:x2], max_size), remove_bg=remove_bg
    )
    # keep top-3 colors by percentage (same rule as old video_controller.py)
    detailed_colors = dict(sorted(detailed_colors.items(), key=lambda x: x[1], reverse=True)[:3])
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
    timings: Any = None,
    color_resize: int = 0,
    remove_bg: bool | None = None,
) -> None:
    if timings is None:
        timings = DummyTimings()
    if remove_bg is None:
        remove_bg = _get_color_remove_background()

    slot = clothing_slot(item.get("class", ""))
    if slot is None:
        add_item_detailed_colors(frame, item, width, height, color_resize, remove_bg=remove_bg)
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
        t0 = time.perf_counter()
        add_item_detailed_colors(frame, item, width, height, color_resize, remove_bg=remove_bg)
        timings.add("detailed_color_analysis", time.perf_counter() - t0, 1)
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


# ── OnlineReID ────────────────────────────────────────────────────────────────

class OnlineReID:
    def __init__(self, args: Any) -> None:
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
            self.observations_by_id[byte_id].append({
                "frame": frame_no,
                "profile": person.get("reid_profile", {}),
                "bbox": person.get("bbox", []),
            })

        for new_id in new_ids:
            start = self.first_frame[new_id]
            candidates = [
                old_id
                for old_id in self.finished_ids
                if old_id != new_id
                and 0 < start - self.last_frame.get(old_id, start) <= self.args.reid_max_gap_frames
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
            "recovered_tracks": len(self.recovered_events),
            "remapped_person_rows": self.remapped_person_rows,
            "attempts": self.attempts,
            "comparisons": self.comparisons,
            "events": self.recovered_events,
        }
