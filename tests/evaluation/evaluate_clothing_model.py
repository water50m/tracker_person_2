from __future__ import annotations

import argparse
import ast
import csv
import json
import math
import os
import re
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
os.environ.setdefault("YOLO_CONFIG_DIR", str(PROJECT_ROOT / ".ultralytics"))
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from ultralytics import YOLO

try:
    import yaml
except ImportError:  # pragma: no cover - PyYAML normally comes with ultralytics
    yaml = None


TARGET_CLASSES = [
    "short_sleeve",
    "long_sleeve",
    "shorts",
    "trousers",
    "skirt",
    "dress",
]

TOP_CLASSES = {"short_sleeve", "long_sleeve"}
BOTTOM_CLASSES = {"shorts", "trousers", "skirt"}
DRESS_COMPATIBLE_CLASSES = {"dress", "trousers", "short_sleeve", "long_sleeve"}

DATASET_TO_TARGET = {
    "long_sleeve_dress": "dress",
    "long_sleeve_outwear": "long_sleeve",
    "long_sleeve_top": "long_sleeve",
    "short_sleeve_dress": "dress",
    "short_sleeve_outwear": "short_sleeve",
    "short_sleeve_top": "short_sleeve",
    "shorts": "shorts",
    "skirt": "skirt",
    "sling": "short_sleeve",
    "sling_dress": "dress",
    "trousers": "trousers",
    "vest": "short_sleeve",
    "vest_dress": "dress",
}

PREDICTION_ALIASES = {
    "0": "short_sleeve",
    "short": "shorts",
    "shorts": "shorts",
    "short_sleeve": "short_sleeve",
    "short_sleeve_top": "short_sleeve",
    "short_sleeve_outwear": "short_sleeve",
    "short sleeve": "short_sleeve",
    "short sleeve top": "short_sleeve",
    "short sleeve outwear": "short_sleeve",
    "sling": "short_sleeve",
    "vest": "short_sleeve",
    "1": "long_sleeve",
    "long_sleeve": "long_sleeve",
    "long_sleeve_top": "long_sleeve",
    "long_sleeve_outwear": "long_sleeve",
    "long sleeve": "long_sleeve",
    "long sleeve top": "long_sleeve",
    "long sleeve outwear": "long_sleeve",
    "2": "shorts",
    "3": "trousers",
    "trouser": "trousers",
    "trousers": "trousers",
    "pants": "trousers",
    "4": "skirt",
    "skirt": "skirt",
    "5": "dress",
    "dress": "dress",
    "vest_dress": "dress",
    "long_sleeve_dress": "dress",
    "short_sleeve_dress": "dress",
    "sling_dress": "dress",
    "vest dress": "dress",
    "long sleeve dress": "dress",
    "short sleeve dress": "dress",
    "sling dress": "dress",
}

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}


def resolve_path(path: str | Path) -> Path:
    path = Path(path)
    if path.is_absolute():
        return path
    return (PROJECT_ROOT / path).resolve()


def clean_label(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value).strip().lower().replace("-", "_")).replace(" ", "_")


def prediction_to_target(value: Any) -> str | None:
    raw = str(value).strip().lower().replace("-", "_")
    normalized = re.sub(r"\s+", " ", raw.replace("_", " ")).strip()
    compact = normalized.replace(" ", "_")
    return PREDICTION_ALIASES.get(raw) or PREDICTION_ALIASES.get(normalized) or PREDICTION_ALIASES.get(compact)


def safe_div(numerator: float, denominator: float) -> float:
    return numerator / denominator if denominator else 0.0


def pct(value: float) -> str:
    return f"{value * 100:.2f}%"


