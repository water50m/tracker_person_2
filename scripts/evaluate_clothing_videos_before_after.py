from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path
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

from evaluate_clothing_model import (  # noqa: E402
    TARGET_CLASSES,
    YoloPredictor,
    detect_person_boxes,
    prediction_result,
    safe_div,
)


VIDEO_SPECS = [
    {
        "name": "shorttop_redskirt",
        "path": r"C:\Users\pmach\Downloads\drive-download-20260521T101829Z-3-001\shorttop_redskrit.mp4",
        "expected": ["short_sleeve", "skirt"],
        "input_mode": "full_frame",
        "start_frame": 0,
        "end_frame": -1,
    },
    {
        "name": "bluedress",
        "path": r"C:\Users\pmach\Downloads\drive-download-20260521T101829Z-3-001\bluedress.mp4",
        "expected": ["short_sleeve", "skirt"],
        "input_mode": "full_frame",
        "start_frame": 0,
        "end_frame": -1,
    },
    {
        "name": "reddress",
        "path": r"C:\Users\pmach\Downloads\drive-download-20260521T101829Z-3-001\reddress.mp4",
        "expected": ["dress"],
        "input_mode": "full_frame",
        "start_frame": 0,
        "end_frame": -1,
    },
    {
        "name": "whitedress",
        "path": r"C:\Users\pmach\Downloads\drive-download-20260521T101829Z-3-001\whitedress.mp4",
        "expected": ["dress"],
        "input_mode": "full_frame",
        "start_frame": 0,
        "end_frame": -1,
    },
    {
        "name": "dress_1080p",
        "path": r"C:\Users\pmach\Downloads\drive-download-20260521T101829Z-3-001\dress.mp4",
        "expected": ["dress"],
        "input_mode": "person_detector",
        "start_frame": 0,
        "end_frame": -1,
    },
    {
        "name": "redskirt_1080p",
        "path": r"C:\Users\pmach\Downloads\drive-download-20260521T101829Z-3-001\redskirt.mp4",
        "expected": ["short_sleeve", "skirt"],
        "input_mode": "person_detector",
        "start_frame": 0,
        "end_frame": -1,
    },
    {
        "name": "cam01_long_sleeve_trousers_f1000_1999",
        "path": r"E:\ALL_CODE\my-project\temp_videos\CAM-01_4p-c0-new.mp4",
        "expected": ["long_sleeve", "trousers"],
        "input_mode": "person_detector",
        "start_frame": 1000,
        "end_frame": 1999,
    },
    {
        "name": "combined_short_sleeve_shorts",
        "path": r"E:\ALL_CODE\my-project\tracked_results\combined_results\combined_target_ids.mp4",
        "expected": ["short_sleeve", "shorts"],
        "input_mode": "person_detector",
        "start_frame": 0,
        "end_frame": -1,
    },
]

MODES = {
    "before_raw": "raw",
    "after_tuned": "outfit",
}


def pct(value: float) -> str:
    return f"{value * 100:.2f}%"


def fmt_seconds(value: float) -> str:
    return f"{value:.3f}s"


