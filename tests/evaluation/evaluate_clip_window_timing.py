from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import cv2
import numpy as np
import torch


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = PROJECT_ROOT / "src"
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from ai.classifier import ClothingClassifier  # noqa: E402
from ai.detector import PersonDetector  # noqa: E402
from ai.feature_extractor import ClothingEmbedder  # noqa: E402
from src.ai.color_analysis_unified import analyze_clothing_colors  # noqa: E402
from src.config_loader import get_classifier_model_path, get_device  # noqa: E402
from tests.evaluation.metrics import mean, percentile, write_json  # noqa: E402


def now_ms() -> float:
    return time.perf_counter() * 1000


def sync_cuda() -> None:
    if torch.cuda.is_available():
        torch.cuda.synchronize()


class Timer:
    def __init__(self, timings: dict[str, list[float]], name: str):
        self.timings = timings
        self.name = name
        self.start = 0.0

    def __enter__(self):
        sync_cuda()
        self.start = now_ms()
        return self

    def __exit__(self, exc_type, exc, tb):
        sync_cuda()
        self.timings[self.name].append(now_ms() - self.start)


def summarize(values: list[float]) -> dict[str, float]:
    return {
        "count": len(values),
        "total_ms": sum(values),
        "avg_ms": mean(values),
        "p50_ms": percentile(values, 0.50),
        "p95_ms": percentile(values, 0.95),
        "max_ms": max(values) if values else 0.0,
    }


def item_crop(person_crop: np.ndarray, bbox) -> np.ndarray:
    if bbox is None:
        return person_crop
    x1, y1, x2, y2 = map(int, bbox)
    h, w = person_crop.shape[:2]
    x1 = max(0, min(w, x1))
    x2 = max(0, min(w, x2))
    y1 = max(0, min(h, y1))
    y2 = max(0, min(h, y2))
    if x2 <= x1 or y2 <= y1:
        return person_crop
    return person_crop[y1:y2, x1:x2]


def parse_expected_classes(value: str) -> set[str]:
    return {item.strip() for item in value.split(",") if item.strip()}


def top_expected_items(
    predictions: list[tuple[str, float, Any]],
    expected_classes: set[str],
) -> list[tuple[str, float, Any]]:
    """Keep one prediction for each expected class in this clip."""
    selected = []
    seen = set()
    for class_name, confidence, bbox in predictions:
        if class_name in expected_classes and class_name not in seen:
            selected.append((class_name, confidence, bbox))
            seen.add(class_name)
    return selected


