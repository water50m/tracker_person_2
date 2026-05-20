from __future__ import annotations

import argparse
import json
import math
import os
import sqlite3
import sys
import time
from collections import Counter, defaultdict, deque
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import cv2
import torch

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

from apply_viewer_reid import apply_reid, color_distribution, profile_from_person
from evaluate_clothing_model import TARGET_CLASSES, YoloPredictor, prediction_result
from src.ai.color_system import (
    analyze_detailed_colors,
    get_color_groups,
    get_primary_color_group,
    get_primary_detailed_color,
)
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

    def strength(item: dict[str, Any] | None) -> tuple[int, float]:
        if not item:
            return (0, 0.0)
        return (int(item.get("votes") or 0), float(item.get("avg_confidence") or 0.0))

    if dress and strength(dress) >= max(strength(top), strength(bottom)):
        companion = max([item for item in (top, bottom) if item], key=strength, default=None)
        selected = [dress]
        if companion:
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
                    "slot_votes": {"top": [], "dress": [], "bottom": []},
                    "original_ids": set(),
                },
            )
            track["first_frame"] = min(track["first_frame"], frame_no)
            track["last_frame"] = max(track["last_frame"], frame_no)
            track["observations"] += 1
            track["original_ids"].add(int(person.get("original_id", person["id"])))
            for item in person.get("result_clothing") or person.get("clothing") or []:
                slot = clothing_slot(item.get("class", ""))
                if not slot:
                    continue
                track["slot_votes"][slot].append(
                    {
                        "frame": frame_no,
                        "class": item.get("class"),
                        "confidence": float(item.get("confidence") or 0.0),
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
        "track_count": len(final_by_id),
        "tracks": {str(track_id): final for track_id, final in sorted(final_by_id.items())},
    }
    data.setdefault("metadata", {})["final_outfit_votes"] = summary
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


def add_item_detailed_colors(frame, item: dict[str, Any], width: int, height: int) -> None:
    bbox = item.get("bbox")
    if not bbox:
        item["detailed_colors"] = {}
        item["color_groups"] = {}
        item["primary_detailed_color"] = "unknown"
        item["primary_color_group"] = "unknown"
        return
    x1, y1, x2, y2 = clamp_bbox([int(v) for v in bbox], width, height) or [0, 0, 0, 0]
    detailed_colors = analyze_detailed_colors(frame[y1:y2, x1:x2])
    color_groups = get_color_groups(detailed_colors)
    item["detailed_colors"] = detailed_colors
    item["color_groups"] = color_groups
    item["primary_detailed_color"] = get_primary_detailed_color(detailed_colors)
    item["primary_color_group"] = get_primary_color_group(color_groups)


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
        f"- Output FPS: `{metadata['output_fps']}`",
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

    lines.extend(["", "## Timings"])
    for name, row in timings.as_dict().items():
        lines.append(f"- {name}: `{row['seconds']}` sec, count `{row['count']}`, avg `{row['avg_ms']}` ms")

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

    model_start = now()
    detector = YOLO(str(Path(args.detector).resolve()))
    detector.to(device)
    clothing = YoloPredictor(Path(args.model).resolve(), device=device, imgsz=args.imgsz_clothing, conf=args.clothing_conf)
    timings.add("model_load", now() - model_start)

    frames: list[dict[str, Any]] = []
    vote_history: dict[int, dict[str, deque[str]]] = defaultdict(dict)
    person_rows_before_iou = 0
    person_rows_after_iou = 0
    suppressed_by_iou = 0

    frame_index = -1
    while frame_index + 1 < max_frames:
        ok, frame = cap.read()
        if not ok:
            break
        frame_index += 1
        if frame_index % max(args.frame_stride, 1) != 0:
            continue
        if frame_index % args.log_every == 0:
            print(f"[full-predict] frame {frame_index}/{max_frames} ({frame_index / fps:.2f}s)", flush=True)

        detect_start = now()
        result = detector.track(
            frame,
            persist=True,
            tracker="bytetrack.yaml",
            classes=[0],
            conf=args.person_conf,
            imgsz=args.imgsz_person,
            device=device,
            verbose=False,
        )[0]
        timings.add("person_detect_track", now() - detect_start)

        persons: list[dict[str, Any]] = []
        crops: list[Any] = []
        crop_meta: list[dict[str, Any]] = []
        boxes = getattr(result, "boxes", None)
        if boxes is not None and len(boxes) > 0:
            ids = boxes.id
            if ids is None:
                timings.add("untracked_person_boxes_skipped", 0.0, len(boxes))
                boxes = []
            for det_idx, box in enumerate(boxes):
                bbox = clamp_bbox([int(v) for v in box.xyxy[0].tolist()], width, height)
                if bbox is None:
                    continue
                x1, y1, x2, y2 = bbox
                crop = frame[y1:y2, x1:x2]
                if crop.size == 0:
                    continue
                track_id = int(ids[det_idx].item())
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
                crops.append(crop)
                crop_meta.append({"person": person, "offset": (x1, y1), "crop": crop})

        if crops:
            clothing_start = now()
            predictions = clothing.predict_batch_top_n(crops, args.top_k, args.batch_size)
            timings.add("clothing_predict", now() - clothing_start, len(crops))

            post_start = now()
            for meta, top_predictions in zip(crop_meta, predictions):
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
                            add_item_colors(frame, item, width, height)
                            detail_start = now()
                            add_item_detailed_colors(frame, item, width, height)
                            timings.add("detailed_color_analysis", now() - detail_start, 1)
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
            timings.add("clothing_postprocess", now() - post_start, len(crops))

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
            if not final_items:
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
        frames.append({"frame": frame_index, "time": frame_index / fps, "persons": visible_persons})

    cap.release()

    metadata = {
        "source_video": str(video_path),
        "fps": fps,
        "width": width,
        "height": height,
        "source_total_frames": total_frames,
        "processed_frames": len(frames),
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
        "result_rule": "max 2 objects: dress/top/bottom groups; top+top and bottom+bottom impossible; dress companion only trousers or top>=0.76; skirt confidence x3 against dress",
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
    }
    data = {"metadata": metadata, "frames": frames}

    reid_start = now()
    reid_args = SimpleNamespace(
        color_threshold=args.reid_color_threshold,
        confirmation_frames=args.reid_confirmation_frames,
        min_hits=args.reid_min_hits,
        max_gap_frames=args.reid_max_gap_frames,
        aggregate_slot_history=args.reid_aggregate_slot_history,
    )
    metadata["viewer_reid"] = apply_reid(data, reid_args)
    metadata["display_id_source"] = "viewer_reid_clothing_color"
    timings.add("reid_apply", now() - reid_start)

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
    metadata["output_fps"] = round(len(frames) / max(timings.seconds["total_without_file_db_write"], 0.0001), 4)

    file_start = now()
    save_outputs(data, output_dir, clips)
    write_summary(output_dir, data, timings)
    (output_dir / "timing_summary.json").write_text(json.dumps(timings.as_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    (output_dir / "viewer_reid_summary.json").write_text(
        json.dumps(metadata["viewer_reid"], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    timings.add("file_write", now() - file_start)

    db_start = now()
    save_sqlite(data, output_dir / "prediction_results.sqlite", timings)
    timings.add("sqlite_save", now() - db_start)
    metadata["timings"] = timings.as_dict()
    metadata["output_fps"] = round(len(frames) / max(now() - total_start, 0.0001), 4)

    final_file_start = now()
    save_outputs(data, output_dir, clips)
    write_summary(output_dir, data, timings)
    (output_dir / "timing_summary.json").write_text(json.dumps(timings.as_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    timings.add("final_file_refresh", now() - final_file_start)

    return data, timings


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--video", required=True)
    parser.add_argument("--output-dir", default="track_result/bangkok_earthquake_predict_2min_yolo11s_pc045_full")
    parser.add_argument("--model", default="models/prepare_dataset.pt")
    parser.add_argument("--detector", default="yolo11s.pt")
    parser.add_argument("--seconds", type=float, default=120.0)
    parser.add_argument("--frame-start", type=int, default=1000)
    parser.add_argument("--frame-end", type=int, default=1999)
    parser.add_argument("--person-conf", type=float, default=0.45)
    parser.add_argument("--clothing-conf", type=float, default=0.25)
    parser.add_argument("--imgsz-person", type=int, default=640)
    parser.add_argument("--imgsz-clothing", type=int, default=224)
    parser.add_argument("--top-k", type=int, default=20)
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument("--frame-stride", type=int, default=1)
    parser.add_argument("--person-iou-dedupe-threshold", type=float, default=0.50)
    parser.add_argument("--reid-color-threshold", type=float, default=0.70)
    parser.add_argument("--reid-confirmation-frames", type=int, default=30)
    parser.add_argument("--reid-min-hits", type=int, default=10)
    parser.add_argument("--reid-max-gap-frames", type=int, default=45)
    parser.add_argument("--reid-aggregate-slot-history", type=int, default=10)
    parser.add_argument("--final-outfit-lost-timeout-frames", type=int, default=30)
    parser.add_argument("--jpeg-quality", type=int, default=85)
    parser.add_argument("--baseline-json", default="track_result/bangkok_earthquake_predict_2min_yolo11s/prediction_results.json")
    parser.add_argument("--log-every", type=int, default=100)
    parser.add_argument("--device", default="auto")
    args = parser.parse_args()

    data, timings = predict_full(args)
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
