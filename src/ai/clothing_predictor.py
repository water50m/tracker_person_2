"""
clothing_predictor.py — production clothing classifier and post-processing rules.

Moved from tests/evaluation/evaluate_clothing_model.py so this code
lives in src/ and can be imported by any flow without touching test files.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import numpy as np
import torch
from ultralytics import YOLO


# ── Class constants ───────────────────────────────────────────────────────────

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

PREDICTION_ALIASES: dict[str, str] = {
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


# ── Label normalisation ───────────────────────────────────────────────────────

def prediction_to_target(value: Any) -> str | None:
    raw = str(value).strip().lower().replace("-", "_")
    normalized = re.sub(r"\s+", " ", raw.replace("_", " ")).strip()
    compact = normalized.replace(" ", "_")
    return (
        PREDICTION_ALIASES.get(raw)
        or PREDICTION_ALIASES.get(normalized)
        or PREDICTION_ALIASES.get(compact)
    )


# ── YoloPredictor ─────────────────────────────────────────────────────────────

class YoloPredictor:
    def __init__(
        self,
        model_path: Path,
        device: str = "auto",
        imgsz: int = 224,
        conf: float | None = None,
        half: bool = False,
    ) -> None:
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
        kwargs: dict[str, Any] = {
            "verbose": False,
            "device": self.device,
            "imgsz": self.imgsz,
        }
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
                predictions.append({
                    "raw_class": raw_label,
                    "class": prediction_to_target(raw_label),
                    "confidence": float(probs[index].item()),
                    "bbox": None,
                })
            return predictions

        boxes = getattr(result, "boxes", None)
        if boxes is None or len(boxes) == 0:
            return []
        sorted_boxes = sorted(boxes, key=lambda box: float(box.conf.item()), reverse=True)
        for box in sorted_boxes[: max(top_n, 1)]:
            class_id = int(box.cls.item())
            raw_label = self._class_name(result.names, class_id)
            predictions.append({
                "raw_class": raw_label,
                "class": prediction_to_target(raw_label),
                "confidence": float(box.conf.item()),
                "bbox": [int(v) for v in box.xyxy[0].tolist()],
            })
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
        except Exception:
            self.last_results = []
            return [self.predict_top_n(image, top_n) for image in images]


# ── Post-processing rules ─────────────────────────────────────────────────────

def candidate_detections(
    top_predictions: list[dict[str, Any]], threshold: float
) -> list[dict[str, Any]]:
    detections = []
    for index, item in enumerate(top_predictions):
        class_name = item.get("class")
        confidence = float(item.get("confidence", 0.0))
        if class_name not in TARGET_CLASSES or confidence < threshold:
            continue
        detections.append({
            "id": index,
            "class": str(class_name),
            "raw_class": str(item.get("raw_class", class_name)),
            "confidence": confidence,
            "bbox": item.get("bbox"),
            "kept": False,
            "removed_reason": "",
        })
    return detections


def best_detection(
    detections: list[dict[str, Any]], classes: set[str]
) -> dict[str, Any] | None:
    matches = [det for det in detections if det["class"] in classes]
    return max(matches, key=lambda det: det["confidence"], default=None)


def _bbox_contained_ratio(bbox_a: list[int], bbox_b: list[int]) -> float:
    """Return the fraction of bbox_a's area that is covered by bbox_b.

    Returns 1.0 if bbox_a is fully inside bbox_b, 0.0 if no overlap.
    """
    if not bbox_a or not bbox_b or len(bbox_a) < 4 or len(bbox_b) < 4:
        return 0.0
    x1a, y1a, x2a, y2a = bbox_a
    x1b, y1b, x2b, y2b = bbox_b
    ix1, iy1 = max(x1a, x1b), max(y1a, y1b)
    ix2, iy2 = min(x2a, x2b), min(y2a, y2b)
    if ix2 <= ix1 or iy2 <= iy1:
        return 0.0
    inter = (ix2 - ix1) * (iy2 - iy1)
    area_a = max((x2a - x1a) * (y2a - y1a), 1)
    return inter / area_a


# Fraction of the smaller bbox that must be covered by the larger for it to be
# considered "fully contained" and eligible for removal.
_CONTAINMENT_THRESHOLD = 0.85


def postprocess_outfit_detections(
    top_predictions: list[dict[str, Any]], threshold: float
) -> dict[str, Any]:
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
        if rule_score(skirt_det) > dress_det["confidence"]:
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

        # ── BBox containment filter (non-dress only) ────────────────────────────
        # When both items have bboxes and one is almost fully inside the other
        # (≥ _CONTAINMENT_THRESHOLD), the contained item is likely a spurious
        # detection (e.g. a shorts box sitting inside a short_sleeve box).
        # Drop the contained item and substitute the next-best candidate from
        # that same slot.
        if len(selected) == 2:
            a_det, b_det = selected
            a_bbox = a_det.get("bbox")
            b_bbox = b_det.get("bbox")
            if a_bbox and b_bbox:
                a_in_b = _bbox_contained_ratio(a_bbox, b_bbox) >= _CONTAINMENT_THRESHOLD
                b_in_a = _bbox_contained_ratio(b_bbox, a_bbox) >= _CONTAINMENT_THRESHOLD
                if a_in_b or b_in_a:
                    # Which one is the contained (smaller) item?
                    contained = a_det if a_in_b else b_det
                    kept = b_det if a_in_b else a_det
                    removed_reasons[contained["id"]] = "removed_by_bbox_containment"

                    # Try next-best candidate from the same slot as the removed item
                    if contained["class"] in TOP_CLASSES:
                        alt_candidates = [
                            d for d in raw_detections
                            if d["class"] in TOP_CLASSES and d["id"] != contained["id"]
                        ]
                        alt = max(alt_candidates, key=lambda d: d["confidence"], default=None)
                    else:
                        alt_candidates = [
                            d for d in raw_detections
                            if d["class"] in BOTTOM_CLASSES and d["id"] != contained["id"]
                        ]
                        alt = max(alt_candidates, key=rule_score, default=None)

                    selected = [kept, alt] if alt is not None else [kept]

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


def raw_outfit_detections(
    top_predictions: list[dict[str, Any]], threshold: float
) -> dict[str, Any]:
    raw_detections = []
    for index, item in enumerate(top_predictions):
        class_name = item.get("class")
        confidence = float(item.get("confidence", 0.0))
        raw_detections.append({
            "id": index,
            "class": str(class_name) if class_name else None,
            "raw_class": str(item.get("raw_class", "")),
            "confidence": confidence,
            "bbox": item.get("bbox"),
            "kept": class_name in TARGET_CLASSES and confidence >= threshold,
            "removed_reason": "" if (class_name in TARGET_CLASSES and confidence >= threshold) else "threshold",
        })
    final_detections = [d for d in raw_detections if d["kept"]]
    return {
        "raw_detections": raw_detections,
        "final_detections": final_detections,
        "classes": sorted({det["class"] for det in final_detections if det["class"]}),
    }


def prediction_result(
    top_predictions: list[dict[str, Any]],
    threshold: float,
    postprocess_mode: str = "outfit",
) -> dict[str, Any]:
    if postprocess_mode == "raw":
        return raw_outfit_detections(top_predictions, threshold)
    return postprocess_outfit_detections(top_predictions, threshold)