def evaluate(args: argparse.Namespace) -> dict[str, Any]:
    out_dir = Path(args.output_dir)
    crop_dir = out_dir / "crops"
    wrong_crop_dir = out_dir / "wrong_crops"
    crop_dir.mkdir(parents=True, exist_ok=True)
    wrong_crop_dir.mkdir(parents=True, exist_ok=True)
    expected_classes = parse_expected_classes(args.expected_classes)

    device = get_device()
    if args.device:
        device = args.device
    if device == "cuda" and not torch.cuda.is_available():
        print("[clip-test] CUDA requested but unavailable; falling back to CPU")
        device = "cpu"

    print(f"[clip-test] device={device}")
    print(f"[clip-test] video={args.video}")
    print(f"[clip-test] frames={args.start_frame}-{args.end_frame - 1}")

    timings: dict[str, list[float]] = defaultdict(list)
    detections: list[dict[str, Any]] = []
    wrong_predictions: list[dict[str, Any]] = []
    class_counter = Counter()
    wrong_class_counter = Counter()
    color_counter = Counter()
    track_counter = Counter()

    detector = PersonDetector()
    classifier_model = get_classifier_model_path()
    classifier = ClothingClassifier(classifier_model)
    embedder = ClothingEmbedder(classifier_model, device=device)

    cap = cv2.VideoCapture(args.video)
    if not cap.isOpened():
        raise RuntimeError(f"Cannot open video: {args.video}")

    input_fps = cap.get(cv2.CAP_PROP_FPS) or 0.0
    total_video_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

    wall_start = time.perf_counter()
    processed_frames = 0
    frames_with_person = 0

    cap.set(cv2.CAP_PROP_POS_FRAMES, args.start_frame)
    for offset in range(args.frames):
        frame_number = args.start_frame + offset
        with Timer(timings, "frame_read_ms"):
            ok, frame = cap.read()
        if not ok or frame is None:
            break

        processed_frames += 1
        with Timer(timings, "person_detect_track_ms"):
            result = detector.track_people(frame)

        boxes = getattr(result, "boxes", None)
        person_embeddings = (
            getattr(result, "person_embeddings", None)
            or getattr(detector, "last_person_embeddings", [])
            or []
        )
        if boxes is None or len(boxes) == 0:
            continue

        frames_with_person += 1
        for det_idx, box in enumerate(boxes):
            confidence = float(box.conf.item()) if hasattr(box, "conf") else 0.0
            if confidence < args.confidence:
                continue
            track_id = -1
            if hasattr(box, "id") and box.id is not None:
                track_id = int(box.id.item())
            x1, y1, x2, y2 = map(int, box.xyxy[0])
            x1 = max(0, min(width, x1))
            x2 = max(0, min(width, x2))
            y1 = max(0, min(height, y1))
            y2 = max(0, min(height, y2))
            if x2 <= x1 or y2 <= y1:
                continue

            with Timer(timings, "person_crop_ms"):
                person_crop = frame[y1:y2, x1:x2]

            crop_path = ""
            if args.save_crops:
                with Timer(timings, "crop_save_ms"):
                    crop_path = str(crop_dir / f"frame_{frame_number:05d}_track_{track_id}_det_{det_idx}.jpg")
                    cv2.imwrite(crop_path, person_crop)

            detector_embedding = person_embeddings[det_idx] if det_idx < len(person_embeddings) else None

            with Timer(timings, "embedding_fusion_ms"):
                embedding, embed_labels = embedder.get_embedding(
                    person_crop,
                    person_embedding=detector_embedding,
                )

            with Timer(timings, "clothing_predict_ms"):
                predictions = classifier.predict_top_n(person_crop, top_n=args.top_k)

            selected_items = top_expected_items(predictions, expected_classes)
            if not selected_items and predictions:
                selected_items = predictions[: min(2, len(predictions))]

            detection_wrong_predictions = []
            for pred_rank, (pred_class, pred_conf, pred_bbox) in enumerate(predictions, 1):
                if pred_class in expected_classes or pred_class == "Unknown":
                    continue
                with Timer(timings, "wrong_object_crop_save_ms"):
                    wrong_crop = item_crop(person_crop, pred_bbox)
                    wrong_path = wrong_crop_dir / (
                        f"frame_{frame_number:05d}_track_{track_id}_det_{det_idx}_"
                        f"rank_{pred_rank}_{pred_class}.jpg"
                    )
                    cv2.imwrite(str(wrong_path), wrong_crop)
                wrong_row = {
                    "frame": frame_number,
                    "track_id": track_id,
                    "det_idx": det_idx,
                    "rank": pred_rank,
                    "predicted_class": str(pred_class),
                    "confidence": float(pred_conf),
                    "expected_classes": sorted(expected_classes),
                    "person_bbox": [x1, y1, x2, y2],
                    "object_bbox_in_person_crop": list(map(int, pred_bbox)) if pred_bbox is not None else None,
                    "wrong_crop_path": str(wrong_path),
                }
                wrong_predictions.append(wrong_row)
                detection_wrong_predictions.append(wrong_row)
                wrong_class_counter[str(pred_class)] += 1

            color_results = []
            if not args.disable_color:
                for class_name, item_conf, item_bbox in selected_items:
                    crop = item_crop(person_crop, item_bbox)
                    with Timer(timings, "color_analysis_ms"):
                        color_result = analyze_clothing_colors(crop)
                    primary_color = color_result.get("primary_detailed_color", "unknown")
                    color_counter[primary_color] += 1
                    color_results.append({
                        "class_name": class_name,
                        "confidence": float(item_conf),
                        "primary_color": primary_color,
                        "top_colors": color_result.get("top_colors", []),
                    })

            for class_name, _, _ in selected_items:
                class_counter[class_name] += 1
            track_counter[str(track_id)] += 1

            detections.append({
                "frame": frame_number,
                "track_id": track_id,
                "confidence": confidence,
                "bbox": [x1, y1, x2, y2],
                "crop_path": crop_path,
                "selected_classes": [
                    {"class_name": str(name), "confidence": float(conf)}
                    for name, conf, _ in selected_items
                ],
                "wrong_predictions": detection_wrong_predictions,
                "embed_labels": embed_labels,
                "embedding_dim": int(len(embedding)) if embedding is not None else 0,
                "color_results": color_results,
            })

    cap.release()
    wall_seconds = time.perf_counter() - wall_start

    timing_summary = {name: summarize(values) for name, values in timings.items()}
    bottlenecks = sorted(
        (
            {"stage": name, **summary}
            for name, summary in timing_summary.items()
        ),
        key=lambda row: row["total_ms"],
        reverse=True,
    )

    report = {
        "task": "clip_window_timing",
        "video": args.video,
        "video_info": {
            "frames": total_video_frames,
            "input_fps": input_fps,
            "width": width,
            "height": height,
        },
        "device_requested": args.device or get_device(),
        "device_used": device,
        "cuda_available": torch.cuda.is_available(),
        "window": {
            "start_frame": args.start_frame,
            "end_frame_exclusive": args.end_frame,
            "requested_frames": args.end_frame - args.start_frame,
            "processed_frames": processed_frames,
            "frames_with_person": frames_with_person,
        },
        "wall_seconds": wall_seconds,
        "processed_window_fps": processed_frames / wall_seconds if wall_seconds > 0 else 0.0,
        "detections": len(detections),
        "unique_track_ids": len(track_counter),
        "track_counts": dict(track_counter),
        "expected_classes": sorted(expected_classes),
        "class_counts": dict(class_counter),
        "wrong_prediction_count": len(wrong_predictions),
        "wrong_class_counts": dict(wrong_class_counter),
        "color_counts": dict(color_counter),
        "timing_summary": timing_summary,
        "bottlenecks_by_total_time": bottlenecks,
        "detections_detail": detections,
        "wrong_predictions": wrong_predictions,
    }

    write_json(out_dir / "clip_timing_report.json", report)
    with (out_dir / "detections.csv").open("w", encoding="utf-8", newline="") as f:
        fieldnames = [
            "frame", "track_id", "confidence", "bbox", "crop_path",
            "selected_classes", "wrong_predictions", "embed_labels", "embedding_dim", "color_results",
        ]
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in detections:
            writer.writerow({
                **row,
                "bbox": json.dumps(row["bbox"]),
                "selected_classes": json.dumps(row["selected_classes"], ensure_ascii=False),
                "wrong_predictions": json.dumps(row["wrong_predictions"], ensure_ascii=False),
                "embed_labels": json.dumps(row["embed_labels"], ensure_ascii=False),
                "color_results": json.dumps(row["color_results"], ensure_ascii=False),
            })

    with (out_dir / "wrong_predictions.csv").open("w", encoding="utf-8", newline="") as f:
        fieldnames = [
            "frame", "track_id", "det_idx", "rank", "predicted_class", "confidence",
            "expected_classes", "person_bbox", "object_bbox_in_person_crop", "wrong_crop_path",
        ]
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in wrong_predictions:
            writer.writerow({
                **row,
                "expected_classes": json.dumps(row["expected_classes"], ensure_ascii=False),
                "person_bbox": json.dumps(row["person_bbox"]),
                "object_bbox_in_person_crop": json.dumps(row["object_bbox_in_person_crop"]),
            })

    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Time each stage on a fixed video frame window and save crops.")
    parser.add_argument("--video", required=True)
    parser.add_argument("--start-frame", type=int, default=100)
    parser.add_argument("--frames", type=int, default=200)
    parser.add_argument("--output-dir", default="track_result/test")
    parser.add_argument("--device", choices=["cuda", "cpu"], default="cuda")
    parser.add_argument("--confidence", type=float, default=0.25)
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--expected-classes", default="long_sleeve,trousers")
    parser.add_argument("--disable-color", action="store_true")
    parser.add_argument("--no-save-crops", dest="save_crops", action="store_false")
    parser.set_defaults(save_crops=True)
    args = parser.parse_args()
    args.end_frame = args.start_frame + args.frames
    report = evaluate(args)
    print(json.dumps({
        "processed_frames": report["window"]["processed_frames"],
        "detections": report["detections"],
        "unique_track_ids": report["unique_track_ids"],
        "processed_window_fps": report["processed_window_fps"],
        "class_counts": report["class_counts"],
        "wrong_prediction_count": report["wrong_prediction_count"],
        "wrong_class_counts": report["wrong_class_counts"],
        "top_bottlenecks": report["bottlenecks_by_total_time"][:5],
        "output": str(Path(args.output_dir) / "clip_timing_report.json"),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
