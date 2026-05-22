from __future__ import annotations

import csv
import json
import math
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable


def read_records(path: str | Path) -> list[dict[str, Any]]:
    """Read CSV, JSON, or JSONL records."""
    path = Path(path)
    suffix = path.suffix.lower()
    if suffix == ".csv":
        with path.open("r", encoding="utf-8-sig", newline="") as f:
            return [dict(row) for row in csv.DictReader(f)]
    if suffix == ".jsonl":
        with path.open("r", encoding="utf-8") as f:
            return [json.loads(line) for line in f if line.strip()]
    if suffix == ".json":
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            for key in ("records", "items", "detections", "results"):
                if isinstance(data.get(key), list):
                    return data[key]
        raise ValueError(f"JSON file must contain a list or records/items/detections/results: {path}")
    raise ValueError(f"Unsupported record format: {path}")


def write_json(path: str | Path, data: dict[str, Any]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def safe_int(value: Any, default: int = 0) -> int:
    try:
        if value is None or value == "":
            return default
        return int(float(value))
    except (TypeError, ValueError):
        return default


def bbox_xyxy(record: dict[str, Any]) -> tuple[float, float, float, float] | None:
    """Parse bbox from x1/y1/x2/y2 or x/y/w/h fields."""
    if all(k in record for k in ("x1", "y1", "x2", "y2")):
        return (
            safe_float(record["x1"]),
            safe_float(record["y1"]),
            safe_float(record["x2"]),
            safe_float(record["y2"]),
        )
    if all(k in record for k in ("x", "y", "w", "h")):
        x = safe_float(record["x"])
        y = safe_float(record["y"])
        w = safe_float(record["w"])
        h = safe_float(record["h"])
        return (x, y, x + w, y + h)
    if "bbox" in record:
        bbox = record["bbox"]
        if isinstance(bbox, str):
            bbox = [safe_float(v) for v in bbox.replace(";", ",").split(",") if v.strip()]
        if isinstance(bbox, (list, tuple)) and len(bbox) >= 4:
            x, y, a, b = map(float, bbox[:4])
            fmt = str(record.get("bbox_format", "")).lower()
            if fmt in {"xywh", "coco"}:
                return (x, y, x + a, y + b)
            return (x, y, a, b)
    return None


def iou(a: tuple[float, float, float, float], b: tuple[float, float, float, float]) -> float:
    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b
    ix1 = max(ax1, bx1)
    iy1 = max(ay1, by1)
    ix2 = min(ax2, bx2)
    iy2 = min(ay2, by2)
    iw = max(0.0, ix2 - ix1)
    ih = max(0.0, iy2 - iy1)
    inter = iw * ih
    area_a = max(0.0, ax2 - ax1) * max(0.0, ay2 - ay1)
    area_b = max(0.0, bx2 - bx1) * max(0.0, by2 - by1)
    union = area_a + area_b - inter
    return inter / union if union > 0 else 0.0


def classification_report(
    y_true: Iterable[str],
    y_pred: Iterable[str],
    labels: Iterable[str] | None = None,
) -> dict[str, Any]:
    y_true = [str(v) for v in y_true]
    y_pred = [str(v) for v in y_pred]
    label_list = sorted(set(labels or []) | set(y_true) | set(y_pred))
    per_class: dict[str, dict[str, float]] = {}

    for label in label_list:
        tp = sum(t == label and p == label for t, p in zip(y_true, y_pred))
        fp = sum(t != label and p == label for t, p in zip(y_true, y_pred))
        fn = sum(t == label and p != label for t, p in zip(y_true, y_pred))
        support = sum(t == label for t in y_true)
        precision = tp / (tp + fp) if tp + fp else 0.0
        recall = tp / (tp + fn) if tp + fn else 0.0
        f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
        per_class[label] = {
            "precision": precision,
            "recall": recall,
            "f1": f1,
            "support": support,
            "tp": tp,
            "fp": fp,
            "fn": fn,
        }

    total = len(y_true)
    accuracy = sum(t == p for t, p in zip(y_true, y_pred)) / total if total else 0.0
    macro_f1 = sum(v["f1"] for v in per_class.values()) / len(per_class) if per_class else 0.0
    confusion = defaultdict(Counter)
    for true, pred in zip(y_true, y_pred):
        confusion[true][pred] += 1

    return {
        "total": total,
        "accuracy": accuracy,
        "macro_f1": macro_f1,
        "per_class": per_class,
        "confusion_matrix": {k: dict(v) for k, v in confusion.items()},
    }


def detection_average_precision(matches: list[tuple[float, bool]], total_gt: int) -> float:
    """11-point interpolated AP from (confidence, is_true_positive)."""
    if total_gt <= 0:
        return 0.0
    matches = sorted(matches, key=lambda x: x[0], reverse=True)
    tp = 0
    fp = 0
    points: list[tuple[float, float]] = []
    for _, is_tp in matches:
        if is_tp:
            tp += 1
        else:
            fp += 1
        recall = tp / total_gt
        precision = tp / (tp + fp) if tp + fp else 0.0
        points.append((recall, precision))
    ap = 0.0
    for threshold in [i / 10 for i in range(11)]:
        precisions = [p for r, p in points if r >= threshold]
        ap += max(precisions) if precisions else 0.0
    return ap / 11


def mot_identity_metrics(
    gt_records: list[dict[str, Any]],
    pred_records: list[dict[str, Any]],
    iou_threshold: float = 0.5,
) -> dict[str, Any]:
    """Compute ID continuity metrics from MOT-like frame/id/bbox records."""
    gt_by_frame = defaultdict(list)
    pred_by_frame = defaultdict(list)
    for rec in gt_records:
        box = bbox_xyxy(rec)
        if box is None:
            continue
        gt_by_frame[safe_int(rec.get("frame"))].append({**rec, "_bbox": box})
    for rec in pred_records:
        box = bbox_xyxy(rec)
        if box is None:
            continue
        pred_by_frame[safe_int(rec.get("frame"))].append({**rec, "_bbox": box})

    identity_to_pred_ids: dict[str, list[str]] = defaultdict(list)
    identity_last_pred: dict[str, str] = {}
    identity_switches = 0
    matched = 0
    missed = 0
    false_positive = 0
    matched_rows = []

    for frame in sorted(set(gt_by_frame) | set(pred_by_frame)):
        gts = gt_by_frame.get(frame, [])
        preds = pred_by_frame.get(frame, [])
        used_preds = set()
        for gt in gts:
            gt_box = gt["_bbox"]
            best_idx = None
            best_iou = 0.0
            for idx, pred in enumerate(preds):
                if idx in used_preds:
                    continue
                score = iou(gt_box, pred["_bbox"])
                if score > best_iou:
                    best_iou = score
                    best_idx = idx
            if best_idx is None or best_iou < iou_threshold:
                missed += 1
                continue

            used_preds.add(best_idx)
            pred = preds[best_idx]
            matched += 1
            identity = str(gt.get("identity") or gt.get("gt_id") or gt.get("id"))
            pred_id = str(pred.get("track_id") or pred.get("id"))
            if identity_last_pred.get(identity) not in (None, pred_id):
                identity_switches += 1
            identity_last_pred[identity] = pred_id
            identity_to_pred_ids[identity].append(pred_id)
            matched_rows.append({
                "frame": frame,
                "identity": identity,
                "pred_track_id": pred_id,
                "iou": best_iou,
            })
        false_positive += max(0, len(preds) - len(used_preds))

    unique_pred_ids_per_identity = {
        identity: sorted(set(ids))
        for identity, ids in identity_to_pred_ids.items()
    }
    fragmentations = sum(max(0, len(ids) - 1) for ids in unique_pred_ids_per_identity.values())
    total_gt = sum(len(v) for v in gt_by_frame.values())

    return {
        "total_gt": total_gt,
        "matched": matched,
        "missed": missed,
        "false_positive": false_positive,
        "match_rate": matched / total_gt if total_gt else 0.0,
        "id_switches": identity_switches,
        "fragmentations": fragmentations,
        "unique_pred_ids_total": len({row["pred_track_id"] for row in matched_rows}),
        "unique_pred_ids_per_identity": unique_pred_ids_per_identity,
        "matched_rows": matched_rows,
    }


def tracking_proxy_metrics(records: list[dict[str, Any]]) -> dict[str, Any]:
    track_frames = defaultdict(list)
    for rec in records:
        track_id = str(rec.get("track_id") or rec.get("id"))
        if not track_id or track_id == "None":
            continue
        track_frames[track_id].append(safe_int(rec.get("frame")))

    lengths = [len(frames) for frames in track_frames.values()]
    return {
        "detections": len(records),
        "unique_track_ids": len(track_frames),
        "avg_track_length": sum(lengths) / len(lengths) if lengths else 0.0,
        "max_track_length": max(lengths) if lengths else 0,
        "min_track_length": min(lengths) if lengths else 0,
        "track_lengths": {tid: len(frames) for tid, frames in track_frames.items()},
    }


def mean(values: Iterable[float]) -> float:
    values = list(values)
    return sum(values) / len(values) if values else 0.0


def percentile(values: Iterable[float], pct: float) -> float:
    values = sorted(values)
    if not values:
        return 0.0
    if len(values) == 1:
        return values[0]
    rank = (len(values) - 1) * pct
    lo = math.floor(rank)
    hi = math.ceil(rank)
    if lo == hi:
        return values[lo]
    return values[lo] * (hi - rank) + values[hi] * (rank - lo)