def json_text(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({name: row.get(name, "") for name in fieldnames})


def bbox_from_frame(frame: Any) -> tuple[int, int, int, int, float]:
    height, width = frame.shape[:2]
    return (0, 0, width, height, 1.0)


def result_for_mode(top_predictions: list[dict[str, Any]], threshold: float, postprocess_mode: str) -> dict[str, Any]:
    result = prediction_result(top_predictions, threshold, postprocess_mode)
    classes = set(result["classes"])
    confidence_map: dict[str, float] = {}
    for det in result["final_detections"]:
        label = det["class"]
        confidence_map[label] = max(confidence_map.get(label, 0.0), float(det.get("confidence", 0.0)))
    return {
        "classes": classes,
        "confidence_map": confidence_map,
        "raw_detections": result["raw_detections"],
        "final_detections": result["final_detections"],
    }


def predictions_in_frame_coords(
    top_predictions: list[dict[str, Any]],
    person_bbox: tuple[int, int, int, int, float],
) -> list[dict[str, Any]]:
    x_offset, y_offset, x_max, y_max, _person_confidence = person_bbox
    adjusted = []
    for det in top_predictions:
        item = dict(det)
        bbox = det.get("bbox")
        if isinstance(bbox, (list, tuple)) and len(bbox) == 4:
            x1, y1, x2, y2 = bbox
            item["bbox"] = [
                max(x_offset, min(x_max, int(round(float(x1) + x_offset)))),
                max(y_offset, min(y_max, int(round(float(y1) + y_offset)))),
                max(x_offset, min(x_max, int(round(float(x2) + x_offset)))),
                max(y_offset, min(y_max, int(round(float(y2) + y_offset)))),
            ]
        adjusted.append(item)
    return adjusted


def add_metrics_row(
    mode_rows: list[dict[str, Any]],
    detail_rows: list[dict[str, Any]],
    video_name: str,
    frame_index: int,
    time_sec: float,
    detection_index: int,
    bbox: tuple[int, int, int, int, float],
    expected: set[str],
    top_predictions: list[dict[str, Any]],
    threshold: float,
) -> None:
    x1, y1, x2, y2, person_conf = bbox
    frame_predictions = predictions_in_frame_coords(top_predictions, bbox)
    for mode_name, postprocess_mode in MODES.items():
        result = result_for_mode(frame_predictions, threshold, postprocess_mode)
        predicted = result["classes"]
        correct = expected & predicted
        missing = expected - predicted
        extra = predicted - expected
        mode_rows.append(
            {
                "video": video_name,
                "mode": mode_name,
                "frame": frame_index,
                "time_sec": time_sec,
                "detection_index": detection_index,
                "person_bbox": [x1, y1, x2, y2],
                "person_confidence": person_conf,
                "expected_classes": sorted(expected),
                "predicted_classes": sorted(predicted),
                "correct_labels": sorted(correct),
                "missing_labels": sorted(missing),
                "extra_labels": sorted(extra),
                "exact_match": not missing and not extra,
                "partial_match": bool(correct),
                "confidence_map": result["confidence_map"],
            }
        )
        detail_rows.append(
            {
                "video": video_name,
                "mode": mode_name,
                "frame": frame_index,
                "time_sec": f"{time_sec:.4f}",
                "detection_index": detection_index,
                "person_bbox": json_text([x1, y1, x2, y2]),
                "person_confidence": f"{person_conf:.6f}",
                "expected_classes": "|".join(sorted(expected)),
                "predicted_classes": "|".join(sorted(predicted)),
                "correct_labels": "|".join(sorted(correct)),
                "missing_labels": "|".join(sorted(missing)),
                "extra_labels": "|".join(sorted(extra)),
                "exact_match": str(not missing and not extra),
                "partial_match": str(bool(correct)),
                "confidence_map_json": json_text(result["confidence_map"]),
                "raw_detections_json": json_text(result["raw_detections"]),
                "final_detections_json": json_text(result["final_detections"]),
                "top_predictions_json": json_text(frame_predictions),
            }
        )


def summarize_rows(rows: list[dict[str, Any]], expected_counter: Counter[str]) -> dict[str, Any]:
    total = len(rows)
    exact = sum(1 for row in rows if row["exact_match"])
    partial = sum(1 for row in rows if row["partial_match"])
    label_tp = 0
    label_fp = 0
    label_fn = 0
    pred_counter: Counter[str] = Counter()
    missing_counter: Counter[str] = Counter()
    extra_counter: Counter[str] = Counter()
    conf_sum: defaultdict[str, float] = defaultdict(float)
    conf_count: Counter[str] = Counter()

    for row in rows:
        expected = set(row["expected_classes"])
        predicted = set(row["predicted_classes"])
        confidence_map = row["confidence_map"]
        correct = expected & predicted
        missing = expected - predicted
        extra = predicted - expected
        label_tp += len(correct)
        label_fp += len(extra)
        label_fn += len(missing)
        pred_counter.update(predicted)
        missing_counter.update(missing)
        extra_counter.update(extra)
        for label, confidence in confidence_map.items():
            conf_sum[label] += float(confidence)
            conf_count[label] += 1

    precision = safe_div(label_tp, label_tp + label_fp)
    recall = safe_div(label_tp, label_tp + label_fn)
    f1 = safe_div(2 * precision * recall, precision + recall)
    per_class = {}
    for label in TARGET_CLASSES:
        tp = sum(label in row["expected_classes"] and label in row["predicted_classes"] for row in rows)
        fp = sum(label not in row["expected_classes"] and label in row["predicted_classes"] for row in rows)
        fn = sum(label in row["expected_classes"] and label not in row["predicted_classes"] for row in rows)
        p = safe_div(tp, tp + fp)
        r = safe_div(tp, tp + fn)
        per_class[label] = {
            "support": expected_counter[label],
            "predicted": pred_counter[label],
            "tp": tp,
            "fp": fp,
            "fn": fn,
            "precision": p,
            "recall": r,
            "f1": safe_div(2 * p * r, p + r),
            "avg_confidence_when_predicted": safe_div(conf_sum[label], conf_count[label]),
        }

    return {
        "total_predictions": total,
        "exact_match": exact,
        "partial_match": partial,
        "exact_match_rate": safe_div(exact, total),
        "partial_match_rate": safe_div(partial, total),
        "label_true_positive": label_tp,
        "label_false_positive": label_fp,
        "label_false_negative": label_fn,
        "label_precision": precision,
        "label_recall": recall,
        "label_f1": f1,
        "predictions_by_class": dict(pred_counter),
        "missing_by_class": dict(missing_counter),
        "extra_by_class": dict(extra_counter),
        "per_class": per_class,
    }


def evaluate_one_video(
    spec: dict[str, Any],
    output_dir: Path,
    predictor: YoloPredictor,
    detector: YOLO,
    device: str,
    args: argparse.Namespace,
) -> dict[str, Any]:
    video_path = Path(spec["path"])
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        return {"name": spec["name"], "status": "failed_to_open", "path": str(video_path)}

    fps = float(cap.get(cv2.CAP_PROP_FPS) or 0.0)
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    start_frame = int(spec.get("start_frame", 0))
    end_frame = int(spec.get("end_frame", -1))
    if end_frame < 0:
        end_frame = frame_count - 1
    expected = set(spec["expected"])
    input_mode = spec["input_mode"]
    cap.set(cv2.CAP_PROP_POS_FRAMES, start_frame)

    video_out_dir = output_dir / "videos" / spec["name"]
    video_out_dir.mkdir(parents=True, exist_ok=True)

    mode_rows: list[dict[str, Any]] = []
    detail_rows: list[dict[str, Any]] = []
    expected_counter: Counter[str] = Counter()
    timing = {
        "read_frame_seconds": 0.0,
        "person_detect_seconds": 0.0,
        "clothing_predict_seconds": 0.0,
        "postprocess_metric_seconds": 0.0,
    }

    wall_start = time.perf_counter()
    sampled_frames = 0
    frames_with_person = 0
    detected_persons = 0
    frame_index = start_frame - 1

    while frame_index < end_frame:
        t0 = time.perf_counter()
        ok, frame = cap.read()
        timing["read_frame_seconds"] += time.perf_counter() - t0
        if not ok:
            break
        frame_index += 1
        if (frame_index - start_frame) % args.frame_stride != 0:
            continue
        sampled_frames += 1
        if sampled_frames % args.log_every == 0:
            print(f"[{spec['name']}] frame={frame_index} sampled={sampled_frames}", flush=True)

        t0 = time.perf_counter()
        if input_mode == "full_frame":
            boxes = [bbox_from_frame(frame)]
        else:
            boxes = detect_person_boxes(detector, frame, device, args.person_conf)
        timing["person_detect_seconds"] += time.perf_counter() - t0

        if boxes:
            frames_with_person += 1
        detected_persons += len(boxes)

        crops = []
        metas = []
        for detection_index, (x1, y1, x2, y2, person_confidence) in enumerate(boxes):
            crop = frame[y1:y2, x1:x2]
            if crop.size == 0:
                continue
            crops.append(crop)
            metas.append((detection_index, (x1, y1, x2, y2, person_confidence)))

        if not crops:
            continue

        t0 = time.perf_counter()
        predictions = predictor.predict_batch_top_n(crops, args.top_k, args.batch_size)
        timing["clothing_predict_seconds"] += time.perf_counter() - t0

        t0 = time.perf_counter()
        for (detection_index, bbox), top_predictions in zip(metas, predictions):
            for label in expected:
                expected_counter[label] += 1
            add_metrics_row(
                mode_rows,
                detail_rows,
                spec["name"],
                frame_index,
                safe_div(frame_index, fps),
                detection_index,
                bbox,
                expected,
                top_predictions,
                args.clothing_conf,
            )
        timing["postprocess_metric_seconds"] += time.perf_counter() - t0

    cap.release()
    wall_seconds = time.perf_counter() - wall_start

    by_mode = {}
    per_video_rows = []
    for mode_name in MODES:
        mode_specific_rows = [row for row in mode_rows if row["mode"] == mode_name]
        summary = summarize_rows(mode_specific_rows, expected_counter)
        by_mode[mode_name] = summary
        per_video_rows.append(
            {
                "video": spec["name"],
                "mode": mode_name,
                "expected_classes": "|".join(sorted(expected)),
                "input_mode": input_mode,
                "source_fps": fps,
                "source_width": width,
                "source_height": height,
                "start_frame": start_frame,
                "end_frame": end_frame,
                "sampled_frames": sampled_frames,
                "frames_with_person": frames_with_person,
                "detected_persons": detected_persons,
                "total_predictions": summary["total_predictions"],
                "exact_match_rate": summary["exact_match_rate"],
                "partial_match_rate": summary["partial_match_rate"],
                "label_precision": summary["label_precision"],
                "label_recall": summary["label_recall"],
                "label_f1": summary["label_f1"],
                "missing_total": summary["label_false_negative"],
                "extra_total": summary["label_false_positive"],
                "wall_seconds": wall_seconds,
                "sampled_frame_fps": safe_div(sampled_frames, wall_seconds),
                "person_prediction_fps": safe_div(summary["total_predictions"], wall_seconds),
            }
        )

    write_csv(
        video_out_dir / "per_detection_predictions.csv",
        detail_rows,
        [
            "video",
            "mode",
            "frame",
            "time_sec",
            "detection_index",
            "person_bbox",
            "person_confidence",
            "expected_classes",
            "predicted_classes",
            "correct_labels",
            "missing_labels",
            "extra_labels",
            "exact_match",
            "partial_match",
            "confidence_map_json",
            "raw_detections_json",
            "final_detections_json",
            "top_predictions_json",
        ],
    )
    write_csv(video_out_dir / "video_summary.csv", per_video_rows, list(per_video_rows[0].keys()) if per_video_rows else [])

    result = {
        "name": spec["name"],
        "status": "completed",
        "path": str(video_path),
        "expected_classes": sorted(expected),
        "input_mode": input_mode,
        "source": {
            "fps": fps,
            "width": width,
            "height": height,
            "frame_count": frame_count,
            "start_frame": start_frame,
            "end_frame": end_frame,
        },
        "sampled_frames": sampled_frames,
        "frames_with_person": frames_with_person,
        "detected_persons": detected_persons,
        "wall_seconds": wall_seconds,
        "sampled_frame_fps": safe_div(sampled_frames, wall_seconds),
        "person_prediction_fps": safe_div(detected_persons, wall_seconds),
        "timing_seconds": timing,
        "timing_percent": {name: safe_div(value, sum(timing.values())) for name, value in timing.items()},
        "modes": by_mode,
    }
    (video_out_dir / "metrics.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    write_video_markdown(video_out_dir / "summary.md", result)
    return result


def aggregate_mode(rows: list[dict[str, Any]], mode_name: str) -> dict[str, Any]:
    mode_rows = []
    expected_counter: Counter[str] = Counter()
    for video in rows:
        summary = video["modes"][mode_name]
        for label, item in summary["per_class"].items():
            expected_counter[label] += item["support"]
        # Reconstruct enough weighted aggregate from class counters.
        # Full aggregate is computed separately below from totals.
        mode_rows.append(summary)

    total = sum(item["total_predictions"] for item in mode_rows)
    exact = sum(item["exact_match"] for item in mode_rows)
    partial = sum(item["partial_match"] for item in mode_rows)
    tp = sum(item["label_true_positive"] for item in mode_rows)
    fp = sum(item["label_false_positive"] for item in mode_rows)
    fn = sum(item["label_false_negative"] for item in mode_rows)
    precision = safe_div(tp, tp + fp)
    recall = safe_div(tp, tp + fn)
    return {
        "total_predictions": total,
        "exact_match": exact,
        "partial_match": partial,
        "exact_match_rate": safe_div(exact, total),
        "partial_match_rate": safe_div(partial, total),
        "label_true_positive": tp,
        "label_false_positive": fp,
        "label_false_negative": fn,
        "label_precision": precision,
        "label_recall": recall,
        "label_f1": safe_div(2 * precision * recall, precision + recall),
    }


def write_video_markdown(path: Path, result: dict[str, Any]) -> None:
    lines = [
        f"# {result['name']}",
        "",
        f"- Video: `{result['path']}`",
        f"- Expected: `{', '.join(result['expected_classes'])}`",
        f"- Input mode: `{result['input_mode']}`",
        f"- Frame range: `{result['source']['start_frame']}-{result['source']['end_frame']}`",
        f"- Source FPS: `{result['source']['fps']:.3f}`",
        f"- Sampled frames: `{result['sampled_frames']}`",
        f"- Frames with person: `{result['frames_with_person']}`",
        f"- Person predictions: `{result['detected_persons']}`",
        f"- Wall time: `{fmt_seconds(result['wall_seconds'])}`",
        f"- Sampled-frame FPS: `{result['sampled_frame_fps']:.3f}`",
        f"- Person-prediction FPS: `{result['person_prediction_fps']:.3f}`",
        "",
        "## Before vs After",
        "",
        "| Mode | Exact match | Partial match | Precision | Recall | F1 | Missing | Extra |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for mode_name in MODES:
        item = result["modes"][mode_name]
        label = "Before raw model output" if mode_name == "before_raw" else "After tuned rules"
        lines.append(
            f"| {label} | {pct(item['exact_match_rate'])} | {pct(item['partial_match_rate'])} | "
            f"{pct(item['label_precision'])} | {pct(item['label_recall'])} | {item['label_f1']:.4f} | "
            f"{item['label_false_negative']} | {item['label_false_positive']} |"
        )

    lines.extend(
        [
            "",
            "## Time Breakdown",
            "",
            "| Section | Seconds | Percent |",
            "|---|---:|---:|",
        ]
    )
    for name, seconds in result["timing_seconds"].items():
        lines.append(f"| {name} | {seconds:.3f} | {pct(result['timing_percent'][name])} |")

    lines.extend(["", "## Per-Class After Tuned", "", "| Class | Support | Pred | TP | FP | FN | Precision | Recall | Avg conf |", "|---|---:|---:|---:|---:|---:|---:|---:|---:|"])
    after = result["modes"]["after_tuned"]["per_class"]
    for label in TARGET_CLASSES:
        item = after[label]
        lines.append(
            f"| {label} | {item['support']} | {item['predicted']} | {item['tp']} | {item['fp']} | {item['fn']} | "
            f"{pct(item['precision'])} | {pct(item['recall'])} | {item['avg_confidence_when_predicted']:.4f} |"
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_overall_summary(path: Path, results: list[dict[str, Any]], args: argparse.Namespace) -> None:
    total_wall = sum(item["wall_seconds"] for item in results if item.get("status") == "completed")
    total_frames = sum(item["sampled_frames"] for item in results if item.get("status") == "completed")
    total_persons = sum(item["detected_persons"] for item in results if item.get("status") == "completed")
    before = aggregate_mode(results, "before_raw")
    after = aggregate_mode(results, "after_tuned")
    lines = [
        "# Clothing Video Evaluation: Before Raw vs After Tuned",
        "",
        "## Test Setup",
        "",
        f"- Clothing confidence threshold: `{args.clothing_conf}`",
        f"- Person confidence threshold: `{args.person_conf}`",
        f"- Frame stride: `{args.frame_stride}`",
        f"- Model: `{args.model}`",
        f"- Detector: `{args.detector}`",
        f"- Device: `{args.device}`",
        "",
        "Before means raw model detections directly above confidence threshold, without outfit rules.",
        "After means current tuned outfit rules.",
        "",
        "## Overall Result",
        "",
        "| Mode | Total predictions | Exact match | Partial match | Precision | Recall | F1 | Missing | Extra |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for label, item in (("Before raw model output", before), ("After tuned rules", after)):
        lines.append(
            f"| {label} | {item['total_predictions']} | {pct(item['exact_match_rate'])} | {pct(item['partial_match_rate'])} | "
            f"{pct(item['label_precision'])} | {pct(item['label_recall'])} | {item['label_f1']:.4f} | "
            f"{item['label_false_negative']} | {item['label_false_positive']} |"
        )

    lines.extend(
        [
            "",
            "## Runtime",
            "",
            f"- Total wall time: `{fmt_seconds(total_wall)}`",
            f"- Total sampled frames: `{total_frames}`",
            f"- Total person predictions: `{total_persons}`",
            f"- Overall sampled-frame FPS: `{safe_div(total_frames, total_wall):.3f}`",
            f"- Overall person-prediction FPS: `{safe_div(total_persons, total_wall):.3f}`",
            "",
            "## Per Video",
            "",
            "| Video | Expected | Input | Frames | Persons | Wall time | FPS | Before exact | After exact | Before F1 | After F1 |",
            "|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for result in results:
        b = result["modes"]["before_raw"]
        a = result["modes"]["after_tuned"]
        lines.append(
            f"| {result['name']} | {', '.join(result['expected_classes'])} | {result['input_mode']} | "
            f"{result['sampled_frames']} | {result['detected_persons']} | {fmt_seconds(result['wall_seconds'])} | "
            f"{result['sampled_frame_fps']:.3f} | {pct(b['exact_match_rate'])} | {pct(a['exact_match_rate'])} | "
            f"{b['label_f1']:.4f} | {a['label_f1']:.4f} |"
        )

    lines.extend(["", "## Interpretation", ""])
    lines.append(
        "- If After has higher exact match or precision, the tuned rules reduced noisy extra clothing predictions."
    )
    lines.append(
        "- If After has lower recall, the tuned rules removed some true clothing labels too aggressively."
    )
    lines.append(
        "- Use each `videos/<name>/per_detection_predictions.csv` file to inspect frame-level missing/extra labels and bounding boxes."
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", default="track_result/clothing_video_before_after_eval")
    parser.add_argument("--model", default="models/prepare_dataset.pt")
    parser.add_argument("--detector", default="yolo11n.pt")
    parser.add_argument("--device", default="auto")
    parser.add_argument("--person-conf", type=float, default=0.25)
    parser.add_argument("--clothing-conf", type=float, default=0.10)
    parser.add_argument("--imgsz-clothing", type=int, default=224)
    parser.add_argument("--top-k", type=int, default=20)
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument("--frame-stride", type=int, default=1)
    parser.add_argument("--log-every", type=int, default=100)
    parser.add_argument("--videos", nargs="*", default=None, help="Optional list of VIDEO_SPECS names to run.")
    args = parser.parse_args()

    output_dir = (WORKSPACE / args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    device = args.device
    if device == "auto":
        device = "cuda" if torch.cuda.is_available() else "cpu"
    args.device = device

    predictor = YoloPredictor((WORKSPACE / args.model).resolve(), device=device, imgsz=args.imgsz_clothing, conf=args.clothing_conf)
    detector = YOLO(str((WORKSPACE / args.detector).resolve()))
    detector.to(device)

    results = []
    start = time.perf_counter()
    specs = VIDEO_SPECS
    if args.videos:
        selected = set(args.videos)
        specs = [spec for spec in VIDEO_SPECS if spec["name"] in selected]
        missing = sorted(selected - {spec["name"] for spec in specs})
        if missing:
            raise SystemExit(f"Unknown video spec name(s): {', '.join(missing)}")
    for spec in specs:
        print(f"[start] {spec['name']}", flush=True)
        result = evaluate_one_video(spec, output_dir, predictor, detector, device, args)
        results.append(result)
        print(f"[done] {spec['name']} {result.get('wall_seconds', 0):.2f}s", flush=True)
    total_seconds = time.perf_counter() - start

    data = {
        "metadata": {
            "output_dir": str(output_dir),
            "model": args.model,
            "detector": args.detector,
            "device": device,
            "person_conf": args.person_conf,
            "clothing_conf": args.clothing_conf,
            "frame_stride": args.frame_stride,
            "selected_videos": args.videos or [spec["name"] for spec in specs],
            "total_wall_seconds": total_seconds,
        },
        "results": results,
    }
    (output_dir / "metrics.json").write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    write_overall_summary(output_dir / "summary.md", results, args)

    per_video_rows = []
    for result in results:
        for mode_name in MODES:
            item = result["modes"][mode_name]
            per_video_rows.append(
                {
                    "video": result["name"],
                    "mode": mode_name,
                    "expected_classes": "|".join(result["expected_classes"]),
                    "input_mode": result["input_mode"],
                    "sampled_frames": result["sampled_frames"],
                    "detected_persons": result["detected_persons"],
                    "wall_seconds": result["wall_seconds"],
                    "sampled_frame_fps": result["sampled_frame_fps"],
                    "person_prediction_fps": result["person_prediction_fps"],
                    "total_predictions": item["total_predictions"],
                    "exact_match_rate": item["exact_match_rate"],
                    "partial_match_rate": item["partial_match_rate"],
                    "label_precision": item["label_precision"],
                    "label_recall": item["label_recall"],
                    "label_f1": item["label_f1"],
                    "missing": item["label_false_negative"],
                    "extra": item["label_false_positive"],
                }
            )
    write_csv(output_dir / "per_video_summary.csv", per_video_rows, list(per_video_rows[0].keys()))
    print(json.dumps({"output_dir": str(output_dir), "summary": str(output_dir / "summary.md"), "total_seconds": total_seconds}, indent=2), flush=True)


if __name__ == "__main__":
    main()