def read_data_yaml(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    if yaml is not None:
        loaded = yaml.safe_load(text)
        if isinstance(loaded, dict):
            return loaded

    data: dict[str, Any] = {}
    for line in text.splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        key = key.strip()
        value = value.strip()
        if key == "names":
            data["names"] = ast.literal_eval(value)
        elif key == "nc":
            data["nc"] = int(value)
    return data


def parse_class_names(data_yaml: Path) -> list[str]:
    data = read_data_yaml(data_yaml)
    names = data.get("names", [])
    if isinstance(names, dict):
        return [str(names[i]) for i in sorted(names, key=lambda v: int(v))]
    return [str(name) for name in names]


def yolo_to_xyxy(
    x_center: float,
    y_center: float,
    width: float,
    height: float,
    image_width: int,
    image_height: int,
) -> tuple[int, int, int, int]:
    x1 = int(round((x_center - width / 2) * image_width))
    y1 = int(round((y_center - height / 2) * image_height))
    x2 = int(round((x_center + width / 2) * image_width))
    y2 = int(round((y_center + height / 2) * image_height))
    return (
        max(0, min(image_width, x1)),
        max(0, min(image_height, y1)),
        max(0, min(image_width, x2)),
        max(0, min(image_height, y2)),
    )


def crop_image(image: np.ndarray, bbox: tuple[int, int, int, int]) -> np.ndarray | None:
    x1, y1, x2, y2 = bbox
    if x2 <= x1 or y2 <= y1:
        return None
    crop = image[y1:y2, x1:x2]
    if crop.size == 0:
        return None
    return crop


class YoloPredictor:
    def __init__(self, model_path: Path, device: str = "auto", imgsz: int = 224, conf: float | None = None, half: bool = False):
        self.model_path = model_path
        self.imgsz = imgsz
        self.conf = conf
        self.half = half
        if device == "auto":
            device = "cuda" if torch.cuda.is_available() else "cpu"
        self.device = device
        self.model = YOLO(str(model_path))
        self.model.to(self.device)
        self.last_results: list[Any] = []

    def _predict_kwargs(self) -> dict[str, Any]:
        kwargs = {"verbose": False, "device": self.device, "imgsz": self.imgsz}
        if self.half and str(self.device).startswith("cuda"):
            kwargs["half"] = True
        if self.conf is not None:
            kwargs["conf"] = self.conf
        return kwargs

    @staticmethod
    def _class_name(names: Any, class_id: int) -> str:
        if isinstance(names, dict):
            return str(names.get(class_id, names.get(str(class_id), class_id)))
        if isinstance(names, (list, tuple)) and class_id < len(names):
            return str(names[class_id])
        return str(class_id)

    def _result_top_n(self, result: Any, top_n: int = 5) -> list[dict[str, Any]]:
        predictions: list[dict[str, Any]] = []
        if getattr(result, "probs", None) is not None:
            probs = result.probs.data
            n = min(max(top_n, 1), int(probs.numel()))
            top_indices = torch.topk(probs, n).indices.tolist()
            for index in top_indices:
                raw_label = self._class_name(result.names, int(index))
                predictions.append(
                    {
                        "raw_class": raw_label,
                        "class": prediction_to_target(raw_label),
                        "confidence": float(probs[index].item()),
                        "bbox": None,
                    }
                )
            return predictions

        boxes = getattr(result, "boxes", None)
        if boxes is None or len(boxes) == 0:
            return []

        sorted_boxes = sorted(boxes, key=lambda box: float(box.conf.item()), reverse=True)
        for box in sorted_boxes[: max(top_n, 1)]:
            class_id = int(box.cls.item())
            raw_label = self._class_name(result.names, class_id)
            predictions.append(
                {
                    "raw_class": raw_label,
                    "class": prediction_to_target(raw_label),
                    "confidence": float(box.conf.item()),
                    "bbox": [int(v) for v in box.xyxy[0].tolist()],
                }
            )
        return predictions

    def predict_top_n(self, image: np.ndarray, top_n: int = 5) -> list[dict[str, Any]]:
        if image is None or image.size == 0:
            return []

        results = self.model(image, **self._predict_kwargs())
        if not results:
            self.last_results = []
            return []
        self.last_results = list(results)
        return self._result_top_n(results[0], top_n)

    def predict_batch_top_n(
        self,
        images: list[np.ndarray],
        top_n: int = 5,
        batch_size: int = 16,
    ) -> list[list[dict[str, Any]]]:
        if not images:
            return []
        if any(image is None or image.size == 0 for image in images):
            return [self.predict_top_n(image, top_n) for image in images]
        try:
            results = self.model(images, batch=batch_size, **self._predict_kwargs())
            self.last_results = list(results)
            return [self._result_top_n(result, top_n) for result in results]
        except Exception as exc:
            print(f"[dataset] batch inference fallback: {exc}", flush=True)
            self.last_results = []
            return [self.predict_top_n(image, top_n) for image in images]


def list_dataset_images(dataset: Path) -> list[Path]:
    images_dir = dataset / "images"
    if not images_dir.exists():
        raise FileNotFoundError(f"Missing YOLO images directory: {images_dir}")
    return sorted(path for path in images_dir.iterdir() if path.suffix.lower() in IMAGE_EXTENSIONS)


def read_yolo_labels(label_path: Path) -> list[tuple[int, float, float, float, float]]:
    if not label_path.exists():
        return []
    labels = []
    for line in label_path.read_text(encoding="utf-8").splitlines():
        parts = line.strip().split()
        if len(parts) < 5:
            continue
        labels.append((int(float(parts[0])), *[float(v) for v in parts[1:5]]))
    return labels


def save_wrong_crop(
    image: np.ndarray,
    output_dir: Path,
    true_class: str,
    pred_class: str,
    image_path: Path,
    object_index: int,
    confidence: float,
) -> str:
    safe_pred = pred_class or "unknown"
    target_dir = output_dir / f"true_{true_class}_pred_{safe_pred}"
    target_dir.mkdir(parents=True, exist_ok=True)
    stem = f"{image_path.stem}_obj{object_index:02d}_conf_{confidence:.3f}".replace(".", "p")
    wrong_path = target_dir / f"{stem}.jpg"
    cv2.imwrite(str(wrong_path), image)
    return str(wrong_path)


def selected_prediction(row: dict[str, Any], threshold: float) -> tuple[str, float, str]:
    top = row.get("top_k", [])
    if not top:
        return "no_prediction", 0.0, "Unknown"
    best = top[0]
    confidence = float(best.get("confidence", 0.0))
    mapped = best.get("class")
    raw = str(best.get("raw_class", "Unknown"))
    if confidence < threshold or mapped not in TARGET_CLASSES:
        return "no_prediction", confidence, raw
    return str(mapped), confidence, raw


def classification_metrics(rows: list[dict[str, Any]], threshold: float) -> dict[str, Any]:
    confusion: dict[str, Counter[str]] = {label: Counter() for label in TARGET_CLASSES}
    per_class: dict[str, dict[str, Any]] = {}
    predictions_by_class: Counter[str] = Counter()

    correct = 0
    rejected = 0
    for row in rows:
        true_class = row["true_class"]
        pred_class, confidence, _ = selected_prediction(row, threshold)
        if pred_class == "no_prediction":
            rejected += 1
        predictions_by_class[pred_class] += 1
        confusion[true_class][pred_class] += 1
        correct += int(true_class == pred_class)

    total = len(rows)
    for label in TARGET_CLASSES:
        tp = confusion[label][label]
        fp = sum(confusion[true][label] for true in TARGET_CLASSES if true != label)
        fn = sum(count for pred, count in confusion[label].items() if pred != label)
        support = sum(confusion[label].values())
        predicted = tp + fp
        precision = safe_div(tp, predicted)
        recall = safe_div(tp, support)
        f1 = safe_div(2 * precision * recall, precision + recall)
        per_class[label] = {
            "precision": precision,
            "recall": recall,
            "f1": f1,
            "support": support,
            "predicted": predicted,
            "tp": tp,
            "fp": fp,
            "fn": fn,
        }

    macro_f1 = safe_div(sum(item["f1"] for item in per_class.values()), len(TARGET_CLASSES))
    return {
        "threshold": threshold,
        "total": total,
        "accepted": total - rejected,
        "rejected": rejected,
        "correct": correct,
        "wrong": total - correct,
        "accuracy": safe_div(correct, total),
        "accepted_accuracy": safe_div(
            sum(
                row["true_class"] == selected_prediction(row, threshold)[0]
                for row in rows
                if selected_prediction(row, threshold)[0] != "no_prediction"
            ),
            total - rejected,
        ),
        "macro_f1": macro_f1,
        "per_class": per_class,
        "confusion_matrix": {label: dict(confusion[label]) for label in TARGET_CLASSES},
        "predictions_by_class": dict(predictions_by_class),
    }


def threshold_comparison(rows: list[dict[str, Any]], thresholds: list[float]) -> list[dict[str, Any]]:
    comparison = []
    for threshold in thresholds:
        metrics = classification_metrics(rows, threshold)
        comparison.append(
            {
                "threshold": threshold,
                "total_samples": metrics["total"],
                "total_accepted_predictions": metrics["accepted"],
                "correct": metrics["correct"],
                "wrong": metrics["wrong"],
                "accuracy": metrics["accuracy"],
                "accepted_accuracy": metrics["accepted_accuracy"],
                "rejected_no_prediction_count": metrics["rejected"],
            }
        )
    return comparison


def top_k_accuracy(rows: list[dict[str, Any]], top_k: int) -> dict[str, float]:
    result = {}
    for k in range(1, top_k + 1):
        correct = 0
        for row in rows:
            predicted_classes = [item.get("class") for item in row.get("top_k", [])[:k]]
            correct += int(row["true_class"] in predicted_classes)
        result[f"top{k}"] = safe_div(correct, len(rows))
    return result


def false_positive_breakdown(rows: list[dict[str, Any]], threshold: float) -> dict[str, dict[str, int]]:
    breakdown: dict[str, Counter[str]] = {label: Counter() for label in TARGET_CLASSES}
    for row in rows:
        pred_class, _, _ = selected_prediction(row, threshold)
        if pred_class in TARGET_CLASSES:
            breakdown[pred_class][row["true_class"]] += 1
    return {label: dict(counter) for label, counter in breakdown.items()}


def false_negative_breakdown(rows: list[dict[str, Any]], threshold: float) -> dict[str, dict[str, int]]:
    breakdown: dict[str, Counter[str]] = {label: Counter() for label in TARGET_CLASSES}
    for row in rows:
        pred_class, _, _ = selected_prediction(row, threshold)
        breakdown[row["true_class"]][pred_class] += 1
    return {label: dict(counter) for label, counter in breakdown.items()}


def top_mistakes(rows: list[dict[str, Any]], threshold: float, limit: int = 10) -> list[dict[str, Any]]:
    mistakes = Counter()
    for row in rows:
        pred_class, _, _ = selected_prediction(row, threshold)
        if row["true_class"] != pred_class:
            mistakes[(row["true_class"], pred_class)] += 1
    return [
        {"true_class": true_class, "predicted_class": pred_class, "count": count}
        for (true_class, pred_class), count in mistakes.most_common(limit)
    ]


def candidate_detections(top_predictions: list[dict[str, Any]], threshold: float) -> list[dict[str, Any]]:
    detections = []
    for index, item in enumerate(top_predictions):
        class_name = item.get("class")
        confidence = float(item.get("confidence", 0.0))
        if class_name not in TARGET_CLASSES or confidence < threshold:
            continue
        detections.append(
            {
                "id": index,
                "class": str(class_name),
                "raw_class": str(item.get("raw_class", class_name)),
                "confidence": confidence,
                "bbox": item.get("bbox"),
                "kept": False,
                "removed_reason": "",
            }
        )
    return detections


def best_detection(detections: list[dict[str, Any]], classes: set[str]) -> dict[str, Any] | None:
    matches = [det for det in detections if det["class"] in classes]
    return max(matches, key=lambda det: det["confidence"], default=None)


def postprocess_outfit_base_detections(top_predictions: list[dict[str, Any]], threshold: float) -> dict[str, Any]:
    raw_detections = candidate_detections(top_predictions, threshold)
    final_ids: set[int] = set()
    removed_reasons: dict[int, str] = {}

    top_det = best_detection(raw_detections, TOP_CLASSES)
    bottom_det = best_detection(raw_detections, BOTTOM_CLASSES)
    dress_det = best_detection(raw_detections, {"dress"})

    selected = [det for det in (top_det, bottom_det, dress_det) if det is not None]

    if dress_det is not None and bottom_det is not None and bottom_det["class"] != "trousers":
        selected = [det for det in selected if det["id"] != bottom_det["id"]]
        removed_reasons[bottom_det["id"]] = "removed_by_dress_rule"

    for det in selected:
        final_ids.add(det["id"])

    final_detections = []
    annotated_raw = []
    for det in raw_detections:
        annotated = dict(det)
        annotated["kept"] = det["id"] in final_ids
        if not annotated["kept"]:
            annotated["removed_reason"] = removed_reasons.get(det["id"], "not_best_in_slot")
        annotated_raw.append(annotated)
        if annotated["kept"]:
            final_detections.append(annotated)

    return {
        "raw_detections": annotated_raw,
        "final_detections": final_detections,
        "classes": sorted({det["class"] for det in final_detections}),
    }


def postprocess_outfit_detections(top_predictions: list[dict[str, Any]], threshold: float) -> dict[str, Any]:
    raw_detections = candidate_detections(top_predictions, threshold)
    final_ids: set[int] = set()
    removed_reasons: dict[int, str] = {}

    dress_det = best_detection(raw_detections, {"dress"})
    skirt_det = best_detection(raw_detections, {"skirt"})
    boost_skirt = dress_det is not None and skirt_det is not None

    def rule_score(det: dict[str, Any]) -> float:
        if boost_skirt and det["class"] == "skirt":
            return det["confidence"] * 3.0
        return det["confidence"]

    top_det = best_detection(raw_detections, TOP_CLASSES)
    bottom_candidates = [det for det in raw_detections if det["class"] in BOTTOM_CLASSES]
    bottom_det = max(bottom_candidates, key=rule_score, default=None)

    dress_wins = dress_det is not None
    if boost_skirt and dress_det is not None and skirt_det is not None:
        skirt_adjusted_conf = rule_score(skirt_det)
        if skirt_adjusted_conf > dress_det["confidence"]:
            dress_wins = False
            removed_reasons[dress_det["id"]] = "removed_by_skirt_x3_rule"
        else:
            removed_reasons[skirt_det["id"]] = "removed_by_dress_skirt_rule"

    if dress_wins and dress_det is not None:
        selected = [dress_det]
        companions = []
        if top_det is not None:
            if top_det["confidence"] >= 0.76:
                companions.append(top_det)
            else:
                removed_reasons[top_det["id"]] = "removed_by_dress_top_conf_0p76_rule"
        if bottom_det is not None:
            if bottom_det["class"] == "trousers":
                companions.append(bottom_det)
            else:
                removed_reasons[bottom_det["id"]] = "removed_by_dress_rule"
        if companions:
            selected.append(max(companions, key=lambda det: det["confidence"]))
        for det in companions:
            if det["id"] not in {item["id"] for item in selected}:
                removed_reasons[det["id"]] = "removed_by_dress_max_2_rule"
    else:
        selected = [det for det in (top_det, bottom_det) if det is not None]

    for det in selected:
        final_ids.add(det["id"])

    final_detections = []
    annotated_raw = []
    for det in raw_detections:
        annotated = dict(det)
        annotated["kept"] = det["id"] in final_ids
        if det["class"] == "skirt" and dress_det is not None:
            annotated["adjusted_confidence_for_rule"] = det["confidence"] * 3.0
        if not annotated["kept"]:
            annotated["removed_reason"] = removed_reasons.get(det["id"], "not_best_in_slot")
        annotated_raw.append(annotated)
        if annotated["kept"]:
            final_detections.append(annotated)

    return {
        "raw_detections": annotated_raw,
        "final_detections": final_detections,
        "classes": sorted({det["class"] for det in final_detections}),
    }


def raw_outfit_detections(top_predictions: list[dict[str, Any]], threshold: float) -> dict[str, Any]:
    raw_detections = []
    for det in candidate_detections(top_predictions, threshold):
        annotated = dict(det)
        annotated["kept"] = True
        annotated["removed_reason"] = ""
        raw_detections.append(annotated)
    return {
        "raw_detections": raw_detections,
        "final_detections": raw_detections,
        "classes": sorted({det["class"] for det in raw_detections}),
    }


def prediction_result(top_predictions: list[dict[str, Any]], threshold: float, postprocess_mode: str = "outfit") -> dict[str, Any]:
    if postprocess_mode == "raw":
        return raw_outfit_detections(top_predictions, threshold)
    if postprocess_mode == "outfit_base":
        return postprocess_outfit_base_detections(top_predictions, threshold)
    return postprocess_outfit_detections(top_predictions, threshold)


def prediction_class_set(
    top_predictions: list[dict[str, Any]],
    threshold: float,
    postprocess_mode: str = "outfit",
) -> set[str]:
    return set(prediction_result(top_predictions, threshold, postprocess_mode)["classes"])


def prediction_class_confidence_map(
    top_predictions: list[dict[str, Any]],
    threshold: float,
    postprocess_mode: str = "outfit",
) -> dict[str, float]:
    confidences: dict[str, float] = {}
    for item in prediction_result(top_predictions, threshold, postprocess_mode)["final_detections"]:
        class_name = item["class"]
        confidence = float(item["confidence"])
        current = confidences.get(str(class_name), 0.0)
        confidences[str(class_name)] = max(current, confidence)
    return confidences


def evaluate_dataset_multilabel(
    args: argparse.Namespace,
    predictor: YoloPredictor,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    dataset = resolve_path(args.dataset)
    data_yaml = resolve_path(args.data_yaml)
    output_dir = resolve_path(args.output_dir)
    wrong_dir = output_dir / "wrong_predictions"
    class_names = parse_class_names(data_yaml)
    images = list_dataset_images(dataset)
    if args.max_images:
        images = images[: args.max_images]

    rows: list[dict[str, Any]] = []
    pending_images: list[np.ndarray] = []
    pending_samples: list[dict[str, Any]] = []
    latencies: list[float] = []
    label_read_failures = 0
    multi_label_images = 0

    def flush_pending() -> None:
        if not pending_images:
            return

        start = time.perf_counter()
        batch_predictions = predictor.predict_batch_top_n(pending_images, args.top_k, args.batch_size)
        latency_ms = (time.perf_counter() - start) * 1000
        per_sample_latency = safe_div(latency_ms, len(pending_images))

        for sample, top_predictions, image in zip(pending_samples, batch_predictions, pending_images):
            latencies.append(per_sample_latency)
            postprocessed = prediction_result(top_predictions, args.primary_threshold, args.postprocess_mode)
            pred_classes = set(postprocessed["classes"])
            true_classes = set(sample["true_classes"])
            correct_labels = sorted(true_classes & pred_classes)
            missing_labels = sorted(true_classes - pred_classes)
            extra_labels = sorted(pred_classes - true_classes)
            exact_match = not missing_labels and not extra_labels
            wrong_image_path = ""
            if not exact_match:
                safe_missing = "_".join(missing_labels) if missing_labels else "none"
                safe_extra = "_".join(extra_labels) if extra_labels else "none"
                target_dir = wrong_dir / f"missing_{safe_missing}_extra_{safe_extra}"
                target_dir.mkdir(parents=True, exist_ok=True)
                wrong_image_path = str(target_dir / f"{sample['image_path'].stem}.jpg")
                cv2.imwrite(wrong_image_path, image)

            rows.append(
                {
                    "image_path": str(sample["image_path"]),
                    "label_path": str(sample["label_path"]),
                    "dataset_classes": sample["dataset_classes"],
                    "true_classes": sorted(true_classes),
                    "predicted_classes": sorted(pred_classes),
                    "correct_labels": correct_labels,
                    "missing_labels": missing_labels,
                    "extra_labels": extra_labels,
                    "exact_match": exact_match,
                    "partial_match": bool(correct_labels),
                    "image_width": int(image.shape[1]),
                    "image_height": int(image.shape[0]),
                    "raw_detections": postprocessed["raw_detections"],
                    "final_detections": postprocessed["final_detections"],
                    "top_k": top_predictions,
                    "latency_ms": per_sample_latency,
                    "wrong_image_path": wrong_image_path,
                }
            )

        pending_images.clear()
        pending_samples.clear()

    for image_index, image_path in enumerate(images, 1):
        if args.max_dataset_samples and len(rows) + len(pending_samples) >= args.max_dataset_samples:
            break

        label_path = dataset / "labels" / f"{image_path.stem}.txt"
        labels = read_yolo_labels(label_path)
        if not labels:
            label_read_failures += 1
            continue

        dataset_classes = []
        true_classes = []
        for dataset_class_id, *_ in labels:
            if dataset_class_id >= len(class_names):
                label_read_failures += 1
                continue
            dataset_class = class_names[dataset_class_id]
            target_class = DATASET_TO_TARGET.get(dataset_class)
            if target_class is None:
                label_read_failures += 1
                continue
            dataset_classes.append(dataset_class)
            true_classes.append(target_class)

        true_class_set = sorted(set(true_classes))
        if not true_class_set:
            label_read_failures += 1
            continue
        if len(true_class_set) > 1:
            multi_label_images += 1

        image = cv2.imread(str(image_path))
        if image is None:
            label_read_failures += 1
            continue

        pending_images.append(image)
        pending_samples.append(
            {
                "image_path": image_path,
                "label_path": label_path,
                "dataset_classes": sorted(set(dataset_classes)),
                "true_classes": true_class_set,
            }
        )
        if len(pending_images) >= args.batch_size:
            flush_pending()

        if image_index % args.log_every == 0:
            print(f"[dataset-multilabel] processed {image_index}/{len(images)} images, {len(rows)} rows", flush=True)

    flush_pending()
    metadata = {
        "dataset": str(dataset),
        "data_yaml": str(data_yaml),
        "images_found": len(images),
        "images_evaluated": len(rows),
        "label_or_image_failures": label_read_failures,
        "image_eval_mode": "multilabel_person",
        "postprocess_mode": args.postprocess_mode,
        "multi_label_images": multi_label_images,
        "avg_latency_ms": safe_div(sum(latencies), len(latencies)),
        "model": str(predictor.model_path),
        "model_device": predictor.device,
        "class_names": class_names,
        "target_classes": TARGET_CLASSES,
        "dataset_to_target": DATASET_TO_TARGET,
    }
    return rows, metadata


def multilabel_metrics(rows: list[dict[str, Any]], threshold: float, postprocess_mode: str = "outfit") -> dict[str, Any]:
    per_class: dict[str, dict[str, Any]] = {}
    label_tp = 0
    label_fp = 0
    label_fn = 0
    exact = 0
    partial = 0
    missing_counter: Counter[str] = Counter()
    extra_counter: Counter[str] = Counter()
    predictions_by_class: Counter[str] = Counter()
    gt_by_class: Counter[str] = Counter()

    for row in rows:
        true_classes = set(row["true_classes"])
        pred_classes = prediction_class_set(row["top_k"], threshold, postprocess_mode)
        correct = true_classes & pred_classes
        missing = true_classes - pred_classes
        extra = pred_classes - true_classes

        label_tp += len(correct)
        label_fn += len(missing)
        label_fp += len(extra)
        exact += int(not missing and not extra)
        partial += int(bool(correct))
        missing_counter.update(missing)
        extra_counter.update(extra)
        predictions_by_class.update(pred_classes)
        gt_by_class.update(true_classes)

    for label in TARGET_CLASSES:
        tp = sum(label in row["true_classes"] and label in prediction_class_set(row["top_k"], threshold, postprocess_mode) for row in rows)
        fp = sum(label not in row["true_classes"] and label in prediction_class_set(row["top_k"], threshold, postprocess_mode) for row in rows)
        fn = sum(label in row["true_classes"] and label not in prediction_class_set(row["top_k"], threshold, postprocess_mode) for row in rows)
        precision = safe_div(tp, tp + fp)
        recall = safe_div(tp, tp + fn)
        f1 = safe_div(2 * precision * recall, precision + recall)
        per_class[label] = {
            "precision": precision,
            "recall": recall,
            "f1": f1,
            "support": gt_by_class[label],
            "predicted": predictions_by_class[label],
            "tp": tp,
            "fp": fp,
            "fn": fn,
        }

    precision = safe_div(label_tp, label_tp + label_fp)
    recall = safe_div(label_tp, label_tp + label_fn)
    f1 = safe_div(2 * precision * recall, precision + recall)
    return {
        "threshold": threshold,
        "total_images": len(rows),
        "exact_match_images": exact,
        "partial_match_images": partial,
        "exact_match_accuracy": safe_div(exact, len(rows)),
        "partial_match_rate": safe_div(partial, len(rows)),
        "label_true_positive": label_tp,
        "label_false_positive": label_fp,
        "label_false_negative": label_fn,
        "label_precision": precision,
        "label_recall": recall,
        "label_f1": f1,
        "per_class": per_class,
        "missing_by_class": dict(missing_counter),
        "extra_by_class": dict(extra_counter),
        "predictions_by_class": dict(predictions_by_class),
        "ground_truth_by_class": dict(gt_by_class),
    }


def multilabel_threshold_comparison(
    rows: list[dict[str, Any]],
    thresholds: list[float],
    postprocess_mode: str = "outfit",
) -> list[dict[str, Any]]:
    comparison = []
    for threshold in thresholds:
        metrics = multilabel_metrics(rows, threshold, postprocess_mode)
        comparison.append(
            {
                "threshold": threshold,
                "total_images": metrics["total_images"],
                "exact_match_images": metrics["exact_match_images"],
                "partial_match_images": metrics["partial_match_images"],
                "exact_match_accuracy": metrics["exact_match_accuracy"],
                "partial_match_rate": metrics["partial_match_rate"],
                "label_precision": metrics["label_precision"],
                "label_recall": metrics["label_recall"],
                "label_f1": metrics["label_f1"],
                "label_false_positive": metrics["label_false_positive"],
                "label_false_negative": metrics["label_false_negative"],
            }
        )
    return comparison


def multilabel_tuning_breakdowns(rows: list[dict[str, Any]], threshold: float, postprocess_mode: str = "outfit") -> dict[str, Any]:
    true_to_pred: dict[str, dict[str, dict[str, float]]] = {
        true_class: {
            pred_class: {
                "true_images": 0,
                "predicted_on_true_images": 0,
                "confidence_sum": 0.0,
                "avg_confidence": 0.0,
            }
            for pred_class in TARGET_CLASSES
        }
        for true_class in TARGET_CLASSES
    }
    pred_summary = {
        pred_class: {
            "predicted_images": 0,
            "confidence_sum": 0.0,
            "avg_confidence": 0.0,
            "true_positive_images": 0,
            "extra_false_positive_images": 0,
        }
        for pred_class in TARGET_CLASSES
    }
    missing_combo_counter: Counter[str] = Counter()
    extra_combo_counter: Counter[str] = Counter()
    predicted_combo_counter: Counter[str] = Counter()
    true_combo_counter: Counter[str] = Counter()

    for row in rows:
        true_classes = set(row["true_classes"])
        pred_conf = prediction_class_confidence_map(row["top_k"], threshold, postprocess_mode)
        pred_classes = set(pred_conf)
        true_key = "|".join(sorted(true_classes))
        pred_key = "|".join(sorted(pred_classes)) if pred_classes else "no_prediction"
        true_combo_counter[true_key] += 1
        predicted_combo_counter[pred_key] += 1

        missing = true_classes - pred_classes
        extra = pred_classes - true_classes
        if missing:
            missing_combo_counter["|".join(sorted(missing))] += 1
        if extra:
            extra_combo_counter["|".join(sorted(extra))] += 1

        for true_class in true_classes:
            for pred_class in TARGET_CLASSES:
                true_to_pred[true_class][pred_class]["true_images"] += 1
            for pred_class, confidence in pred_conf.items():
                bucket = true_to_pred[true_class][pred_class]
                bucket["predicted_on_true_images"] += 1
                bucket["confidence_sum"] += confidence

        for pred_class, confidence in pred_conf.items():
            bucket = pred_summary[pred_class]
            bucket["predicted_images"] += 1
            bucket["confidence_sum"] += confidence
            if pred_class in true_classes:
                bucket["true_positive_images"] += 1
            else:
                bucket["extra_false_positive_images"] += 1

    for true_class in TARGET_CLASSES:
        for pred_class in TARGET_CLASSES:
            bucket = true_to_pred[true_class][pred_class]
            bucket["avg_confidence"] = safe_div(bucket["confidence_sum"], bucket["predicted_on_true_images"])
            del bucket["confidence_sum"]

    for pred_class in TARGET_CLASSES:
        bucket = pred_summary[pred_class]
        bucket["avg_confidence"] = safe_div(bucket["confidence_sum"], bucket["predicted_images"])
        bucket["precision"] = safe_div(bucket["true_positive_images"], bucket["predicted_images"])
        del bucket["confidence_sum"]

    return {
        "threshold": threshold,
        "true_to_pred": true_to_pred,
        "predicted_class_confidence": pred_summary,
        "top_missing_combinations": dict(missing_combo_counter.most_common(20)),
        "top_extra_combinations": dict(extra_combo_counter.most_common(20)),
        "predicted_label_combinations": dict(predicted_combo_counter.most_common(20)),
        "ground_truth_label_combinations": dict(true_combo_counter.most_common(20)),
    }


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def write_confusion_matrix_csv(path: Path, confusion: dict[str, dict[str, int]]) -> None:
    columns = TARGET_CLASSES + ["no_prediction"]
    rows = []
    for true_class in TARGET_CLASSES:
        row = {"true_class": true_class}
        row.update({pred_class: confusion.get(true_class, {}).get(pred_class, 0) for pred_class in columns})
        rows.append(row)
    write_csv(path, rows, ["true_class", *columns])


def write_per_class_csv(path: Path, per_class: dict[str, dict[str, Any]]) -> None:
    rows = []
    for label in TARGET_CLASSES:
        item = per_class[label]
        rows.append(
            {
                "class": label,
                "precision": item["precision"],
                "recall": item["recall"],
                "f1": item["f1"],
                "support": item["support"],
                "predicted": item["predicted"],
                "tp": item["tp"],
                "fp": item["fp"],
                "fn": item["fn"],
            }
        )
    write_csv(path, rows, ["class", "precision", "recall", "f1", "support", "predicted", "tp", "fp", "fn"])


def write_breakdown_csv(path: Path, breakdown: dict[str, dict[str, int]], axis_name: str) -> None:
    rows = []
    for label in TARGET_CLASSES:
        row = {axis_name: label}
        row.update({class_name: breakdown.get(label, {}).get(class_name, 0) for class_name in TARGET_CLASSES})
        row["no_prediction"] = breakdown.get(label, {}).get("no_prediction", 0)
        rows.append(row)
    write_csv(path, rows, [axis_name, *TARGET_CLASSES, "no_prediction"])


def write_confusion_matrix_png(path: Path, confusion: dict[str, dict[str, int]]) -> None:
    labels = TARGET_CLASSES + ["no_prediction"]
    cell = 96
    left = 170
    top = 130
    width = left + cell * len(labels) + 30
    height = top + cell * len(TARGET_CLASSES) + 40
    image = np.full((height, width, 3), 255, dtype=np.uint8)

    cv2.putText(image, "True \\ Pred", (20, 55), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (30, 30, 30), 2)
    for col_idx, label in enumerate(labels):
        x = left + col_idx * cell + 8
        cv2.putText(image, label[:12], (x, 85), cv2.FONT_HERSHEY_SIMPLEX, 0.43, (30, 30, 30), 1)
    for row_idx, true_class in enumerate(TARGET_CLASSES):
        y = top + row_idx * cell
        cv2.putText(image, true_class, (18, y + 56), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (30, 30, 30), 1)
        row_max = max([confusion.get(true_class, {}).get(label, 0) for label in labels] or [1])
        for col_idx, pred_class in enumerate(labels):
            x = left + col_idx * cell
            value = confusion.get(true_class, {}).get(pred_class, 0)
            intensity = int(245 - 160 * safe_div(value, row_max or 1))
            color = (255, intensity, intensity) if true_class != pred_class else (intensity, 255, intensity)
            cv2.rectangle(image, (x, y), (x + cell, y + cell), color, -1)
            cv2.rectangle(image, (x, y), (x + cell, y + cell), (210, 210, 210), 1)
            cv2.putText(image, str(value), (x + 28, y + 56), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (20, 20, 20), 2)

    path.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(path), image)


def evaluate_dataset(args: argparse.Namespace, predictor: YoloPredictor) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    dataset = resolve_path(args.dataset)
    data_yaml = resolve_path(args.data_yaml)
    output_dir = resolve_path(args.output_dir)
    wrong_dir = output_dir / "wrong_predictions"
    class_names = parse_class_names(data_yaml)
    images = list_dataset_images(dataset)
    if args.max_images:
        images = images[: args.max_images]
    rows: list[dict[str, Any]] = []
    latencies: list[float] = []
    label_read_failures = 0
    multi_label_images = 0
    pending_images: list[np.ndarray] = []
    pending_samples: list[dict[str, Any]] = []

    def flush_pending() -> None:
        if not pending_images:
            return

        start = time.perf_counter()
        batch_predictions = predictor.predict_batch_top_n(pending_images, args.top_k, args.batch_size)
        latency_ms = (time.perf_counter() - start) * 1000
        per_sample_latency = safe_div(latency_ms, len(pending_images))

        for sample, top_predictions, eval_image in zip(pending_samples, batch_predictions, pending_images):
            latencies.append(per_sample_latency)
            pred_class, confidence, raw_class = selected_prediction({"top_k": top_predictions}, args.primary_threshold)
            wrong_image_path = ""
            if pred_class != sample["true_class"]:
                wrong_image_path = save_wrong_crop(
                    eval_image,
                    wrong_dir,
                    sample["true_class"],
                    pred_class,
                    sample["image_path"],
                    sample["object_index"],
                    confidence,
                )

            rows.append(
                {
                    "image_path": str(sample["image_path"]),
                    "label_path": str(sample["label_path"]),
                    "object_index": sample["object_index"],
                    "dataset_class": sample["dataset_class"],
                    "dataset_class_id": sample["dataset_class_id"],
                    "true_class": sample["true_class"],
                    "bbox_xyxy": list(sample["bbox"]),
                    "prediction": pred_class,
                    "raw_prediction": raw_class,
                    "confidence": confidence,
                    "top_k": top_predictions,
                    "latency_ms": per_sample_latency,
                    "wrong_image_path": wrong_image_path,
                }
            )

        pending_images.clear()
        pending_samples.clear()

    for image_index, image_path in enumerate(images, 1):
        if args.max_dataset_samples and len(rows) + len(pending_samples) >= args.max_dataset_samples:
            break
        label_path = dataset / "labels" / f"{image_path.stem}.txt"
        labels = read_yolo_labels(label_path)
        if not labels:
            label_read_failures += 1
            continue

        image = cv2.imread(str(image_path))
        if image is None:
            label_read_failures += len(labels)
            continue

        height, width = image.shape[:2]
        if len(labels) > 1:
            multi_label_images += 1
        labels_to_evaluate = labels if args.image_input_mode == "bbox-crop" else labels[:1]
        for object_index, (dataset_class_id, x_center, y_center, box_width, box_height) in enumerate(labels_to_evaluate):
            if dataset_class_id >= len(class_names):
                label_read_failures += 1
                continue
            dataset_class = class_names[dataset_class_id]
            true_class = DATASET_TO_TARGET.get(dataset_class)
            if true_class is None:
                label_read_failures += 1
                continue

            bbox = yolo_to_xyxy(x_center, y_center, box_width, box_height, width, height)
            eval_image = image
            if args.image_input_mode == "bbox-crop":
                eval_image = crop_image(image, bbox)
                if eval_image is None:
                    label_read_failures += 1
                    continue

            pending_images.append(eval_image)
            pending_samples.append(
                {
                    "image_path": image_path,
                    "label_path": label_path,
                    "object_index": object_index,
                    "dataset_class": dataset_class,
                    "dataset_class_id": dataset_class_id,
                    "true_class": true_class,
                    "bbox": bbox,
                }
            )
            if len(pending_images) >= args.batch_size:
                flush_pending()

        if image_index % args.log_every == 0:
            print(f"[dataset] processed {image_index}/{len(images)} images, {len(rows)} objects", flush=True)

    flush_pending()

    metadata = {
        "dataset": str(dataset),
        "data_yaml": str(data_yaml),
        "images_found": len(images),
        "objects_evaluated": len(rows),
        "label_or_image_failures": label_read_failures,
        "image_input_mode": args.image_input_mode,
        "multi_label_images": multi_label_images,
        "avg_latency_ms": safe_div(sum(latencies), len(latencies)),
        "model": str(predictor.model_path),
        "model_device": predictor.device,
        "class_names": class_names,
        "target_classes": TARGET_CLASSES,
        "dataset_to_target": DATASET_TO_TARGET,
    }
    return rows, metadata


def detect_person_boxes(detector: YOLO, frame: np.ndarray, device: str, confidence: float) -> list[tuple[int, int, int, int, float]]:
    results = detector(frame, classes=[0], conf=confidence, verbose=False, device=device)
    if not results:
        return []
    boxes = getattr(results[0], "boxes", None)
    if boxes is None or len(boxes) == 0:
        return []
    output = []
    height, width = frame.shape[:2]
    for box in boxes:
        x1, y1, x2, y2 = [int(v) for v in box.xyxy[0].tolist()]
        x1 = max(0, min(width, x1))
        x2 = max(0, min(width, x2))
        y1 = max(0, min(height, y1))
        y2 = max(0, min(height, y2))
        if x2 > x1 and y2 > y1:
            output.append((x1, y1, x2, y2, float(box.conf.item())))
    return output


def evaluate_video(
    video_path: Path,
    name: str,
    allowed_classes: set[str],
    start_frame: int,
    end_frame: int,
    args: argparse.Namespace,
    predictor: YoloPredictor,
    detector: YOLO,
    detector_device: str,
) -> dict[str, Any]:
    output_dir = resolve_path(args.output_dir) / "video_tests" / name
    output_dir.mkdir(parents=True, exist_ok=True)
    capture = cv2.VideoCapture(str(video_path))
    if not capture.isOpened():
        return {"name": name, "video_path": str(video_path), "status": "failed_to_open"}
    if start_frame > 0:
        capture.set(cv2.CAP_PROP_POS_FRAMES, start_frame)

    rows = []
    wrong_rows = []
    frame_index = start_frame - 1
    sampled_frames = 0
    frames_with_wrong_counts: Counter[int] = Counter()
    while True:
        ok, frame = capture.read()
        if not ok:
            break
        frame_index += 1
        if end_frame >= 0 and frame_index > end_frame:
            break
        if (frame_index - start_frame) % args.video_frame_stride != 0:
            continue
        sampled_frames += 1
        if args.video_max_frames and sampled_frames > args.video_max_frames:
            break
        if sampled_frames % args.log_every == 0:
            print(f"[video:{name}] processed {sampled_frames} sampled frames at source frame {frame_index}", flush=True)

        boxes = detect_person_boxes(detector, frame, detector_device, args.person_confidence)
        for detection_index, (x1, y1, x2, y2, person_confidence) in enumerate(boxes):
            crop = frame[y1:y2, x1:x2]
            top_predictions = predictor.predict_top_n(crop, args.top_k)
            pred_class, confidence, raw_class = selected_prediction({"top_k": top_predictions}, args.primary_threshold)
            is_correct = pred_class in allowed_classes
            if not is_correct:
                frames_with_wrong_counts[frame_index] += 1
                wrong_rows.append(
                    {
                        "frame": frame_index,
                        "detection_index": detection_index,
                        "bbox_x1": x1,
                        "bbox_y1": y1,
                        "bbox_x2": x2,
                        "bbox_y2": y2,
                        "person_confidence": person_confidence,
                        "expected_classes": "|".join(sorted(allowed_classes)),
                        "predicted_class": pred_class,
                        "raw_prediction": raw_class,
                        "prediction_confidence": confidence,
                        "mistake_from": "|".join(sorted(allowed_classes)),
                        "mistake_to": pred_class,
                    }
                )

            rows.append(
                {
                    "frame": frame_index,
                    "detection_index": detection_index,
                    "person_bbox_xyxy": [x1, y1, x2, y2],
                    "person_confidence": person_confidence,
                    "prediction": pred_class,
                    "raw_prediction": raw_class,
                    "confidence": confidence,
                    "is_correct": is_correct,
                    "top_k": top_predictions,
                }
            )

    capture.release()
    total = len(rows)
    correct = sum(1 for row in rows if row["is_correct"])
    wrong = total - correct
    predictions_by_class = Counter(row["prediction"] for row in rows)
    unexpected = Counter(row["prediction"] for row in rows if row["prediction"] not in allowed_classes)
    worst_frames = [
        {"frame": frame, "wrong_predictions": count}
        for frame, count in frames_with_wrong_counts.most_common(10)
    ]
    result = {
        "name": name,
        "video_path": str(video_path),
        "status": "completed",
        "allowed_classes": sorted(allowed_classes),
        "start_frame": start_frame,
        "end_frame": end_frame,
        "sampled_frames": sampled_frames,
        "frame_stride": args.video_frame_stride,
        "total_predictions": total,
        "correct_predictions": correct,
        "wrong_predictions": wrong,
        "accuracy": safe_div(correct, total),
        "wrong_rate": safe_div(wrong, total),
        "predictions_by_class": dict(predictions_by_class),
        "unexpected_class_count": dict(unexpected),
        "frames_with_most_wrong_predictions": worst_frames,
        "wrong_records": wrong_rows,
        "rows": rows,
    }
    write_video_summary(output_dir / "summary.md", result)
    (output_dir / "metrics.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    write_video_predictions_csv(output_dir / "predictions.csv", rows, allowed_classes)
    write_video_wrong_predictions_csv(output_dir / "wrong_predictions.csv", wrong_rows)
    return result


def write_video_summary(path: Path, result: dict[str, Any]) -> None:
    lines = [
        f"# {result['name']}",
        "",
        f"- Video path: `{result.get('video_path', '')}`",
        f"- Status: `{result.get('status', '')}`",
    ]
    if result.get("status") == "completed":
        lines.extend(
            [
                f"- Allowed classes: {', '.join(result['allowed_classes'])}",
                f"- Frame range: {result['start_frame']} to {result['end_frame'] if result['end_frame'] >= 0 else 'end'}",
                f"- Frame stride: {result['frame_stride']}",
                f"- Total predictions: {result['total_predictions']}",
                f"- Correct predictions: {result['correct_predictions']}",
                f"- Wrong predictions: {result['wrong_predictions']}",
                f"- Accuracy: {pct(result['accuracy'])}",
                f"- Wrong rate: {pct(result['wrong_rate'])}",
                "",
                "## Predictions by class",
                "",
            ]
        )
        for label, count in sorted(result["predictions_by_class"].items()):
            lines.append(f"- {label}: {count}")
        lines.extend(["", "## Unexpected class count", ""])
        for label, count in sorted(result["unexpected_class_count"].items()):
            lines.append(f"- {label}: {count}")
        lines.extend(["", "## Frames with most wrong predictions", ""])
        for item in result["frames_with_most_wrong_predictions"]:
            lines.append(f"- frame {item['frame']}: {item['wrong_predictions']}")
        lines.extend(["", "## Wrong prediction records", ""])
        lines.append(f"See `{path.parent / 'wrong_predictions.csv'}` for frame, bbox, expected class, and predicted class.")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_video_predictions_csv(path: Path, rows: list[dict[str, Any]], allowed_classes: set[str]) -> None:
    csv_rows = []
    for row in rows:
        x1, y1, x2, y2 = row["person_bbox_xyxy"]
        csv_rows.append(
            {
                "frame": row["frame"],
                "detection_index": row["detection_index"],
                "bbox_x1": x1,
                "bbox_y1": y1,
                "bbox_x2": x2,
                "bbox_y2": y2,
                "person_confidence": row["person_confidence"],
                "expected_classes": "|".join(sorted(allowed_classes)),
                "predicted_class": row["prediction"],
                "raw_prediction": row["raw_prediction"],
                "prediction_confidence": row["confidence"],
                "is_correct": row["is_correct"],
                "top_k_json": json.dumps(row["top_k"], ensure_ascii=False),
            }
        )
    write_csv(
        path,
        csv_rows,
        [
            "frame",
            "detection_index",
            "bbox_x1",
            "bbox_y1",
            "bbox_x2",
            "bbox_y2",
            "person_confidence",
            "expected_classes",
            "predicted_class",
            "raw_prediction",
            "prediction_confidence",
            "is_correct",
            "top_k_json",
        ],
    )


def write_video_wrong_predictions_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    write_csv(
        path,
        rows,
        [
            "frame",
            "detection_index",
            "bbox_x1",
            "bbox_y1",
            "bbox_x2",
            "bbox_y2",
            "person_confidence",
            "expected_classes",
            "predicted_class",
            "raw_prediction",
            "prediction_confidence",
            "mistake_from",
            "mistake_to",
        ],
    )


def write_summary(
    path: Path,
    metadata: dict[str, Any],
    primary_metrics: dict[str, Any],
    topk: dict[str, float],
    threshold_rows: list[dict[str, Any]],
    fp_breakdown: dict[str, dict[str, int]],
    fn_breakdown: dict[str, dict[str, int]],
    mistakes: list[dict[str, Any]],
    video_results: list[dict[str, Any]],
) -> None:
    lines = [
        "# Clothing Model Evaluation Summary",
        "",
        "## Dataset path",
        "",
        f"`{metadata['dataset']}`",
        "",
        "## Model path",
        "",
        f"`{metadata['model']}` on `{metadata['model_device']}`",
        "",
        "## Class mapping",
        "",
        "| Dataset class | Target class |",
        "|---|---|",
    ]
    for source, target in sorted(DATASET_TO_TARGET.items()):
        lines.append(f"| `{source}` | `{target}` |")

    lines.extend(
        [
            "",
            "## Overall accuracy",
            "",
            f"- Primary threshold: `{primary_metrics['threshold']:.2f}`",
            f"- Total object samples: {primary_metrics['total']}",
            f"- Accepted predictions: {primary_metrics['accepted']}",
            f"- Rejected / no prediction: {primary_metrics['rejected']}",
            f"- Correct predictions: {primary_metrics['correct']}",
            f"- Wrong predictions: {primary_metrics['wrong']}",
            f"- Accuracy: {pct(primary_metrics['accuracy'])}",
            f"- Accepted accuracy: {pct(primary_metrics['accepted_accuracy'])}",
            f"- Macro F1: {primary_metrics['macro_f1']:.4f}",
            f"- Image input mode: `{metadata['image_input_mode']}`",
            f"- Multi-label images seen: {metadata['multi_label_images']}",
            f"- Average latency: {metadata['avg_latency_ms']:.2f} ms/object",
            "",
            "## Per-class precision / recall / f1",
            "",
            "| Class | Precision | Recall | F1 | Support | TP | FP | FN |",
            "|---|---:|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for label in TARGET_CLASSES:
        item = primary_metrics["per_class"][label]
        lines.append(
            f"| {label} | {item['precision']:.4f} | {item['recall']:.4f} | "
            f"{item['f1']:.4f} | {item['support']} | {item['tp']} | {item['fp']} | {item['fn']} |"
        )

    lines.extend(["", "## Confusion matrix", "", "| True \\ Pred | " + " | ".join(TARGET_CLASSES + ["no_prediction"]) + " |"])
    lines.append("|---|" + "|".join("---:" for _ in TARGET_CLASSES + ["no_prediction"]) + "|")
    for true_class in TARGET_CLASSES:
        row = primary_metrics["confusion_matrix"].get(true_class, {})
        values = [str(row.get(pred_class, 0)) for pred_class in TARGET_CLASSES + ["no_prediction"]]
        lines.append(f"| {true_class} | " + " | ".join(values) + " |")

    lines.extend(["", "## Top mistakes", ""])
    if mistakes:
        for item in mistakes:
            lines.append(f"- true `{item['true_class']}` predicted `{item['predicted_class']}`: {item['count']}")
    else:
        lines.append("- No mistakes at the primary threshold.")

    lines.extend(["", "## False positive breakdown", ""])
    for label in TARGET_CLASSES:
        detail = ", ".join(f"{true}: {count}" for true, count in sorted(fp_breakdown[label].items())) or "none"
        lines.append(f"- predicted `{label}`: {detail}")

    lines.extend(["", "## False negative breakdown", ""])
    for label in TARGET_CLASSES:
        detail = ", ".join(f"{pred}: {count}" for pred, count in sorted(fn_breakdown[label].items())) or "none"
        lines.append(f"- true `{label}`: {detail}")

    lines.extend(["", "## Top-K accuracy", ""])
    for label, value in topk.items():
        lines.append(f"- {label}: {pct(value)}")

    lines.extend(
        [
            "",
            "## Confidence threshold comparison",
            "",
            "| Threshold | Accepted | Correct | Wrong | Accuracy | Accepted accuracy | Rejected |",
            "|---:|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for item in threshold_rows:
        lines.append(
            f"| {item['threshold']:.2f} | {item['total_accepted_predictions']} | {item['correct']} | "
            f"{item['wrong']} | {pct(item['accuracy'])} | {pct(item['accepted_accuracy'])} | "
            f"{item['rejected_no_prediction_count']} |"
        )

    lines.extend(["", "## Video results", ""])
    if not video_results:
        lines.append("- Video 1 result: skipped, no `--video-short` path provided.")
        lines.append("- Video 2 result: skipped, no `--video-long` path provided.")
    else:
        for result in video_results:
            if result.get("status") != "completed":
                lines.append(f"- {result['name']}: {result.get('status')} (`{result.get('video_path', '')}`)")
                continue
            lines.append(
                f"- {result['name']}: accuracy {pct(result['accuracy'])}, "
                f"total {result['total_predictions']}, wrong {result['wrong_predictions']}"
            )
        completed = [result for result in video_results if result.get("status") == "completed"]
        total_predictions = sum(result["total_predictions"] for result in completed)
        correct_predictions = sum(result["correct_predictions"] for result in completed)
        if completed:
            lines.append(f"- Overall video accuracy: {pct(safe_div(correct_predictions, total_predictions))}")

    lines.extend(["", "## Wrong prediction image examples and video mistake records", ""])
    lines.append(f"Image mistakes are saved as full already-cropped images in `{path.parent / 'wrong_predictions'}`.")
    lines.append("Video mistakes are saved as CSV rows with frame and bbox only in each `video_tests/*/wrong_predictions.csv`.")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_multilabel_summary(
    path: Path,
    metadata: dict[str, Any],
    primary_metrics: dict[str, Any],
    threshold_rows: list[dict[str, Any]],
    video_results: list[dict[str, Any]],
) -> None:
    lines = [
        "# Clothing Model Multi-Label Evaluation Summary",
        "",
        "## Dataset path",
        "",
        f"`{metadata['dataset']}`",
        "",
        "## Model path",
        "",
        f"`{metadata['model']}` on `{metadata['model_device']}`",
        "",
        "## Evaluation method",
        "",
        "- Each image is treated as one person crop.",
        "- Ground truth is the set of all mapped labels in that image label file.",
        "- Prediction is the set of all model detections whose confidence passes the threshold.",
        "- An image is complete only when predicted labels exactly match the ground-truth label set.",
        "",
        "## Overall image result",
        "",
        f"- Primary threshold: `{primary_metrics['threshold']:.2f}`",
        f"- Images evaluated: {primary_metrics['total_images']}",
        f"- Complete match images: {primary_metrics['exact_match_images']}",
        f"- Partial match images: {primary_metrics['partial_match_images']}",
        f"- Complete match accuracy: {pct(primary_metrics['exact_match_accuracy'])}",
        f"- Partial match rate: {pct(primary_metrics['partial_match_rate'])}",
        f"- Label precision: {pct(primary_metrics['label_precision'])}",
        f"- Label recall: {pct(primary_metrics['label_recall'])}",
        f"- Label F1: {primary_metrics['label_f1']:.4f}",
        f"- Missing labels: {primary_metrics['label_false_negative']}",
        f"- Extra labels: {primary_metrics['label_false_positive']}",
        f"- Multi-label images: {metadata['multi_label_images']}",
        f"- Average latency: {metadata['avg_latency_ms']:.2f} ms/image",
        "",
        "## Per-class result",
        "",
        "| Class | Precision | Recall | F1 | GT images | Pred images | TP | Extra/FP | Missing/FN |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for label in TARGET_CLASSES:
        item = primary_metrics["per_class"][label]
        lines.append(
            f"| {label} | {item['precision']:.4f} | {item['recall']:.4f} | {item['f1']:.4f} | "
            f"{item['support']} | {item['predicted']} | {item['tp']} | {item['fp']} | {item['fn']} |"
        )

    lines.extend(["", "## Missing labels by class", ""])
    for label in TARGET_CLASSES:
        lines.append(f"- `{label}`: {primary_metrics['missing_by_class'].get(label, 0)}")

    lines.extend(["", "## Extra labels by class", ""])
    for label in TARGET_CLASSES:
        lines.append(f"- `{label}`: {primary_metrics['extra_by_class'].get(label, 0)}")

    lines.extend(
        [
            "",
            "## Confidence threshold comparison",
            "",
            "| Threshold | Complete | Partial | Complete Acc | Partial Rate | Label Precision | Label Recall | Label F1 | Extra | Missing |",
            "|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for item in threshold_rows:
        lines.append(
            f"| {item['threshold']:.2f} | {item['exact_match_images']} | {item['partial_match_images']} | "
            f"{pct(item['exact_match_accuracy'])} | {pct(item['partial_match_rate'])} | "
            f"{pct(item['label_precision'])} | {pct(item['label_recall'])} | {item['label_f1']:.4f} | "
            f"{item['label_false_positive']} | {item['label_false_negative']} |"
        )

    lines.extend(["", "## Video results", ""])
    for result in video_results:
        if result.get("status") != "completed":
            lines.append(f"- {result['name']}: {result.get('status')} (`{result.get('video_path', '')}`)")
            continue
        lines.append(
            f"- {result['name']}: accuracy {pct(result['accuracy'])}, "
            f"total {result['total_predictions']}, wrong {result['wrong_predictions']}"
        )
    completed = [result for result in video_results if result.get("status") == "completed"]
    total_predictions = sum(result["total_predictions"] for result in completed)
    correct_predictions = sum(result["correct_predictions"] for result in completed)
    if completed:
        lines.append(f"- Overall video accuracy: {pct(safe_div(correct_predictions, total_predictions))}")

    lines.extend(["", "## Output files", ""])
    lines.append(f"- Per-image label comparison: `{path.parent / 'image_label_comparison.csv'}`")
    lines.append(f"- Detection viewer HTML: `{path.parent / 'detection_viewer.html'}`")
    lines.append(f"- Wrong full person images: `{path.parent / 'wrong_predictions'}`")
    lines.append("- Video mistakes: each `video_tests/*/wrong_predictions.csv`")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_image_label_comparison_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    csv_rows = []
    for row in rows:
        csv_rows.append(
            {
                "image_path": row["image_path"],
                "true_classes": "|".join(row["true_classes"]),
                "predicted_classes": "|".join(row["predicted_classes"]),
                "correct_labels": "|".join(row["correct_labels"]),
                "missing_labels": "|".join(row["missing_labels"]),
                "extra_labels": "|".join(row["extra_labels"]),
                "exact_match": row["exact_match"],
                "partial_match": row["partial_match"],
                "wrong_image_path": row["wrong_image_path"],
                "raw_detections_json": json.dumps(row.get("raw_detections", []), ensure_ascii=False),
                "final_detections_json": json.dumps(row.get("final_detections", []), ensure_ascii=False),
                "top_k_json": json.dumps(row["top_k"], ensure_ascii=False),
            }
        )
    write_csv(
        path,
        csv_rows,
        [
            "image_path",
            "true_classes",
            "predicted_classes",
            "correct_labels",
            "missing_labels",
            "extra_labels",
            "exact_match",
            "partial_match",
            "wrong_image_path",
            "raw_detections_json",
            "final_detections_json",
            "top_k_json",
        ],
    )


def image_file_url(path: str) -> str:
    return "file:///" + Path(path).as_posix().replace(" ", "%20").replace("#", "%23")


def write_detection_viewer_html(path: Path, rows: list[dict[str, Any]], threshold: float) -> None:
    viewer_rows = []
    for index, row in enumerate(rows):
        viewer_rows.append(
            {
                "index": index,
                "image_path": row["image_path"],
                "image_url": image_file_url(row["image_path"]),
                "image_width": row.get("image_width"),
                "image_height": row.get("image_height"),
                "true_classes": row["true_classes"],
                "predicted_classes": row["predicted_classes"],
                "correct_labels": row["correct_labels"],
                "missing_labels": row["missing_labels"],
                "extra_labels": row["extra_labels"],
                "exact_match": row["exact_match"],
                "partial_match": row["partial_match"],
                "raw_detections": row.get("raw_detections", []),
                "final_detections": row.get("final_detections", []),
            }
        )

    data_file = path.with_name(f"{path.stem}_data.js")
    data_json = json.dumps(viewer_rows, ensure_ascii=False).replace("</", "<\\/")
    data_file.write_text(f"window.DETECTION_VIEWER_DATA = {data_json};\n", encoding="utf-8")
    class_buttons = "".join(
        f'<label><input type="checkbox" class="class-filter" value="{class_name}" checked> {class_name}</label>'
        for class_name in TARGET_CLASSES
    )
    html = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Clothing Detection Viewer</title>
  <style>
    :root {{ color-scheme: light; font-family: Arial, sans-serif; }}
    body {{ margin: 0; background: #f4f6f8; color: #101820; }}
    header {{ position: sticky; top: 0; z-index: 2; background: #fff; border-bottom: 1px solid #d9dee5; padding: 10px 14px; }}
    .toolbar {{ display: flex; flex-wrap: wrap; gap: 10px; align-items: center; }}
    button {{ border: 1px solid #b8c0cc; background: #fff; padding: 7px 10px; border-radius: 6px; cursor: pointer; }}
    button:hover {{ background: #eef3f8; }}
    input[type="number"] {{ width: 76px; padding: 6px; }}
    #searchInput {{ width: min(460px, 72vw); padding: 7px 9px; border: 1px solid #b8c0cc; border-radius: 6px; }}
    #searchHelp {{ color: #526071; font-size: 12px; }}
    label {{ font-size: 13px; white-space: nowrap; }}
    main {{ display: grid; grid-template-columns: minmax(360px, 1fr) 360px; gap: 12px; padding: 12px; }}
    .stage {{ position: relative; background: #111; min-height: 420px; overflow: auto; text-align: center; padding: 12px; }}
    #imageWrap {{ position: relative; display: inline-block; line-height: 0; }}
    #image {{ max-width: none; height: auto; display: block; }}
    #overlay {{ position: absolute; left: 0; top: 0; pointer-events: none; }}
    aside {{ background: #fff; border: 1px solid #d9dee5; border-radius: 8px; padding: 12px; overflow: auto; max-height: calc(100vh - 88px); }}
    .pill {{ display: inline-block; padding: 3px 7px; margin: 2px; border-radius: 999px; background: #e9eef5; font-size: 12px; }}
    .ok {{ background: #dff7e8; }}
    .bad {{ background: #ffe3e3; }}
    .warn {{ background: #fff0bf; }}
    table {{ border-collapse: collapse; width: 100%; font-size: 12px; margin-top: 8px; }}
    th, td {{ border-bottom: 1px solid #e5e9ef; padding: 5px; text-align: left; }}
    code {{ font-size: 11px; word-break: break-all; }}
    @media (max-width: 900px) {{ main {{ grid-template-columns: 1fr; }} aside {{ max-height: none; }} }}
  </style>
</head>
<body>
<header>
  <div class="toolbar">
    <button id="prevBtn">Prev</button>
    <button id="nextBtn">Next</button>
    <span id="counter"></span>
    <label>Go <input id="indexInput" type="number" min="1"></label>
    <button id="zoomOutBtn">-</button>
    <span id="zoomLabel">100%</span>
    <button id="zoomInBtn">+</button>
    <button id="zoomResetBtn">Reset</button>
    <label><input id="showRaw" type="checkbox"> show raw boxes</label>
    <label><input id="onlyWrong" type="checkbox"> only wrong</label>
  </div>
  <div class="toolbar" style="margin-top:8px">
    <strong>Filter:</strong>
    {class_buttons}
  </div>
  <div class="toolbar" style="margin-top:8px">
    <label>Search <input id="searchInput" type="search" placeholder="missing:short_sleeve, extra:dress, reason:top_conf, filename, class"></label>
    <button id="clearSearchBtn">Clear</button>
    <span id="searchStatus"></span>
    <span id="searchHelp">Use Enter for next match.</span>
  </div>
</header>
<main>
  <section class="stage">
    <div id="imageWrap">
      <img id="image" alt="detection preview">
      <canvas id="overlay"></canvas>
    </div>
  </section>
  <aside>
    <h3 id="title"></h3>
    <div id="labels"></div>
    <p><code id="path"></code></p>
    <h4>Detections</h4>
    <div id="detections"></div>
  </aside>
</main>
<script src="{data_file.name}"></script>
<script>
const rows = window.DETECTION_VIEWER_DATA || [];
const threshold = {threshold};
const colors = {{
  short_sleeve: '#00a6fb',
  long_sleeve: '#7b2cbf',
  shorts: '#f77f00',
  trousers: '#2a9d8f',
  skirt: '#d62828',
  dress: '#6a994e'
}};
let idx = 0;
let zoom = 1;
const image = document.getElementById('image');
const imageWrap = document.getElementById('imageWrap');
const canvas = document.getElementById('overlay');
const ctx = canvas.getContext('2d');

function activeClasses() {{
  return new Set([...document.querySelectorAll('.class-filter:checked')].map(el => el.value));
}}
function rowText(row) {{
  const detections = [...(row.raw_detections || []), ...(row.final_detections || [])]
    .map(det => [det.class, det.raw_class, det.confidence, det.bbox, det.removed_reason].join(' '))
    .join(' ');
  return [
    row.image_path,
    row.true_classes.join(' '),
    row.predicted_classes.join(' '),
    row.correct_labels.join(' '),
    row.missing_labels.join(' '),
    row.extra_labels.join(' '),
    row.exact_match ? 'complete_match exact_match' : 'mismatch wrong',
    row.partial_match ? 'partial_match' : 'no_partial_match',
    detections
  ].join(' ').toLowerCase();
}}
function rowMatchesToken(row, token) {{
  const lower = token.toLowerCase();
  const parts = lower.split(':');
  if (parts.length >= 2) {{
    const key = parts.shift();
    const value = parts.join(':');
    if (!value) return true;
    if (key === 'missing') return row.missing_labels.some(x => x.toLowerCase().includes(value));
    if (key === 'extra') return row.extra_labels.some(x => x.toLowerCase().includes(value));
    if (key === 'true' || key === 'gt') return row.true_classes.some(x => x.toLowerCase().includes(value));
    if (key === 'pred' || key === 'predicted') return row.predicted_classes.some(x => x.toLowerCase().includes(value));
    if (key === 'correct') return row.correct_labels.some(x => x.toLowerCase().includes(value));
    if (key === 'reason') return (row.raw_detections || []).some(det => String(det.removed_reason || '').toLowerCase().includes(value));
    if (key === 'path' || key === 'file') return row.image_path.toLowerCase().includes(value);
  }}
  return rowText(row).includes(lower);
}}
function rowMatchesSearch(row) {{
  const query = document.getElementById('searchInput').value.trim();
  if (!query) return true;
  return query.split(/\s+/).every(token => rowMatchesToken(row, token));
}}
function visibleIndices() {{
  const onlyWrong = document.getElementById('onlyWrong').checked;
  return rows
    .map((row, i) => ((!onlyWrong || !row.exact_match) && rowMatchesSearch(row)) ? i : -1)
    .filter(i => i >= 0);
}}
function clampIndex() {{
  const visible = visibleIndices();
  if (!visible.length) {{ idx = 0; return; }}
  if (!visible.includes(idx)) idx = visible[0];
}}
function move(delta) {{
  const visible = visibleIndices();
  if (!visible.length) return;
  const pos = Math.max(0, visible.indexOf(idx));
  idx = visible[(pos + delta + visible.length) % visible.length];
  render();
}}
function detectionRows(row) {{
  const showRaw = document.getElementById('showRaw').checked;
  return showRaw ? row.raw_detections : row.final_detections;
}}
function updateZoomLabel() {{
  document.getElementById('zoomLabel').textContent = `${{Math.round(zoom * 100)}}%`;
}}
function applyZoom() {{
  if (!image.naturalWidth) return;
  image.style.width = `${{Math.max(1, Math.round(image.naturalWidth * zoom))}}px`;
  updateZoomLabel();
  draw();
}}
function changeZoom(delta) {{
  zoom = Math.max(0.25, Math.min(8, Number((zoom + delta).toFixed(2))));
  applyZoom();
}}
function renderLabels(row) {{
  const labels = document.getElementById('labels');
  labels.innerHTML = `
    <div>GT: ${{row.true_classes.map(x => `<span class="pill">${{x}}</span>`).join('')}}</div>
    <div>Pred: ${{row.predicted_classes.map(x => `<span class="pill">${{x}}</span>`).join('') || '<span class="pill warn">none</span>'}}</div>
    <div>Correct: ${{row.correct_labels.map(x => `<span class="pill ok">${{x}}</span>`).join('') || '<span class="pill">none</span>'}}</div>
    <div>Missing: ${{row.missing_labels.map(x => `<span class="pill bad">${{x}}</span>`).join('') || '<span class="pill ok">none</span>'}}</div>
    <div>Extra: ${{row.extra_labels.map(x => `<span class="pill warn">${{x}}</span>`).join('') || '<span class="pill ok">none</span>'}}</div>
  `;
}}
function draw() {{
  const row = rows[idx];
  const rect = image.getBoundingClientRect();
  canvas.width = Math.round(rect.width);
  canvas.height = Math.round(rect.height);
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  const scaleX = canvas.width / image.naturalWidth;
  const scaleY = canvas.height / image.naturalHeight;
  const filters = activeClasses();
  for (const det of detectionRows(row)) {{
    if (!filters.has(det.class) || !det.bbox) continue;
    const [x1, y1, x2, y2] = det.bbox;
    const x = x1 * scaleX, y = y1 * scaleY, w = (x2 - x1) * scaleX, h = (y2 - y1) * scaleY;
    ctx.strokeStyle = colors[det.class] || '#fff';
    ctx.lineWidth = det.kept ? 3 : 2;
    ctx.setLineDash(det.kept ? [] : [6, 4]);
    ctx.strokeRect(x, y, w, h);
    ctx.setLineDash([]);
    const text = `${{det.class}} ${{det.confidence.toFixed(2)}}${{det.kept ? '' : ' x'}}`;
    ctx.font = '13px Arial';
    const tw = ctx.measureText(text).width + 8;
    ctx.fillStyle = colors[det.class] || '#fff';
    ctx.fillRect(x, Math.max(0, y - 18), tw, 18);
    ctx.fillStyle = '#fff';
    ctx.fillText(text, x + 4, Math.max(13, y - 5));
  }}
}}
function renderDetections(row) {{
  const filters = activeClasses();
  const rowsHtml = detectionRows(row)
    .filter(det => filters.has(det.class))
    .map(det => `<tr><td>${{det.class}}</td><td>${{det.confidence.toFixed(4)}}</td><td>${{det.bbox ? det.bbox.join(', ') : ''}}</td><td>${{det.kept ? 'kept' : det.removed_reason}}</td></tr>`)
    .join('');
  document.getElementById('detections').innerHTML = `<table><thead><tr><th>class</th><th>conf</th><th>bbox</th><th>status</th></tr></thead><tbody>${{rowsHtml}}</tbody></table>`;
}}
function render() {{
  clampIndex();
  const row = rows[idx];
  const visible = visibleIndices();
  const visiblePos = visible.indexOf(idx) + 1;
  document.getElementById('counter').textContent = visible.length ? `${{visiblePos}} / ${{visible.length}} shown (${{idx + 1}} / ${{rows.length}})` : `0 / 0 shown (${{rows.length}} total)`;
  document.getElementById('searchStatus').textContent = `${{visible.length}} matches`;
  if (!row) return;
  document.getElementById('indexInput').value = idx + 1;
  document.getElementById('title').textContent = row.exact_match ? 'Complete match' : 'Mismatch';
  document.getElementById('path').textContent = row.image_path;
  renderLabels(row);
  renderDetections(row);
  image.onload = () => applyZoom();
  image.src = row.image_url;
  if (image.complete) applyZoom();
}}
document.getElementById('prevBtn').onclick = () => move(-1);
document.getElementById('nextBtn').onclick = () => move(1);
document.getElementById('zoomOutBtn').onclick = () => changeZoom(-0.25);
document.getElementById('zoomInBtn').onclick = () => changeZoom(0.25);
document.getElementById('zoomResetBtn').onclick = () => {{ zoom = 1; applyZoom(); }};
document.getElementById('indexInput').onchange = e => {{ idx = Math.max(0, Math.min(rows.length - 1, Number(e.target.value) - 1)); render(); }};
document.getElementById('showRaw').onchange = render;
document.getElementById('onlyWrong').onchange = render;
document.getElementById('searchInput').oninput = () => {{ clampIndex(); render(); }};
document.getElementById('searchInput').onkeydown = e => {{
  if (e.key === 'Enter') {{
    e.preventDefault();
    move(e.shiftKey ? -1 : 1);
  }}
}};
document.getElementById('clearSearchBtn').onclick = () => {{ document.getElementById('searchInput').value = ''; render(); }};
document.querySelectorAll('.class-filter').forEach(el => el.onchange = render);
window.addEventListener('resize', draw);
window.addEventListener('keydown', e => {{
  if (e.key === 'ArrowLeft') move(-1);
  if (e.key === 'ArrowRight') move(1);
  if (e.key === '+' || e.key === '=') changeZoom(0.25);
  if (e.key === '-' || e.key === '_') changeZoom(-0.25);
  if (e.key === '0') {{ zoom = 1; applyZoom(); }}
}});
render();
</script>
</body>
</html>
"""
    path.write_text(html, encoding="utf-8")


def write_true_to_pred_confidence_csv(path: Path, breakdown: dict[str, Any]) -> None:
    rows = []
    for true_class in TARGET_CLASSES:
        for pred_class in TARGET_CLASSES:
            item = breakdown["true_to_pred"][true_class][pred_class]
            rows.append(
                {
                    "true_class": true_class,
                    "predicted_class": pred_class,
                    "true_images": item["true_images"],
                    "predicted_on_true_images": item["predicted_on_true_images"],
                    "prediction_rate_on_true_class": safe_div(item["predicted_on_true_images"], item["true_images"]),
                    "avg_confidence": item["avg_confidence"],
                }
            )
    write_csv(
        path,
        rows,
        [
            "true_class",
            "predicted_class",
            "true_images",
            "predicted_on_true_images",
            "prediction_rate_on_true_class",
            "avg_confidence",
        ],
    )


def write_predicted_class_confidence_csv(path: Path, breakdown: dict[str, Any]) -> None:
    rows = []
    for pred_class in TARGET_CLASSES:
        item = breakdown["predicted_class_confidence"][pred_class]
        rows.append(
            {
                "predicted_class": pred_class,
                "predicted_images": item["predicted_images"],
                "avg_confidence": item["avg_confidence"],
                "true_positive_images": item["true_positive_images"],
                "extra_false_positive_images": item["extra_false_positive_images"],
                "precision": item["precision"],
            }
        )
    write_csv(
        path,
        rows,
        [
            "predicted_class",
            "predicted_images",
            "avg_confidence",
            "true_positive_images",
            "extra_false_positive_images",
            "precision",
        ],
    )


def write_counter_csv(path: Path, rows_dict: dict[str, int], key_name: str) -> None:
    write_csv(
        path,
        [{key_name: key, "count": count} for key, count in rows_dict.items()],
        [key_name, "count"],
    )


def write_tuning_summary(
    path: Path,
    metadata: dict[str, Any],
    primary_metrics: dict[str, Any],
    tuning_breakdown: dict[str, Any],
) -> None:
    lines = [
        "# Clothing Model Tuning Summary",
        "",
        f"- Dataset: `{metadata['dataset']}`",
        f"- Model: `{metadata['model']}` on `{metadata['model_device']}`",
        f"- Threshold: `{primary_metrics['threshold']:.2f}`",
        f"- Images evaluated: {primary_metrics['total_images']}",
        f"- Complete match accuracy: {pct(primary_metrics['exact_match_accuracy'])}",
        f"- Partial match rate: {pct(primary_metrics['partial_match_rate'])}",
        f"- Label precision: {pct(primary_metrics['label_precision'])}",
        f"- Label recall: {pct(primary_metrics['label_recall'])}",
        f"- Label F1: {primary_metrics['label_f1']:.4f}",
        f"- Extra labels: {primary_metrics['label_false_positive']}",
        f"- Missing labels: {primary_metrics['label_false_negative']}",
        "",
        "## Predicted class confidence",
        "",
        "| Predicted class | Predicted images | Avg conf | TP images | Extra images | Precision |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for pred_class in TARGET_CLASSES:
        item = tuning_breakdown["predicted_class_confidence"][pred_class]
        lines.append(
            f"| {pred_class} | {item['predicted_images']} | {item['avg_confidence']:.4f} | "
            f"{item['true_positive_images']} | {item['extra_false_positive_images']} | {item['precision']:.4f} |"
        )

    lines.extend(["", "## True class to predicted class", ""])
    for true_class in TARGET_CLASSES:
        lines.append(f"### true `{true_class}`")
        lines.append("")
        lines.append("| Predicted class | Count | Rate on true class | Avg conf |")
        lines.append("|---|---:|---:|---:|")
        for pred_class in TARGET_CLASSES:
            item = tuning_breakdown["true_to_pred"][true_class][pred_class]
            if item["predicted_on_true_images"] == 0:
                continue
            lines.append(
                f"| {pred_class} | {item['predicted_on_true_images']} | "
                f"{safe_div(item['predicted_on_true_images'], item['true_images']):.4f} | "
                f"{item['avg_confidence']:.4f} |"
            )
        lines.append("")

    lines.extend(["## Top missing label combinations", ""])
    for combo, count in tuning_breakdown["top_missing_combinations"].items():
        lines.append(f"- `{combo}`: {count}")
    lines.extend(["", "## Top extra label combinations", ""])
    for combo, count in tuning_breakdown["top_extra_combinations"].items():
        lines.append(f"- `{combo}`: {count}")
    lines.extend(["", "## Output files", ""])
    lines.append(f"- True-to-pred confidence CSV: `{path.parent / 'true_to_pred_confidence.csv'}`")
    lines.append(f"- Predicted-class confidence CSV: `{path.parent / 'predicted_class_confidence.csv'}`")
    lines.append(f"- Per-image comparison CSV: `{path.parent / 'image_label_comparison.csv'}`")
    lines.append(f"- Detection viewer HTML: `{path.parent / 'detection_viewer.html'}`")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def metric_delta(new_value: float, old_value: float) -> str:
    delta = new_value - old_value
    sign = "+" if delta >= 0 else ""
    return f"{sign}{delta:.4f}"


def count_delta(new_value: int, old_value: int) -> str:
    delta = new_value - old_value
    sign = "+" if delta >= 0 else ""
    return f"{sign}{delta}"


def write_tuned_summary(
    path: Path,
    metadata: dict[str, Any],
    baseline_metrics: dict[str, Any],
    tuned_metrics: dict[str, Any],
) -> None:
    lines = [
        "# Tuned Clothing Postprocess Summary",
        "",
        "## Rules applied",
        "",
        "- If `skirt` and `dress` are both detected, `skirt` confidence is multiplied by `3` for the rule decision, then the winner is selected.",
        "- If `dress` wins and a top (`short_sleeve` or `long_sleeve`) is also selected, the top must have confidence `>= 0.76`; otherwise the top is removed.",
        "",
        "## Compared with summary.md baseline",
        "",
        f"- Dataset: `{metadata['dataset']}`",
        f"- Model: `{metadata['model']}` on `{metadata['model_device']}`",
        f"- Threshold: `{tuned_metrics['threshold']:.2f}`",
        "",
        "| Metric | summary.md baseline | tuned | Delta |",
        "|---|---:|---:|---:|",
        (
            f"| Complete match accuracy | {pct(baseline_metrics['exact_match_accuracy'])} | "
            f"{pct(tuned_metrics['exact_match_accuracy'])} | {metric_delta(tuned_metrics['exact_match_accuracy'], baseline_metrics['exact_match_accuracy'])} |"
        ),
        (
            f"| Partial match rate | {pct(baseline_metrics['partial_match_rate'])} | "
            f"{pct(tuned_metrics['partial_match_rate'])} | {metric_delta(tuned_metrics['partial_match_rate'], baseline_metrics['partial_match_rate'])} |"
        ),
        (
            f"| Label precision | {pct(baseline_metrics['label_precision'])} | "
            f"{pct(tuned_metrics['label_precision'])} | {metric_delta(tuned_metrics['label_precision'], baseline_metrics['label_precision'])} |"
        ),
        (
            f"| Label recall | {pct(baseline_metrics['label_recall'])} | "
            f"{pct(tuned_metrics['label_recall'])} | {metric_delta(tuned_metrics['label_recall'], baseline_metrics['label_recall'])} |"
        ),
        (
            f"| Label F1 | {baseline_metrics['label_f1']:.4f} | "
            f"{tuned_metrics['label_f1']:.4f} | {metric_delta(tuned_metrics['label_f1'], baseline_metrics['label_f1'])} |"
        ),
        (
            f"| Extra labels | {baseline_metrics['label_false_positive']} | "
            f"{tuned_metrics['label_false_positive']} | {count_delta(tuned_metrics['label_false_positive'], baseline_metrics['label_false_positive'])} |"
        ),
        (
            f"| Missing labels | {baseline_metrics['label_false_negative']} | "
            f"{tuned_metrics['label_false_negative']} | {count_delta(tuned_metrics['label_false_negative'], baseline_metrics['label_false_negative'])} |"
        ),
        "",
        "## Per-class comparison",
        "",
        "| Class | Base precision | Tuned precision | Base recall | Tuned recall | Base F1 | Tuned F1 | F1 delta |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for label in TARGET_CLASSES:
        base = baseline_metrics["per_class"][label]
        tuned = tuned_metrics["per_class"][label]
        lines.append(
            f"| {label} | {base['precision']:.4f} | {tuned['precision']:.4f} | "
            f"{base['recall']:.4f} | {tuned['recall']:.4f} | "
            f"{base['f1']:.4f} | {tuned['f1']:.4f} | {metric_delta(tuned['f1'], base['f1'])} |"
        )

    lines.extend(
        [
            "",
            "## Output files",
            "",
            f"- Tuned summary: `{path.parent / 'summary.md'}`",
            f"- Tuned viewer: `{path.parent / 'detection_viewer.html'}`",
            f"- Per-image detections and bboxes: `{path.parent / 'image_label_comparison.csv'}`",
        ]
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def parse_thresholds(value: str) -> list[float]:
    thresholds = [float(item.strip()) for item in value.split(",") if item.strip()]
    if not thresholds:
        raise argparse.ArgumentTypeError("At least one threshold is required")
    return thresholds


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate the clothing model on YOLO image datasets and optional videos.")
    parser.add_argument("--dataset", default=r"C:\Users\pmach\Downloads\clothing_me.v1i.yolov11\train")
    parser.add_argument("--data-yaml", default=r"C:\Users\pmach\Downloads\clothing_me.v1i.yolov11\data.yaml")
    parser.add_argument("--output-dir", default="track_result/clothing_model_eval")
    parser.add_argument("--model", default="models/prepare_dataset.pt")
    parser.add_argument("--thresholds", type=parse_thresholds, default=parse_thresholds("0.25,0.50,0.70"))
    parser.add_argument("--primary-threshold", type=float, default=None)
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument("--imgsz", type=int, default=224)
    parser.add_argument("--inference-conf", type=float, default=None)
    parser.add_argument("--max-images", type=int, default=0)
    parser.add_argument("--max-dataset-samples", type=int, default=0)
    parser.add_argument(
        "--image-eval-mode",
        choices=["multilabel-person", "single-label"],
        default="multilabel-person",
        help="Use multilabel-person for person crops with multiple clothing labels per image.",
    )
    parser.add_argument(
        "--postprocess-mode",
        choices=["outfit", "raw"],
        default="outfit",
        help="outfit applies top/bottom/dress rules; raw keeps every detection above threshold.",
    )
    parser.add_argument(
        "--image-input-mode",
        choices=["full", "bbox-crop"],
        default="full",
        help="Use full image for already-cropped datasets, or crop from YOLO bbox.",
    )
    parser.add_argument("--video-short", default="", help="Video with short_sleeve and shorts only.")
    parser.add_argument("--video-long", default="", help="Video with long_sleeve and trousers only.")
    parser.add_argument("--video-short-start-frame", type=int, default=0)
    parser.add_argument("--video-short-end-frame", type=int, default=-1)
    parser.add_argument("--video-long-start-frame", type=int, default=0)
    parser.add_argument("--video-long-end-frame", type=int, default=-1)
    parser.add_argument("--detector-model", default="yolo11n.pt")
    parser.add_argument("--device", default="auto", help="Model device: auto, cpu, cuda, cuda:0, ...")
    parser.add_argument("--video-frame-stride", type=int, default=1)
    parser.add_argument("--video-max-frames", type=int, default=0)
    parser.add_argument("--person-confidence", type=float, default=0.25)
    parser.add_argument("--log-every", type=int, default=100)
    args = parser.parse_args()
    args.primary_threshold = args.primary_threshold if args.primary_threshold is not None else min(args.thresholds)
    args.inference_conf = args.inference_conf if args.inference_conf is not None else min(args.thresholds)

    output_dir = resolve_path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    predictor = YoloPredictor(resolve_path(args.model), args.device, args.imgsz, args.inference_conf)

    if args.image_eval_mode == "multilabel-person":
        rows, metadata = evaluate_dataset_multilabel(args, predictor)
        primary_metrics = multilabel_metrics(rows, args.primary_threshold, args.postprocess_mode)
        baseline_postprocess_mode = "outfit_base" if args.postprocess_mode == "outfit" else args.postprocess_mode
        baseline_metrics = multilabel_metrics(rows, args.primary_threshold, baseline_postprocess_mode)
        threshold_rows = multilabel_threshold_comparison(rows, args.thresholds, args.postprocess_mode)
        tuning_breakdown = multilabel_tuning_breakdowns(rows, args.primary_threshold, args.postprocess_mode)
        topk = {}
        fp_breakdown = {}
        fn_breakdown = {}
        mistakes = []
    else:
        rows, metadata = evaluate_dataset(args, predictor)
        primary_metrics = classification_metrics(rows, args.primary_threshold)
        threshold_rows = threshold_comparison(rows, args.thresholds)
        topk = top_k_accuracy(rows, args.top_k)
        fp_breakdown = false_positive_breakdown(rows, args.primary_threshold)
        fn_breakdown = false_negative_breakdown(rows, args.primary_threshold)
        mistakes = top_mistakes(rows, args.primary_threshold)
        tuning_breakdown = {}
        baseline_metrics = {}

    video_results: list[dict[str, Any]] = []
    if args.video_long or args.video_short:
        detector_device = predictor.device
        detector = YOLO(str(resolve_path(args.detector_model)))
        detector.to(detector_device)
        if args.video_short:
            video_results.append(
                evaluate_video(
                    resolve_path(args.video_short),
                    "video_1_short_sleeve_shorts",
                    {"short_sleeve", "shorts"},
                    args.video_short_start_frame,
                    args.video_short_end_frame,
                    args,
                    predictor,
                    detector,
                    detector_device,
                )
            )
        if args.video_long:
            video_results.append(
                evaluate_video(
                    resolve_path(args.video_long),
                    "video_2_long_sleeve_trousers",
                    {"long_sleeve", "trousers"},
                    args.video_long_start_frame,
                    args.video_long_end_frame,
                    args,
                    predictor,
                    detector,
                    detector_device,
                )
            )

    metrics = {
        "metadata": metadata,
        "primary_metrics": primary_metrics,
        "baseline_metrics": baseline_metrics,
        "threshold_comparison": threshold_rows,
        "top_k_accuracy": topk,
        "false_positive_breakdown": fp_breakdown,
        "false_negative_breakdown": fn_breakdown,
        "top_mistakes": mistakes,
        "tuning_breakdown": tuning_breakdown,
        "video_results": video_results,
        "predictions": rows,
    }
    (output_dir / "metrics.json").write_text(json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8")
    write_per_class_csv(output_dir / "per_class_metrics.csv", primary_metrics["per_class"])
    if args.image_eval_mode == "multilabel-person":
        write_image_label_comparison_csv(output_dir / "image_label_comparison.csv", rows)
        write_detection_viewer_html(output_dir / "detection_viewer.html", rows, args.primary_threshold)
        write_true_to_pred_confidence_csv(output_dir / "true_to_pred_confidence.csv", tuning_breakdown)
        write_predicted_class_confidence_csv(output_dir / "predicted_class_confidence.csv", tuning_breakdown)
        write_counter_csv(output_dir / "top_missing_combinations.csv", tuning_breakdown["top_missing_combinations"], "missing_labels")
        write_counter_csv(output_dir / "top_extra_combinations.csv", tuning_breakdown["top_extra_combinations"], "extra_labels")
        write_counter_csv(output_dir / "predicted_label_combinations.csv", tuning_breakdown["predicted_label_combinations"], "predicted_labels")
        write_counter_csv(output_dir / "ground_truth_label_combinations.csv", tuning_breakdown["ground_truth_label_combinations"], "ground_truth_labels")
        write_csv(
            output_dir / "threshold_comparison.csv",
            threshold_rows,
            [
                "threshold",
                "total_images",
                "exact_match_images",
                "partial_match_images",
                "exact_match_accuracy",
                "partial_match_rate",
                "label_precision",
                "label_recall",
                "label_f1",
                "label_false_positive",
                "label_false_negative",
            ],
        )
        write_multilabel_summary(output_dir / "summary.md", metadata, primary_metrics, threshold_rows, video_results)
        write_tuning_summary(output_dir / "tuning_summary.md", metadata, primary_metrics, tuning_breakdown)
        write_tuned_summary(output_dir / "tuned_summary.md", metadata, baseline_metrics, primary_metrics)
    else:
        write_confusion_matrix_csv(output_dir / "confusion_matrix.csv", primary_metrics["confusion_matrix"])
        write_confusion_matrix_png(output_dir / "confusion_matrix.png", primary_metrics["confusion_matrix"])
        write_breakdown_csv(output_dir / "false_positive_breakdown.csv", fp_breakdown, "predicted_class")
        write_breakdown_csv(output_dir / "false_negative_breakdown.csv", fn_breakdown, "true_class")
        write_csv(
            output_dir / "threshold_comparison.csv",
            threshold_rows,
            [
                "threshold",
                "total_samples",
                "total_accepted_predictions",
                "correct",
                "wrong",
                "accuracy",
                "accepted_accuracy",
                "rejected_no_prediction_count",
            ],
        )
        write_summary(
            output_dir / "summary.md",
            metadata,
            primary_metrics,
            topk,
            threshold_rows,
            fp_breakdown,
            fn_breakdown,
            mistakes,
            video_results,
        )

    print(
        json.dumps(
            {
                "image_eval_mode": args.image_eval_mode,
                "images_evaluated": primary_metrics.get("total_images", primary_metrics.get("total")),
                "complete_match_accuracy": primary_metrics.get("exact_match_accuracy"),
                "label_precision": primary_metrics.get("label_precision"),
                "label_recall": primary_metrics.get("label_recall"),
                "label_f1": primary_metrics.get("label_f1", primary_metrics.get("macro_f1")),
                "output_dir": str(output_dir),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
