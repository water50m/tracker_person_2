from __future__ import annotations

import argparse
import asyncio
import csv
import json
import sys
import time
from pathlib import Path
from typing import Any

import cv2
import torch

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = PROJECT_ROOT / "src"
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from ai.detector import PersonDetector  # noqa: E402
from ai.feature_extractor import ClothingEmbedder  # noqa: E402
from ai.classifier import ClothingClassifier  # noqa: E402
from services.hybrid_tracker import HybridTracker, TrackFeatures  # noqa: E402
from src.ai.color_system import analyze_detailed_colors, get_color_groups  # noqa: E402
from src.config_loader import get_classifier_model_path, get_device  # noqa: E402
from tests.evaluation.metrics import (  # noqa: E402
    mot_identity_metrics,
    read_records,
    tracking_proxy_metrics,
    write_json,
)


def similarity_method_summary(threshold: float | None) -> dict[str, Any]:
    return {
        "threshold": threshold,
        "embedding": "cosine similarity between stored embedding vectors",
        "color_groups": "Jaccard/IoU similarity between color group key sets",
        "final_score": "average of available embedding and color-group scores",
        "recover_rule": "recover when final_score >= threshold",
        "note": "detailed_colors are stored in track history, but the current HybridTracker similarity function compares embedding and color_groups only.",
    }


def empty_reid_summary(enabled: bool, threshold: float | None = None) -> dict[str, Any]:
    summary: dict[str, Any] = {
        "enabled": enabled,
        "byte_id_new_events": 0,
        "reid_candidate_events": 0,
        "reid_attempts": 0,
        "reid_similarity_attempts": 0,
        "recovered_tracks": 0,
        "new_tracks": 0,
        "untracked_new_tracks": 0,
        "recover_score_events": [],
        "best_recover_score": None,
        "average_attempt_best_score": 0.0,
        "recovered_scores": [],
        "class_failed_crop_events": 0,
        "class_failed_crop_paths": [],
        "wrong_class_crop_events": 0,
        "wrong_class_crop_paths": [],
        "reid_confirmation_observations": 0,
        "confirmed_new_tracks": 0,
        "single_slot_recovered_tracks": 0,
        "events": [],
        "similarity_method": similarity_method_summary(threshold),
    }
    return summary


def resolve_eval_device(requested: str | None) -> str:
    device = requested or get_device()
    if device == "cuda" and not torch.cuda.is_available():
        print("[tracking-eval] CUDA requested but unavailable; falling back to CPU")
        return "cpu"
    if device not in {"cuda", "cpu"}:
        return "cuda" if torch.cuda.is_available() else "cpu"
    return device


def force_detector_device(detector: PersonDetector, device: str) -> None:
    if detector.device != device:
        detector.device = device
        detector.model.to(device)


def similarity_components(features1: TrackFeatures, features2: TrackFeatures) -> dict[str, Any]:
    scores: list[float] = []
    embedding_score = None
    color_group_score = None

    if features1.embedding and features2.embedding:
        try:
            emb1 = torch.tensor(features1.embedding, dtype=torch.float32).numpy()
            emb2 = torch.tensor(features2.embedding, dtype=torch.float32).numpy()
            dot_product = float((emb1 * emb2).sum())
            norm1 = float((emb1 * emb1).sum() ** 0.5)
            norm2 = float((emb2 * emb2).sum() ** 0.5)
            if norm1 > 0 and norm2 > 0:
                embedding_score = dot_product / (norm1 * norm2)
                scores.append(embedding_score)
        except Exception:
            embedding_score = None

    if features1.color_groups and features2.color_groups:
        try:
            set1 = set(features1.color_groups.keys())
            set2 = set(features2.color_groups.keys())
            if set1 and set2:
                color_group_score = len(set1 & set2) / len(set1 | set2)
                scores.append(color_group_score)
        except Exception:
            color_group_score = None

    final_score = sum(scores) / len(scores) if scores else 0.0
    return {
        "embedding_score": embedding_score,
        "color_group_score": color_group_score,
        "final_score": final_score,
        "score_count": len(scores),
    }


TOP_CLASSES = {"long_sleeve", "short_sleeve"}
BOTTOM_CLASSES = {"trousers", "shorts", "skirt", "jeans"}


def crop_xyxy(image, bbox):
    if bbox is None:
        return None
    x1, y1, x2, y2 = map(int, bbox)
    h, w = image.shape[:2]
    x1 = max(0, min(w, x1))
    x2 = max(0, min(w, x2))
    y1 = max(0, min(h, y1))
    y2 = max(0, min(h, y2))
    if x2 <= x1 or y2 <= y1:
        return None
    return image[y1:y2, x1:x2]


def bbox_area_ratio(image, bbox) -> float:
    if bbox is None:
        return 1.0
    x1, y1, x2, y2 = map(int, bbox)
    h, w = image.shape[:2]
    if h <= 0 or w <= 0:
        return 0.0
    x1 = max(0, min(w, x1))
    x2 = max(0, min(w, x2))
    y1 = max(0, min(h, y1))
    y2 = max(0, min(h, y2))
    if x2 <= x1 or y2 <= y1:
        return 0.0
    return ((x2 - x1) * (y2 - y1)) / float(w * h)


def profile_slot_is_usable(
    profile: dict[str, Any] | None,
    slot: str,
    min_confidence: float = 0.25,
    min_area_ratio: float = 0.03,
) -> bool:
    if not profile:
        return False
    item = profile.get(slot)
    if not item or not item.get("class_name"):
        return False
    if float(item.get("confidence", 0.0)) < min_confidence:
        return False
    area_ratio = item.get("bbox_area_ratio")
    if area_ratio is not None and float(area_ratio) < min_area_ratio:
        return False
    return bool(item.get("detailed_colors"))


def select_clothing_profile(
    person_crop,
    classifier: ClothingClassifier,
    disable_color: bool = False,
    expected_classes: set[str] | None = None,
) -> dict[str, Any]:
    predictions = classifier.predict_top_n(person_crop, top_n=5)
    profile: dict[str, Any] = {
        "top": None,
        "bottom": None,
        "classes": {},
        "predictions": [
            {"class_name": name, "confidence": float(conf), "bbox": list(bbox) if bbox else None}
            for name, conf, bbox in predictions
        ],
        "unexpected_predictions": [
            {"class_name": name, "confidence": float(conf), "bbox": list(bbox) if bbox else None}
            for name, conf, bbox in predictions
            if expected_classes and name != "Unknown" and name not in expected_classes
        ],
    }

    for class_name, confidence, bbox in predictions:
        if class_name == "Unknown":
            continue
        if expected_classes and class_name not in expected_classes:
            continue
        slot = None
        if class_name in TOP_CLASSES:
            slot = "top"
        elif class_name in BOTTOM_CLASSES or class_name not in TOP_CLASSES:
            slot = "bottom"
        if slot is None or profile[slot] is not None:
            continue

        item_crop = crop_xyxy(person_crop, bbox) if bbox is not None else None
        if item_crop is None:
            item_crop = person_crop
        detailed_colors = {} if disable_color else analyze_detailed_colors(item_crop)
        profile[slot] = {
            "class_name": class_name,
            "confidence": float(confidence),
            "bbox": list(bbox) if bbox else None,
            "bbox_area_ratio": bbox_area_ratio(person_crop, bbox),
            "detailed_colors": detailed_colors,
            "top_colors": dict(sorted(detailed_colors.items(), key=lambda kv: kv[1], reverse=True)[:8]),
        }
        profile["classes"][slot] = class_name

        if profile["top"] is not None and profile["bottom"] is not None:
            break

    return profile


def clothing_class_gate(new_profile: dict[str, Any], lost_profile: dict[str, Any] | None) -> dict[str, Any]:
    if not lost_profile:
        return {
            "class_match": False,
            "matched_slots": [],
            "matched_pairs": [],
            "mismatched_slots": [],
            "reason": "missing_lost_clothing_profile",
        }

    new_classes = {
        slot: class_name
        for slot, class_name in new_profile.get("classes", {}).items()
        if slot in {"top", "bottom"} and class_name
    }
    lost_classes = {
        slot: class_name
        for slot, class_name in lost_profile.get("classes", {}).items()
        if slot in {"top", "bottom"} and class_name
    }
    if not new_classes or not lost_classes:
        return {
            "class_match": False,
            "matched_slots": [],
            "matched_pairs": [],
            "mismatched_slots": [],
            "missing_slots": [
                slot
                for slot in ("top", "bottom")
                if slot not in new_classes or slot not in lost_classes
            ],
            "reason": "missing_detected_clothing_class",
        }

    def make_matched_pairs() -> list[dict[str, str]]:
        pairs = []
        used_lost_slots = set()
        for new_slot, new_class in new_classes.items():
            for lost_slot, lost_class in lost_classes.items():
                if lost_slot in used_lost_slots or new_class != lost_class:
                    continue
                pairs.append({
                    "new_slot": new_slot,
                    "lost_slot": lost_slot,
                    "class_name": new_class,
                })
                used_lost_slots.add(lost_slot)
                break
        return pairs

    matched_pairs = make_matched_pairs()
    matched_slots = [
        pair["new_slot"]
        for pair in matched_pairs
        if pair["new_slot"] == pair["lost_slot"]
    ]
    mismatched_slots = []
    missing_slots = [
        slot
        for slot in ("top", "bottom")
        if slot not in new_classes or slot not in lost_classes
    ]

    if len(new_classes) == 2 and len(lost_classes) == 2:
        for slot in ("top", "bottom"):
            new_class = new_classes.get(slot)
            lost_class = lost_classes.get(slot)
            if new_class == lost_class:
                continue
            mismatched_slots.append({
                "slot": slot,
                "new_class": new_class,
                "lost_class": lost_class,
            })
        if mismatched_slots:
            return {
                "class_match": False,
                "matched_slots": matched_slots,
                "matched_pairs": matched_pairs,
                "mismatched_slots": mismatched_slots,
                "missing_slots": missing_slots,
                "reason": "full_profile_class_mismatch",
            }
        return {
            "class_match": True,
            "matched_slots": ["top", "bottom"],
            "matched_pairs": [
                {"new_slot": "top", "lost_slot": "top", "class_name": new_classes["top"]},
                {"new_slot": "bottom", "lost_slot": "bottom", "class_name": new_classes["bottom"]},
            ],
            "mismatched_slots": [],
            "missing_slots": [],
            "reason": "full_profile_match",
        }

    if not matched_pairs:
        return {
            "class_match": False,
            "matched_slots": [],
            "matched_pairs": [],
            "mismatched_slots": mismatched_slots,
            "missing_slots": missing_slots,
            "reason": "no_shared_matching_clothing_class",
        }

    for slot in set(new_classes) & set(lost_classes):
        new_class = new_classes.get(slot)
        lost_class = lost_classes.get(slot)
        if new_class == lost_class:
            continue
        mismatched_slots.append({
            "slot": slot,
            "new_class": new_class,
            "lost_class": lost_class,
        })

    return {
        "class_match": True,
        "matched_slots": matched_slots,
        "matched_pairs": matched_pairs,
        "mismatched_slots": mismatched_slots,
        "missing_slots": missing_slots,
        "reason": "partial_profile_match",
    }


def color_distribution_score(colors1: dict[str, float], colors2: dict[str, float]) -> float | None:
    if not colors1 or not colors2:
        return None
    keys = set(colors1) | set(colors2)
    l1_distance = sum(abs(float(colors1.get(key, 0.0)) - float(colors2.get(key, 0.0))) for key in keys)
    return max(0.0, 1.0 - (l1_distance / 200.0))


def cosine_score(vec1, vec2) -> float | None:
    if vec1 is None or vec2 is None:
        return None
    emb1 = torch.tensor(vec1, dtype=torch.float32).numpy()
    emb2 = torch.tensor(vec2, dtype=torch.float32).numpy()
    if emb1.size == 0 or emb1.shape != emb2.shape:
        return None
    dot_product = float((emb1 * emb2).sum())
    norm1 = float((emb1 * emb1).sum() ** 0.5)
    norm2 = float((emb2 * emb2).sum() ** 0.5)
    if norm1 <= 0 or norm2 <= 0:
        return None
    return dot_product / (norm1 * norm2)


def average_embedding(vectors: list[list[float] | None]) -> list[float] | None:
    valid_vectors = [
        torch.tensor(vec, dtype=torch.float32)
        for vec in vectors
        if vec
    ]
    if not valid_vectors:
        return None
    shapes = {tuple(vec.shape) for vec in valid_vectors}
    if len(shapes) != 1:
        return valid_vectors[-1].tolist()
    return torch.stack(valid_vectors).mean(dim=0).tolist()


def average_color_maps(color_maps: list[dict[str, float]]) -> dict[str, float]:
    valid_maps = [color_map for color_map in color_maps if color_map]
    if not valid_maps:
        return {}
    keys = set().union(*(color_map.keys() for color_map in valid_maps))
    return {
        key: sum(float(color_map.get(key, 0.0)) for color_map in valid_maps) / len(valid_maps)
        for key in keys
    }


def color_ranges(color_maps: list[dict[str, float]]) -> dict[str, dict[str, float]]:
    valid_maps = [color_map for color_map in color_maps if color_map]
    if not valid_maps:
        return {}
    keys = set().union(*(color_map.keys() for color_map in valid_maps))
    ranges = {}
    for key in keys:
        values = [float(color_map.get(key, 0.0)) for color_map in valid_maps]
        ranges[key] = {
            "min": min(values),
            "max": max(values),
            "avg": sum(values) / len(values),
        }
    return ranges


def parse_expected_classes(value: str) -> set[str]:
    return {
        item.strip()
        for item in value.split(",")
        if item.strip()
    }


def add_timing(timings: dict[str, dict[str, float]], name: str, started_at: float) -> None:
    elapsed_ms = (time.perf_counter() - started_at) * 1000.0
    bucket = timings.setdefault(name, {"total_ms": 0.0, "count": 0})
    bucket["total_ms"] += elapsed_ms
    bucket["count"] += 1


def summarize_timings(timings: dict[str, dict[str, float]]) -> dict[str, dict[str, float]]:
    return {
        name: {
            "total_ms": values["total_ms"],
            "count": int(values["count"]),
            "avg_ms": values["total_ms"] / values["count"] if values["count"] else 0.0,
        }
        for name, values in sorted(timings.items())
    }


def color_range_score(colors: dict[str, float], ranges: dict[str, dict[str, float]]) -> float | None:
    if not colors or not ranges:
        return None
    keys = set(colors) | set(ranges)
    distance = 0.0
    for key in keys:
        value = float(colors.get(key, 0.0))
        bounds = ranges.get(key, {"min": 0.0, "max": 0.0})
        low = float(bounds.get("min", 0.0))
        high = float(bounds.get("max", 0.0))
        if value < low:
            distance += low - value
        elif value > high:
            distance += value - high
    return max(0.0, 1.0 - (distance / 200.0))


def append_track_profile_history(
    history: dict[int, list[dict[str, Any]]],
    our_id: int,
    frame_number: int,
    features: TrackFeatures,
    profile: dict[str, Any],
    limit: int,
) -> None:
    entries = history.setdefault(our_id, [])
    entries.append({
        "frame": frame_number,
        "embedding": features.embedding,
        "clothes": features.clothes,
        "profile": profile,
    })
    if limit > 0 and len(entries) > limit:
        del entries[:len(entries) - limit]


def aggregate_track_profile(
    entries: list[dict[str, Any]],
    slot_history_limit: int = 10,
) -> tuple[TrackFeatures | None, dict[str, Any] | None]:
    if not entries:
        return None, None

    aggregate_profile: dict[str, Any] = {
        "top": None,
        "bottom": None,
        "classes": {},
        "class_counts": {},
        "slot_seen_counts": {},
        "slot_coverage": {},
        "frames": [entry["frame"] for entry in entries],
        "history_size": len(entries),
    }

    clothes = []
    for slot in ("top", "bottom"):
        slot_items = []
        class_counts: dict[str, int] = {}
        for entry in entries:
            profile = entry.get("profile", {})
            item = profile.get(slot)
            if not item:
                continue
            class_name = item.get("class_name")
            if not class_name:
                continue
            if not profile_slot_is_usable(profile, slot):
                continue
            slot_items.append(item)
            class_counts[class_name] = class_counts.get(class_name, 0) + 1

        aggregate_profile["class_counts"][slot] = class_counts
        aggregate_profile["slot_seen_counts"][slot] = len(slot_items)
        aggregate_profile["slot_coverage"][slot] = len(slot_items) / len(entries)
        if not slot_items:
            clothes.append(None)
            continue

        majority_class = max(class_counts.items(), key=lambda kv: kv[1])[0]
        matching_items = [
            item
            for item in slot_items
            if item.get("class_name") == majority_class
        ]
        majority_items = matching_items[-slot_history_limit:] if slot_history_limit > 0 else matching_items
        color_maps = [item.get("detailed_colors", {}) for item in majority_items]
        avg_colors = average_color_maps(color_maps)
        ranges = color_ranges(color_maps)
        aggregate_profile[slot] = {
            "class_name": majority_class,
            "confidence": sum(float(item.get("confidence", 0.0)) for item in majority_items) / len(majority_items),
            "vote_count": len(majority_items),
            "observed_count": len(slot_items),
            "selected_total_count": len(matching_items),
            "slot_history_limit": slot_history_limit,
            "detailed_colors": avg_colors,
            "color_ranges": ranges,
            "top_colors": dict(sorted(avg_colors.items(), key=lambda kv: kv[1], reverse=True)[:8]),
        }
        aggregate_profile["classes"][slot] = majority_class
        clothes.append(majority_class)

    embedding = average_embedding([entry.get("embedding") for entry in entries])
    aggregate_features = TrackFeatures(
        detailed_colors={},
        color_groups={},
        embedding=embedding,
        clothes=clothes,
        last_seen=time.time(),
        frame_number=entries[-1]["frame"],
    )
    return aggregate_features, aggregate_profile


def reid_score_from_pairs(
    embedding: float | None,
    shirt_color: float | None,
    pants_color: float | None,
) -> tuple[float, int]:
    scores = [score for score in (embedding, shirt_color, pants_color) if score is not None]
    return (sum(scores) / len(scores), len(scores)) if scores else (0.0, 0)


def clothing_gated_reid_components(
    new_features: TrackFeatures,
    lost_features: TrackFeatures,
    new_profile: dict[str, Any],
    lost_profile: dict[str, Any] | None,
) -> dict[str, Any]:
    gate = clothing_class_gate(new_profile, lost_profile)
    if not gate["class_match"]:
        return {
            "class_match": False,
            "score": 0.0,
            "embedding_score": None,
            "shirt_color_score": None,
            "pants_color_score": None,
            "matched_slots": gate.get("matched_slots", []),
            "matched_pairs": gate.get("matched_pairs", []),
            "mismatched_slots": gate.get("mismatched_slots", []),
            "missing_slots": gate.get("missing_slots", []),
            "reason": gate["reason"],
        }

    embedding = cosine_score(new_features.embedding, lost_features.embedding)
    shirt_color = None
    pants_color = None
    shirt_range_color = None
    pants_range_color = None
    shirt_scores = []
    pants_scores = []
    shirt_range_scores = []
    pants_range_scores = []
    for pair in gate.get("matched_pairs", []):
        new_slot = pair["new_slot"]
        lost_slot = pair["lost_slot"]
        color_score = color_distribution_score(
            new_profile[new_slot]["detailed_colors"],
            lost_profile[lost_slot]["detailed_colors"],
        )
        if color_score is None:
            color_score = 0.0
        range_score = color_range_score(
            new_profile[new_slot]["detailed_colors"],
            lost_profile[lost_slot].get("color_ranges", {}),
        )
        if range_score is None:
            range_score = color_score
        if pair["class_name"] in TOP_CLASSES or new_slot == "top" or lost_slot == "top":
            shirt_scores.append(color_score)
            shirt_range_scores.append(range_score)
        elif pair["class_name"] in BOTTOM_CLASSES or new_slot == "bottom" or lost_slot == "bottom":
            pants_scores.append(color_score)
            pants_range_scores.append(range_score)
    if shirt_scores:
        shirt_color = sum(shirt_scores) / len(shirt_scores)
    if pants_scores:
        pants_color = sum(pants_scores) / len(pants_scores)
    if shirt_range_scores:
        shirt_range_color = sum(shirt_range_scores) / len(shirt_range_scores)
    if pants_range_scores:
        pants_range_color = sum(pants_range_scores) / len(pants_range_scores)

    average_score, average_score_count = reid_score_from_pairs(embedding, shirt_color, pants_color)
    range_score, range_score_count = reid_score_from_pairs(embedding, shirt_range_color, pants_range_color)
    score = average_score
    score_count = average_score_count
    score_mode = "average"

    return {
        "class_match": True,
        "score": score,
        "average_score": average_score,
        "range_score": range_score,
        "score_mode": score_mode,
        "embedding_score": embedding,
        "shirt_color_score": shirt_color,
        "pants_color_score": pants_color,
        "shirt_color_range_score": shirt_range_color,
        "pants_color_range_score": pants_range_color,
        "score_count": score_count,
        "matched_slots": gate["matched_slots"],
        "matched_pairs": gate.get("matched_pairs", []),
        "mismatched_slots": gate.get("mismatched_slots", []),
        "missing_slots": gate.get("missing_slots", []),
        "reason": "ok" if score_count else "missing_available_score",
    }


def resize_to_height(image, height: int):
    h, w = image.shape[:2]
    if h <= 0 or w <= 0:
        return image
    new_w = max(1, int(w * (height / h)))
    return cv2.resize(image, (new_w, height))


def save_recovered_crop_pair(
    output_dir: Path,
    frame_number: int,
    byte_id: int | None,
    our_id: int,
    score: float | None,
    current_crop,
    lost_snapshot: dict[str, Any] | None,
) -> dict[str, Any]:
    crop_dir = output_dir / "recovered_crops" / f"frame_{frame_number:05d}_our_{our_id}_byte_{byte_id}"
    crop_dir.mkdir(parents=True, exist_ok=True)
    score_label = "na" if score is None else f"{score:.3f}".replace(".", "p")

    recovered_path = crop_dir / f"recovered_frame_{frame_number:05d}_our_{our_id}_score_{score_label}.jpg"
    cv2.imwrite(str(recovered_path), current_crop)

    paths: dict[str, Any] = {
        "crop_dir": str(crop_dir),
        "recovered_crop": str(recovered_path),
        "lost_crop": None,
        "pair_crop": None,
        "lost_frame": None,
        "recovered_frame": frame_number,
    }

    if lost_snapshot and lost_snapshot.get("crop") is not None:
        lost_frame = lost_snapshot.get("frame")
        lost_path = crop_dir / f"lost_last_seen_frame_{lost_frame:05d}_our_{our_id}.jpg"
        cv2.imwrite(str(lost_path), lost_snapshot["crop"])
        paths["lost_crop"] = str(lost_path)
        paths["lost_frame"] = lost_frame

        left = resize_to_height(lost_snapshot["crop"], 240)
        right = resize_to_height(current_crop, 240)
        pair = cv2.hconcat([left, right])
        pair_path = crop_dir / f"pair_lost_{lost_frame:05d}_recovered_{frame_number:05d}_our_{our_id}.jpg"
        cv2.imwrite(str(pair_path), pair)
        paths["pair_crop"] = str(pair_path)

    return paths


def safe_path_part(value: Any) -> str:
    text = str(value if value is not None else "none")
    return "".join(ch if ch.isalnum() or ch in {"-", "_"} else "_" for ch in text)[:80]


def save_class_failed_crop_pair(
    output_dir: Path,
    frame_number: int,
    byte_id: int | None,
    current_crop,
    candidate: dict[str, Any],
    lost_snapshot: dict[str, Any] | None,
) -> dict[str, Any]:
    lost_our_id = candidate.get("lost_our_id")
    reason = safe_path_part(candidate.get("reason", "class_failed"))
    crop_dir = (
        output_dir
        / "class_failed_crops"
        / f"frame_{frame_number:05d}_byte_{byte_id}_lost_{lost_our_id}_{reason}"
    )
    crop_dir.mkdir(parents=True, exist_ok=True)

    new_path = crop_dir / f"new_frame_{frame_number:05d}_byte_{byte_id}.jpg"
    cv2.imwrite(str(new_path), current_crop)

    paths: dict[str, Any] = {
        "crop_dir": str(crop_dir),
        "new_crop": str(new_path),
        "lost_crop": None,
        "pair_crop": None,
        "lost_frame": None,
        "new_frame": frame_number,
        "lost_our_id": lost_our_id,
        "reason": candidate.get("reason"),
    }

    if lost_snapshot and lost_snapshot.get("crop") is not None:
        lost_frame = lost_snapshot.get("frame")
        lost_path = crop_dir / f"lost_last_seen_frame_{lost_frame:05d}_our_{lost_our_id}.jpg"
        cv2.imwrite(str(lost_path), lost_snapshot["crop"])
        paths["lost_crop"] = str(lost_path)
        paths["lost_frame"] = lost_frame

        left = resize_to_height(lost_snapshot["crop"], 240)
        right = resize_to_height(current_crop, 240)
        pair = cv2.hconcat([left, right])
        pair_path = crop_dir / f"pair_lost_{lost_frame:05d}_new_{frame_number:05d}_lost_{lost_our_id}.jpg"
        cv2.imwrite(str(pair_path), pair)
        paths["pair_crop"] = str(pair_path)

    metadata = {
        "frame": frame_number,
        "byte_id": byte_id,
        "lost_our_id": lost_our_id,
        "reason": candidate.get("reason"),
        "class_match": candidate.get("class_match"),
        "score": candidate.get("score"),
        "matched_pairs": candidate.get("matched_pairs", []),
        "mismatched_slots": candidate.get("mismatched_slots", []),
        "missing_slots": candidate.get("missing_slots", []),
        "average_score": candidate.get("average_score"),
        "range_score": candidate.get("range_score"),
        "score_mode": candidate.get("score_mode"),
        "embedding_score": candidate.get("embedding_score"),
        "shirt_color_score": candidate.get("shirt_color_score"),
        "pants_color_score": candidate.get("pants_color_score"),
        "shirt_color_range_score": candidate.get("shirt_color_range_score"),
        "pants_color_range_score": candidate.get("pants_color_range_score"),
        "lost_profile_source": candidate.get("lost_profile_source"),
        "lost_clothes": candidate.get("lost_clothes"),
        "new_clothes": candidate.get("new_clothes"),
        "lost_clothing_profile": candidate.get("lost_clothing_profile"),
        "new_clothing_profile": candidate.get("new_clothing_profile"),
        "paths": paths,
    }
    metadata_path = crop_dir / "metadata.json"
    with metadata_path.open("w", encoding="utf-8") as f:
        json.dump(metadata, f, ensure_ascii=False, indent=2)
    paths["metadata"] = str(metadata_path)

    return paths


def save_unexpected_class_crops(
    output_dir: Path,
    frame_number: int,
    byte_id: int | None,
    person_crop,
    profile: dict[str, Any],
) -> list[dict[str, Any]]:
    saved = []
    for index, prediction in enumerate(profile.get("unexpected_predictions", [])):
        class_name = prediction.get("class_name")
        confidence = float(prediction.get("confidence", 0.0))
        bbox = prediction.get("bbox")
        item_crop = crop_xyxy(person_crop, bbox) if bbox is not None else None
        if item_crop is None:
            item_crop = person_crop
        crop_dir = (
            output_dir
            / "wrong_class_crops"
            / f"frame_{frame_number:05d}_byte_{byte_id}_{safe_path_part(class_name)}_{index}"
        )
        crop_dir.mkdir(parents=True, exist_ok=True)
        confidence_label = f"{confidence:.3f}".replace(".", "p")
        crop_path = crop_dir / f"class_{safe_path_part(class_name)}_conf_{confidence_label}.jpg"
        cv2.imwrite(str(crop_path), item_crop)
        metadata = {
            "frame": frame_number,
            "byte_id": byte_id,
            "class_name": class_name,
            "confidence": confidence,
            "bbox": bbox,
            "expected_classes_note": "This clip is expected to contain long_sleeve and trousers only.",
            "crop": str(crop_path),
        }
        metadata_path = crop_dir / "metadata.json"
        with metadata_path.open("w", encoding="utf-8") as f:
            json.dump(metadata, f, ensure_ascii=False, indent=2)
        saved.append({
            "frame": frame_number,
            "byte_id": byte_id,
            "class_name": class_name,
            "confidence": confidence,
            "crop": str(crop_path),
            "metadata": str(metadata_path),
        })
    return saved


def remap_records_for_recovery(
    records: list[dict[str, Any]],
    byte_id: int,
    provisional_our_id: int,
    recovered_our_id: int,
) -> None:
    for record in records:
        if (
            record.get("byte_track_id") == byte_id
            and record.get("persistent_id") == provisional_our_id
        ):
            record["track_id"] = recovered_our_id
            record["persistent_id"] = recovered_our_id


def candidate_slot_scores(candidate: dict[str, Any]) -> dict[str, float]:
    embedding = candidate.get("embedding_score")
    slot_scores: dict[str, float] = {}
    matched_slots = {
        pair.get("new_slot")
        for pair in candidate.get("matched_pairs", [])
    } | {
        pair.get("lost_slot")
        for pair in candidate.get("matched_pairs", [])
    }
    if "top" in matched_slots and candidate.get("shirt_color_score") is not None:
        score, _ = reid_score_from_pairs(embedding, candidate.get("shirt_color_score"), None)
        slot_scores["top"] = score
    if "bottom" in matched_slots and candidate.get("pants_color_score") is not None:
        score, _ = reid_score_from_pairs(embedding, None, candidate.get("pants_color_score"))
        slot_scores["bottom"] = score
    return slot_scores


def single_slot_state_from_counts(
    counts: dict[str, int | float],
    total: int,
    min_coverage: float,
    missing_max_coverage: float,
    dominance_ratio: float,
    missing_max_count: int = 3,
) -> str | None:
    if total <= 0:
        return None
    top = float(counts.get("top", 0))
    bottom = float(counts.get("bottom", 0))
    top_coverage = top / total
    bottom_coverage = bottom / total
    if (
        top_coverage >= min_coverage
        and (bottom_coverage <= missing_max_coverage or bottom <= missing_max_count)
        and top / max(bottom, 1.0) >= dominance_ratio
    ):
        return "top"
    if (
        bottom_coverage >= min_coverage
        and (top_coverage <= missing_max_coverage or top <= missing_max_count)
        and bottom / max(top, 1.0) >= dominance_ratio
    ):
        return "bottom"
    return None


def single_slot_state_from_profile(
    profile: dict[str, Any] | None,
    min_coverage: float,
    missing_max_coverage: float,
    dominance_ratio: float,
) -> str | None:
    if not profile:
        return None
    counts = profile.get("slot_seen_counts")
    total = int(profile.get("history_size") or 0)
    if counts and total > 0:
        return single_slot_state_from_counts(
            counts,
            total,
            min_coverage,
            missing_max_coverage,
            dominance_ratio,
        )
    single_counts = {
        "top": 1 if profile_slot_is_usable(profile, "top") else 0,
        "bottom": 1 if profile_slot_is_usable(profile, "bottom") else 0,
    }
    return single_slot_state_from_counts(
        single_counts,
        1,
        min_coverage,
        missing_max_coverage,
        dominance_ratio,
    )


def update_confirmation_state(
    pending_state: dict[str, Any],
    score_event: dict[str, Any] | None,
    threshold: float,
    confirmation_frames: int,
    min_hits: int,
    single_slot_enabled: bool,
    single_slot_min_hits: int,
    single_slot_threshold: float,
    single_slot_min_coverage: float,
    single_slot_missing_max_coverage: float,
    single_slot_dominance_ratio: float,
    single_slot_ambiguity_margin: float,
) -> tuple[bool, int | None, int, str]:
    pending_state["observations"] += 1
    best_lost_id = None
    best_hits = 0
    recovery_mode = "both_slots"

    if score_event is not None:
        score_event["confirmation_observation"] = pending_state["observations"]
        score_event["confirmation_frames"] = confirmation_frames
        score_event["confirmation_min_hits"] = min_hits
        slot_hit_counts = pending_state.setdefault("slot_hit_counts", {})
        single_slot_hit_counts = pending_state.setdefault("single_slot_hit_counts", {})
        single_slot_score_sums = pending_state.setdefault("single_slot_score_sums", {})
        new_slot_seen_counts = pending_state.setdefault("new_slot_seen_counts", {"top": 0, "bottom": 0})
        new_profile = score_event.get("new_clothing_profile") or {}
        for slot in ("top", "bottom"):
            if profile_slot_is_usable(new_profile, slot):
                new_slot_seen_counts[slot] = new_slot_seen_counts.get(slot, 0) + 1
        score_event["new_slot_seen_counts"] = dict(new_slot_seen_counts)
        score_event["new_single_slot_state"] = single_slot_state_from_counts(
            new_slot_seen_counts,
            pending_state["observations"],
            single_slot_min_coverage,
            single_slot_missing_max_coverage,
            single_slot_dominance_ratio,
        )
        frame_slot_hits = {}
        frame_single_slot_hits = {}
        for candidate in score_event.get("candidate_scores", []):
            if not candidate.get("class_match"):
                continue
            lost_id = candidate.get("lost_our_id")
            if lost_id is None:
                continue
            slot_scores = candidate_slot_scores(candidate)
            for slot, slot_score in slot_scores.items():
                if slot_score < threshold:
                    pass
                else:
                    lost_counts = slot_hit_counts.setdefault(lost_id, {"top": 0, "bottom": 0})
                    lost_counts[slot] = lost_counts.get(slot, 0) + 1
                    frame_slot_hits.setdefault(lost_id, {})[slot] = slot_score
                if slot_score >= single_slot_threshold:
                    single_counts = single_slot_hit_counts.setdefault(lost_id, {"top": 0, "bottom": 0})
                    single_counts[slot] = single_counts.get(slot, 0) + 1
                    score_sums = single_slot_score_sums.setdefault(lost_id, {"top": 0.0, "bottom": 0.0})
                    score_sums[slot] = score_sums.get(slot, 0.0) + slot_score
                    frame_single_slot_hits.setdefault(lost_id, {})[slot] = slot_score
        score_event["confirmation_frame_slot_hits"] = {
            str(lost_id): slots
            for lost_id, slots in frame_slot_hits.items()
        }
        score_event["single_slot_frame_hits"] = {
            str(lost_id): slots
            for lost_id, slots in frame_single_slot_hits.items()
        }

        pending_state.setdefault("score_events", []).append(score_event)

    slot_hit_counts = pending_state.get("slot_hit_counts", {})
    if slot_hit_counts:
        best_lost_id, counts = max(
            slot_hit_counts.items(),
            key=lambda kv: min(kv[1].get("top", 0), kv[1].get("bottom", 0)),
        )
        best_hits = min(counts.get("top", 0), counts.get("bottom", 0))

    if score_event is not None:
        score_event["confirmation_slot_hits_by_lost_id"] = {
            str(lost_id): {
                "top": counts.get("top", 0),
                "bottom": counts.get("bottom", 0),
                "both_min": min(counts.get("top", 0), counts.get("bottom", 0)),
            }
            for lost_id, counts in slot_hit_counts.items()
        }
        score_event["confirmation_hits_by_lost_id"] = {
            str(lost_id): min(counts.get("top", 0), counts.get("bottom", 0))
            for lost_id, counts in slot_hit_counts.items()
        }
        score_event["confirmation_best_lost_id"] = best_lost_id
        score_event["confirmation_best_hits"] = best_hits

    if best_hits >= min_hits:
        return True, best_lost_id, best_hits, recovery_mode

    if not single_slot_enabled:
        return False, best_lost_id, best_hits, recovery_mode

    new_counts = pending_state.get("new_slot_seen_counts", {"top": 0, "bottom": 0})
    new_single_slot = single_slot_state_from_counts(
        new_counts,
        pending_state["observations"],
        single_slot_min_coverage,
        single_slot_missing_max_coverage,
        single_slot_dominance_ratio,
    )
    single_slot_hit_counts = pending_state.get("single_slot_hit_counts", {})
    single_slot_score_sums = pending_state.get("single_slot_score_sums", {})
    single_slot_candidates = []
    if score_event is not None and new_single_slot is not None:
        for candidate in score_event.get("candidate_scores", []):
            if not candidate.get("class_match"):
                continue
            lost_id = candidate.get("lost_our_id")
            if lost_id is None:
                continue
            lost_single_slot = single_slot_state_from_profile(
                candidate.get("lost_clothing_profile"),
                single_slot_min_coverage,
                single_slot_missing_max_coverage,
                single_slot_dominance_ratio,
            )
            if lost_single_slot != new_single_slot:
                continue
            hits = single_slot_hit_counts.get(lost_id, {}).get(new_single_slot, 0)
            score_sum = single_slot_score_sums.get(lost_id, {}).get(new_single_slot, 0.0)
            avg_score = score_sum / hits if hits else 0.0
            if hits >= single_slot_min_hits and avg_score >= single_slot_threshold:
                single_slot_candidates.append({
                    "lost_our_id": lost_id,
                    "slot": new_single_slot,
                    "hits": hits,
                    "avg_score": avg_score,
                    "lost_single_slot_state": lost_single_slot,
                    "new_single_slot_state": new_single_slot,
                })

    if score_event is not None:
        score_event["single_slot_hit_counts_by_lost_id"] = {
            str(lost_id): {
                "top": counts.get("top", 0),
                "bottom": counts.get("bottom", 0),
            }
            for lost_id, counts in single_slot_hit_counts.items()
        }
        score_event["single_slot_recovery_candidates"] = single_slot_candidates

    if not single_slot_candidates:
        return False, best_lost_id, best_hits, recovery_mode

    single_slot_candidates.sort(key=lambda item: item["avg_score"], reverse=True)
    best_single = single_slot_candidates[0]
    second_single = single_slot_candidates[1] if len(single_slot_candidates) > 1 else None
    ambiguous = (
        second_single is not None
        and best_single["avg_score"] - second_single["avg_score"] < single_slot_ambiguity_margin
    )
    if score_event is not None:
        score_event["single_slot_best_candidate"] = best_single
        score_event["single_slot_second_candidate"] = second_single
        score_event["single_slot_ambiguous"] = ambiguous
    if ambiguous:
        return False, best_lost_id, best_hits, recovery_mode

    return (
        True,
        int(best_single["lost_our_id"]),
        int(best_single["hits"]),
        f"single_slot_{best_single['slot']}",
    )


def run_mode(args: argparse.Namespace, use_reid: bool) -> dict[str, Any]:
    mode = "reid" if use_reid else "bytetrack_only"
    records: list[dict[str, Any]] = []
    device = resolve_eval_device(args.device)

    detector = PersonDetector()
    force_detector_device(detector, device)

    tracker = HybridTracker(recovery_threshold=args.recovery_threshold) if use_reid else None
    embedder = None
    classifier = None
    reid_recovery_summary = empty_reid_summary(
        enabled=use_reid,
        threshold=getattr(tracker, "_recovery_threshold", None) if tracker is not None else None,
    )
    if not use_reid:
        reid_recovery_summary["note"] = "Re-ID disabled for this mode."
    else:
        model_path = get_classifier_model_path()
        if not args.disable_reid_embedding:
            embedder = ClothingEmbedder(model_path, device=device)
        else:
            reid_recovery_summary["embedding_disabled"] = True
            reid_recovery_summary["similarity_method"]["embedding"] = "disabled for this evaluation run"
        classifier = ClothingClassifier(model_path)
        if classifier.model is not None:
            classifier.device = device
            classifier.model.to(device)

    cap = cv2.VideoCapture(args.video)
    if not cap.isOpened():
        raise RuntimeError(f"Cannot open video: {args.video}")

    input_fps = cap.get(cv2.CAP_PROP_FPS) or 0.0
    total_video_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    cap.set(cv2.CAP_PROP_POS_FRAMES, args.start_frame)

    t0 = time.perf_counter()
    processed_frames = 0
    skipped_frames = 0
    frames_with_person = 0
    total_detections = 0
    seen_ids = set()
    latest_track_snapshots: dict[int, dict[str, Any]] = {}
    track_profiles: dict[int, dict[str, Any]] = {}
    track_profile_history: dict[int, list[dict[str, Any]]] = {}
    pending_reid: dict[int, dict[str, Any]] = {}
    class_failed_saved_keys: set[tuple[int | None, int | None, str | None]] = set()
    output_dir = Path(args.output_dir)
    timings: dict[str, dict[str, float]] = {}
    expected_classes = parse_expected_classes(args.expected_clothing_classes)
    confirmation_frames = max(1, args.reid_confirmation_frames)
    confirmation_min_hits = (
        args.reid_confirmation_min_hits
        if args.reid_confirmation_min_hits > 0
        else (confirmation_frames // 2) + 1
    )
    reid_recovery_summary["confirmation_frames"] = confirmation_frames
    reid_recovery_summary["confirmation_min_hits"] = confirmation_min_hits
    reid_recovery_summary["single_slot_fallback"] = {
        "enabled": args.single_slot_fallback,
        "min_hits": args.single_slot_min_hits,
        "threshold": args.single_slot_threshold,
        "min_coverage": args.single_slot_min_coverage,
        "missing_max_coverage": args.single_slot_missing_max_coverage,
        "dominance_ratio": args.single_slot_dominance_ratio,
        "ambiguity_margin": args.single_slot_ambiguity_margin,
    }

    for offset in range(args.frames):
        ok, frame = cap.read()
        if not ok or frame is None:
            break

        frame_number = args.start_frame + offset
        if offset % args.frame_skip != 0:
            skipped_frames += 1
            continue

        processed_frames += 1
        section_t0 = time.perf_counter()
        result = detector.track_people(frame)
        add_timing(timings, "person_detector_track", section_t0)
        boxes = getattr(result, "boxes", None)
        person_embeddings = (
            getattr(result, "person_embeddings", None)
            or getattr(detector, "last_person_embeddings", [])
            or []
        )
        current_ids: list[int] = []

        if boxes is None or len(boxes) == 0:
            if tracker is not None:
                tracker.update_lost_tracks(args.camera_id, current_ids)
            continue

        frames_with_person += 1
        pending_track_snapshots: dict[int, dict[str, Any]] = {}
        for det_idx, box in enumerate(boxes):
            confidence = float(box.conf.item()) if hasattr(box, "conf") else 0.0
            if confidence < args.confidence:
                continue

            byte_id = -1
            if hasattr(box, "id") and box.id is not None:
                byte_id = int(box.id.item())

            x1, y1, x2, y2 = map(int, box.xyxy[0])
            x1 = max(0, min(width, x1))
            x2 = max(0, min(width, x2))
            y1 = max(0, min(height, y1))
            y2 = max(0, min(height, y2))
            if x2 <= x1 or y2 <= y1:
                continue

            total_detections += 1
            track_id = byte_id
            persistent_id = None
            clothes: list[str] = []
            detailed_colors: dict[str, float] = {}
            color_groups: dict[str, float] = {}
            person_crop = frame[y1:y2, x1:x2]

            if use_reid and tracker is not None and classifier is not None:
                embedding = None
                if not args.disable_reid_embedding and embedder is not None:
                    detector_embedding = person_embeddings[det_idx] if det_idx < len(person_embeddings) else None
                    section_t0 = time.perf_counter()
                    embedding, clothes = embedder.get_embedding(
                        person_crop,
                        person_embedding=detector_embedding,
                    )
                    add_timing(timings, "embedding_extraction", section_t0)
                section_t0 = time.perf_counter()
                clothing_profile = select_clothing_profile(
                    person_crop,
                    classifier,
                    disable_color=args.disable_color,
                    expected_classes=expected_classes or None,
                )
                add_timing(timings, "clothing_profile_class_color", section_t0)
                if expected_classes and clothing_profile.get("unexpected_predictions"):
                    section_t0 = time.perf_counter()
                    wrong_paths = save_unexpected_class_crops(
                        output_dir,
                        frame_number,
                        byte_id if byte_id >= 0 else None,
                        person_crop,
                        clothing_profile,
                    )
                    add_timing(timings, "wrong_class_crop_saving", section_t0)
                    reid_recovery_summary.setdefault("wrong_class_crop_events", 0)
                    reid_recovery_summary.setdefault("wrong_class_crop_paths", [])
                    reid_recovery_summary["wrong_class_crop_events"] += len(wrong_paths)
                    reid_recovery_summary["wrong_class_crop_paths"].extend(wrong_paths)
                detailed_colors = {}
                color_groups = {}

                byte_arg = byte_id if byte_id >= 0 else None
                state = tracker._get_or_create_state(args.camera_id)
                with state.lock:
                    was_known = byte_arg is not None and byte_arg in state.id_mapping
                    lost_before = len(state.lost_tracks)
                    mapped_before = state.id_mapping.get(byte_arg) if byte_arg is not None else None
                    lost_candidates = list(state.lost_tracks.items())

                pending_state = pending_reid.get(byte_arg) if byte_arg is not None else None
                if pending_state is not None:
                    initial_lost_ids = set(pending_state.get("initial_lost_ids", []))
                    lost_candidates = [
                        (lost_our_id, lost_features)
                        for lost_our_id, lost_features in lost_candidates
                        if lost_our_id in initial_lost_ids
                    ]

                can_try_reid = byte_arg is not None and (not was_known or pending_state is not None)
                score_event = None
                new_features = TrackFeatures(
                    detailed_colors=detailed_colors,
                    color_groups=color_groups,
                    embedding=embedding.tolist() if embedding is not None else None,
                    clothes=[
                        clothing_profile.get("classes", {}).get("top"),
                        clothing_profile.get("classes", {}).get("bottom"),
                    ],
                    last_seen=time.time(),
                    frame_number=frame_number,
                )
                if can_try_reid and lost_candidates:
                    section_t0 = time.perf_counter()
                    candidate_scores = []
                    for lost_our_id, lost_features in lost_candidates:
                        aggregate_features, aggregate_profile = aggregate_track_profile(
                            track_profile_history.get(lost_our_id, []),
                            args.aggregate_slot_history_limit,
                        )
                        comparison_features = aggregate_features if aggregate_features is not None else lost_features
                        comparison_profile = aggregate_profile if aggregate_profile is not None else track_profiles.get(lost_our_id)
                        components = clothing_gated_reid_components(
                            new_features,
                            comparison_features,
                            clothing_profile,
                            comparison_profile,
                        )
                        candidate_scores.append({
                            "lost_our_id": lost_our_id,
                            "score": components["score"],
                            "average_score": components.get("average_score"),
                            "range_score": components.get("range_score"),
                            "score_mode": components.get("score_mode"),
                            "class_match": components["class_match"],
                            "reason": components["reason"],
                            "embedding_score": components["embedding_score"],
                            "shirt_color_score": components["shirt_color_score"],
                            "pants_color_score": components["pants_color_score"],
                            "shirt_color_range_score": components.get("shirt_color_range_score"),
                            "pants_color_range_score": components.get("pants_color_range_score"),
                            "score_count": components.get("score_count", 0),
                            "matched_slots": components.get("matched_slots", []),
                            "matched_pairs": components.get("matched_pairs", []),
                            "mismatched_slots": components.get("mismatched_slots", []),
                            "missing_slots": components.get("missing_slots", []),
                            "lost_clothes": comparison_features.clothes,
                            "new_clothes": new_features.clothes,
                            "lost_clothing_profile": comparison_profile,
                            "new_clothing_profile": clothing_profile,
                            "lost_profile_source": "aggregate" if aggregate_profile is not None else "latest",
                        })
                    add_timing(timings, "reid_candidate_scoring", section_t0)
                    matching_candidates = [item for item in candidate_scores if item.get("class_match")]
                    best_candidate = max(matching_candidates, key=lambda item: item["score"], default=None)
                    score_event = {
                        "frame": frame_number,
                        "byte_id": byte_arg,
                        "candidate_scores": candidate_scores,
                        "best_lost_our_id": best_candidate["lost_our_id"] if best_candidate else None,
                        "best_score": best_candidate["score"] if best_candidate else 0.0,
                        "threshold": getattr(tracker, "_recovery_threshold", None),
                        "matching_candidate_count": len(matching_candidates),
                        "new_clothing_profile": clothing_profile,
                    }
                    if args.save_class_failed_crops:
                        class_failed_paths = []
                        section_t0 = time.perf_counter()
                        for candidate in candidate_scores:
                            if candidate.get("class_match"):
                                continue
                            saved_key = (
                                byte_arg,
                                candidate.get("lost_our_id"),
                                candidate.get("reason"),
                            )
                            if saved_key in class_failed_saved_keys:
                                continue
                            class_failed_saved_keys.add(saved_key)
                            crop_paths = save_class_failed_crop_pair(
                                output_dir=output_dir,
                                frame_number=frame_number,
                                byte_id=byte_arg,
                                current_crop=person_crop,
                                candidate=candidate,
                                lost_snapshot=latest_track_snapshots.get(candidate.get("lost_our_id")),
                            )
                            class_failed_paths.append(crop_paths)
                        add_timing(timings, "class_failed_crop_saving", section_t0)
                        if class_failed_paths:
                            score_event["class_failed_crop_paths"] = class_failed_paths
                            reid_recovery_summary["class_failed_crop_events"] += len(class_failed_paths)
                            reid_recovery_summary["class_failed_crop_paths"].extend(class_failed_paths)

                state = tracker._get_or_create_state(args.camera_id)
                is_new = False
                is_recovered = False
                is_confirmed_new = False
                confirmation_hit_count = 0
                with state.lock:
                    if byte_arg is None:
                        our_id = state.next_our_id
                        state.next_our_id += 1
                        is_new = True
                    elif byte_arg in state.id_mapping:
                        our_id = state.id_mapping[byte_arg]
                    else:
                        our_id = state.next_our_id
                        state.id_mapping[byte_arg] = our_id
                        state.next_our_id += 1
                        is_new = True
                        if lost_candidates:
                            pending_reid[byte_arg] = {
                                "provisional_our_id": our_id,
                                "start_frame": frame_number,
                                "observations": 0,
                                "hit_counts": {},
                                "score_events": [],
                                "initial_lost_ids": [lost_our_id for lost_our_id, _ in lost_candidates],
                            }
                            pending_state = pending_reid[byte_arg]
                            print(f"⏳ [HybridTrackerStrict] Pending new track: {our_id} (byte_id: {byte_arg})")
                        else:
                            print(f"🆕 [HybridTrackerStrict] New track: {our_id} (byte_id: {byte_arg})")

                if byte_arg is not None and pending_state is not None and score_event is not None:
                    should_recover, confirmed_lost_id, confirmation_hit_count, recovery_mode = update_confirmation_state(
                        pending_state,
                        score_event,
                        getattr(tracker, "_recovery_threshold", 0.7),
                        confirmation_frames,
                        confirmation_min_hits,
                        args.single_slot_fallback,
                        args.single_slot_min_hits,
                        args.single_slot_threshold,
                        args.single_slot_min_coverage,
                        args.single_slot_missing_max_coverage,
                        args.single_slot_dominance_ratio,
                        args.single_slot_ambiguity_margin,
                    )
                    if should_recover and confirmed_lost_id is not None:
                        provisional_our_id = int(pending_state["provisional_our_id"])
                        with state.lock:
                            our_id = int(confirmed_lost_id)
                            state.id_mapping[byte_arg] = our_id
                            if our_id in state.lost_tracks:
                                del state.lost_tracks[our_id]
                        pending_reid.pop(byte_arg, None)
                        remap_records_for_recovery(records, byte_arg, provisional_our_id, our_id)
                        is_recovered = True
                        is_new = False
                        score_event["best_lost_our_id"] = our_id
                        score_event["confirmed_by_window"] = True
                        score_event["confirmation_hits"] = confirmation_hit_count
                        score_event["recovery_mode"] = recovery_mode
                        if recovery_mode.startswith("single_slot"):
                            reid_recovery_summary["single_slot_recovered_tracks"] += 1
                        print(
                            f"🔄 [HybridTrackerStrict] Track recovered by confirmation: "
                            f"{our_id} (byte_id: {byte_arg}, hits={confirmation_hit_count}/{confirmation_frames}, "
                            f"mode={recovery_mode}, score={score_event['best_score']:.3f})"
                        )
                    elif pending_state["observations"] >= confirmation_frames:
                        pending_reid.pop(byte_arg, None)
                        is_confirmed_new = True
                        reid_recovery_summary["confirmed_new_tracks"] += 1
                        print(
                            f"🆕 [HybridTrackerStrict] Confirmed new track: {our_id} "
                            f"(byte_id: {byte_arg}, best_hits={confirmation_hit_count}/{confirmation_frames})"
                        )

                if byte_arg is None and is_new:
                    reid_recovery_summary["untracked_new_tracks"] += 1
                elif byte_arg is not None and (not was_known or pending_state is not None):
                    if not was_known:
                        reid_recovery_summary["byte_id_new_events"] += 1
                    if can_try_reid:
                        if not was_known:
                            reid_recovery_summary["reid_candidate_events"] += 1
                        else:
                            reid_recovery_summary["reid_confirmation_observations"] += 1
                        if lost_before > 0:
                            if not was_known:
                                reid_recovery_summary["reid_attempts"] += 1
                            reid_recovery_summary["reid_similarity_attempts"] += 1
                            if score_event is not None:
                                score_event["recovered"] = is_recovered
                                score_event["assigned_our_id"] = our_id
                                score_event["recovered_score"] = (
                                    score_event["best_score"] if is_recovered else None
                                )
                                score_event["pending_reid"] = pending_state is not None and not is_recovered and not is_confirmed_new
                                reid_recovery_summary["recover_score_events"].append(score_event)

                if is_recovered:
                    reid_recovery_summary["recovered_tracks"] += 1
                    if score_event is not None:
                        reid_recovery_summary["recovered_scores"].append(score_event["best_score"])
                        section_t0 = time.perf_counter()
                        crop_paths = save_recovered_crop_pair(
                            output_dir=output_dir,
                            frame_number=frame_number,
                            byte_id=byte_arg,
                            our_id=our_id,
                            score=score_event.get("best_score"),
                            current_crop=person_crop,
                            lost_snapshot=latest_track_snapshots.get(our_id),
                        )
                        add_timing(timings, "recovered_crop_saving", section_t0)
                        score_event["crop_paths"] = crop_paths
                if is_new:
                    reid_recovery_summary["new_tracks"] += 1

                tracker.store_track_features(
                    camera_id=args.camera_id,
                    our_id=our_id,
                    detailed_colors=detailed_colors,
                    color_groups=color_groups,
                    embedding=embedding.tolist() if embedding is not None else None,
                    clothes=new_features.clothes,
                )
                track_profiles[our_id] = clothing_profile
                append_track_profile_history(
                    track_profile_history,
                    our_id,
                    frame_number,
                    new_features,
                    clothing_profile,
                    args.profile_history_limit,
                )

                if (is_recovered or is_new) and len(reid_recovery_summary["events"]) < 500:
                    reid_recovery_summary["events"].append({
                        "frame": frame_number,
                        "camera_id": args.camera_id,
                        "byte_id": byte_arg,
                        "our_id": our_id,
                        "was_known": was_known,
                        "mapped_before": mapped_before,
                        "lost_tracks_before": lost_before,
                        "tried_reid": can_try_reid,
                        "compared_with_lost_tracks": can_try_reid and lost_before > 0,
                        "is_new": is_new,
                        "is_recovered": is_recovered,
                    })

                track_id = our_id
                persistent_id = our_id
                current_ids.append(our_id)
                pending_track_snapshots[our_id] = {
                    "frame": frame_number,
                    "byte_id": byte_arg,
                    "crop": person_crop.copy(),
                    "bbox": [x1, y1, x2, y2],
                    "clothing_profile": clothing_profile,
                }

            seen_ids.add(track_id)
            records.append({
                "mode": mode,
                "frame": frame_number,
                "track_id": track_id,
                "persistent_id": persistent_id,
                "byte_track_id": byte_id,
                "confidence": confidence,
                "x": x1,
                "y": y1,
                "w": x2 - x1,
                "h": y2 - y1,
                "class_names": clothes,
                "primary_colors": list(color_groups.keys()),
            })

        if tracker is not None:
            section_t0 = time.perf_counter()
            tracker.update_lost_tracks(args.camera_id, current_ids)
            add_timing(timings, "update_lost_tracks", section_t0)
            latest_track_snapshots.update(pending_track_snapshots)

    wall_seconds = time.perf_counter() - t0
    output_fps = processed_frames / wall_seconds if wall_seconds > 0 else 0.0
    cap.release()
    timing_summary = summarize_timings(timings)

    if use_reid and reid_recovery_summary.get("enabled"):
        attempts = reid_recovery_summary.get("reid_attempts", 0)
        candidates = reid_recovery_summary.get("reid_candidate_events", 0)
        recovered = reid_recovery_summary.get("recovered_tracks", 0)
        reid_recovery_summary["recovery_rate_per_similarity_attempt"] = (
            recovered / attempts if attempts else 0.0
        )
        reid_recovery_summary["recovery_rate_per_candidate_event"] = (
            recovered / candidates if candidates else 0.0
        )
        score_events = reid_recovery_summary.get("recover_score_events", [])
        best_scores = [event.get("best_score", 0.0) for event in score_events]
        best_candidates = [
            max(event.get("candidate_scores", []), key=lambda item: item.get("score", 0.0))
            for event in score_events
            if event.get("candidate_scores")
        ]
        embedding_scores = [
            item.get("embedding_score")
            for item in best_candidates
            if item.get("embedding_score") is not None
        ]
        range_scores = [
            item.get("range_score")
            for item in best_candidates
            if item.get("range_score") is not None
        ]
        average_scores = [
            item.get("average_score")
            for item in best_candidates
            if item.get("average_score") is not None
        ]
        shirt_color_scores = [
            item.get("shirt_color_score")
            for item in best_candidates
            if item.get("shirt_color_score") is not None
        ]
        pants_color_scores = [
            item.get("pants_color_score")
            for item in best_candidates
            if item.get("pants_color_score") is not None
        ]
        reid_recovery_summary["best_recover_score"] = max(best_scores) if best_scores else None
        reid_recovery_summary["average_attempt_best_score"] = (
            sum(best_scores) / len(best_scores) if best_scores else 0.0
        )
        reid_recovery_summary["average_best_embedding_score"] = (
            sum(embedding_scores) / len(embedding_scores) if embedding_scores else 0.0
        )
        reid_recovery_summary["average_best_average_score"] = (
            sum(average_scores) / len(average_scores) if average_scores else 0.0
        )
        reid_recovery_summary["average_best_range_score"] = (
            sum(range_scores) / len(range_scores) if range_scores else 0.0
        )
        reid_recovery_summary["average_best_shirt_color_score"] = (
            sum(shirt_color_scores) / len(shirt_color_scores) if shirt_color_scores else 0.0
        )
        reid_recovery_summary["average_best_pants_color_score"] = (
            sum(pants_color_scores) / len(pants_color_scores) if pants_color_scores else 0.0
        )
        reid_recovery_summary["final_tracker_stats"] = tracker.get_stats(args.camera_id) if tracker else {}
        if tracker:
            tracker.cleanup(args.camera_id)

    unique_track_ids = {
        record["track_id"]
        for record in records
        if record.get("track_id") is not None
    }
    stats = {
        "video_id": f"{args.video_id}-{mode}",
        "camera_id": args.camera_id,
        "total_frames": total_video_frames,
        "processed_frames": processed_frames,
        "skipped_frames": skipped_frames,
        "fps": input_fps,
        "image_width": width,
        "image_height": height,
        "total_detections": total_detections,
        "num_persons_detected": total_detections,
        "unique_persons": len(unique_track_ids),
        "duration_seconds": wall_seconds,
        "effective_fps": output_fps,
        "completed": True,
        "num_errors": 0,
        "timing_summary": timing_summary,
    }

    return {
        "mode": mode,
        "use_reid": use_reid,
        "stats": stats,
        "wall_seconds": wall_seconds,
        "input_fps": input_fps,
        "processed_fps": output_fps,
        "output_fps": output_fps,
        "timing_summary": timing_summary,
        "progress_events": [],
        "records": records,
        "proxy_metrics": tracking_proxy_metrics(records),
        "reid_recovery_summary": reid_recovery_summary,
    }


def write_records_csv(path: Path, records: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "mode", "frame", "track_id", "persistent_id", "byte_track_id", "confidence",
        "x", "y", "w", "h", "class_names", "primary_colors",
    ]
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in records:
            writer.writerow({
                **row,
                "class_names": json.dumps(row.get("class_names", []), ensure_ascii=False),
                "primary_colors": json.dumps(row.get("primary_colors", []), ensure_ascii=False),
            })


async def evaluate(args: argparse.Namespace) -> dict[str, Any]:
    mode_reports = []
    if args.mode in {"both", "bytetrack_only"}:
        mode_reports.append(run_mode(args, use_reid=False))
    if args.mode in {"both", "reid"}:
        mode_reports.append(run_mode(args, use_reid=True))

    all_records = [record for report in mode_reports for record in report["records"]]
    output_dir = Path(args.output_dir)
    write_records_csv(output_dir / "tracking-detections.csv", all_records)

    report = {
        "task": "tracking_reid_comparison",
        "video": args.video,
        "camera_id": args.camera_id,
        "start_frame": args.start_frame,
        "frames": args.frames,
        "end_frame_exclusive": args.start_frame + args.frames,
        "frame_skip": args.frame_skip,
        "mode_reports": mode_reports,
    }

    if args.ground_truth:
        gt = read_records(args.ground_truth)
        for mode_report in report["mode_reports"]:
            mode_report["identity_metrics"] = mot_identity_metrics(
                gt,
                mode_report["records"],
                iou_threshold=args.iou_threshold,
            )
        if len(report["mode_reports"]) == 2:
            base = report["mode_reports"][0]
            reid = report["mode_reports"][1]
            base_frag = base.get("identity_metrics", {}).get("fragmentations", 0)
            reid_frag = reid.get("identity_metrics", {}).get("fragmentations", 0)
            report["comparison"] = {
                "unique_track_ids_delta": (
                    reid["proxy_metrics"]["unique_track_ids"]
                    - base["proxy_metrics"]["unique_track_ids"]
                ),
                "fragmentation_reduction": base_frag - reid_frag,
                "id_switch_delta": (
                    reid.get("identity_metrics", {}).get("id_switches", 0)
                    - base.get("identity_metrics", {}).get("id_switches", 0)
                ),
            }
    else:
        report["ground_truth_note"] = (
            "No ground truth supplied. Recovery correctness cannot be measured; "
            "only proxy metrics such as unique_track_ids and avg_track_length are reported."
        )

    write_json(output_dir / "tracking-reid-eval.json", report)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Compare ByteTrack-only vs Re-ID tracking on a video.")
    parser.add_argument("--video", required=True)
    parser.add_argument("--ground-truth", default="", help="Optional MOT-like CSV/JSON with frame,identity,x,y,w,h.")
    parser.add_argument("--output-dir", default="my-thesis-report/qa/tracking-reid")
    parser.add_argument("--camera-id", default="EVAL-CAM-01")
    parser.add_argument("--video-id", default="eval-video")
    parser.add_argument("--mode", choices=["both", "bytetrack_only", "reid"], default="both")
    parser.add_argument("--start-frame", type=int, default=100)
    parser.add_argument("--frames", type=int, default=200)
    parser.add_argument("--frame-skip", type=int, default=1)
    parser.add_argument("--confidence", type=float, default=0.25)
    parser.add_argument("--device", choices=["cuda", "cpu"], default="")
    parser.add_argument("--recovery-threshold", type=float, default=0.7)
    parser.add_argument("--max-workers", type=int, default=1)
    parser.add_argument("--iou-threshold", type=float, default=0.5)
    parser.add_argument("--disable-clothing", action="store_true")
    parser.add_argument("--disable-color", action="store_true")
    parser.add_argument(
        "--disable-reid-embedding",
        action="store_true",
        help="Disable embedding extraction and Re-ID embedding similarity; compare clothing slot colors only.",
    )
    parser.add_argument(
        "--profile-history-limit",
        type=int,
        default=60,
        help="Maximum number of per-track profile observations used to build lost-track aggregate features.",
    )
    parser.add_argument(
        "--aggregate-slot-history-limit",
        type=int,
        default=10,
        help="Use only the latest N observations for the selected top/bottom class when aggregating colors.",
    )
    parser.add_argument(
        "--expected-clothing-classes",
        default="",
        help="Comma-separated class names expected in the clip; other predicted classes are ignored and cropped as wrong predictions.",
    )
    parser.add_argument(
        "--reid-confirmation-frames",
        type=int,
        default=30,
        help="Number of consecutive frames used to confirm a Re-ID recovery candidate.",
    )
    parser.add_argument(
        "--reid-confirmation-min-hits",
        type=int,
        default=10,
        help="Minimum matching observations required in both top and bottom slots to recover.",
    )
    parser.add_argument(
        "--single-slot-fallback",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Allow recovery from one clothing slot when both lost and new tracks mostly see only that same slot.",
    )
    parser.add_argument("--single-slot-min-hits", type=int, default=18)
    parser.add_argument("--single-slot-threshold", type=float, default=0.75)
    parser.add_argument("--single-slot-min-coverage", type=float, default=0.60)
    parser.add_argument("--single-slot-missing-max-coverage", type=float, default=0.15)
    parser.add_argument("--single-slot-dominance-ratio", type=float, default=4.0)
    parser.add_argument("--single-slot-ambiguity-margin", type=float, default=0.08)
    parser.add_argument(
        "--save-class-failed-crops",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Save crop pairs and metadata for Re-ID candidates rejected by the clothing class gate.",
    )
    args = parser.parse_args()
    report = asyncio.run(evaluate(args))
    summary = {
        "output": str(Path(args.output_dir) / "tracking-reid-eval.json"),
        "window": {
            "start_frame": args.start_frame,
            "end_frame_exclusive": args.start_frame + args.frames,
            "frames": args.frames,
            "frame_skip": args.frame_skip,
        },
        "modes": [
            {
                "mode": r["mode"],
                "unique_track_ids": r["proxy_metrics"]["unique_track_ids"],
                "processed_fps": r["processed_fps"],
                "output_fps": r["output_fps"],
                "reid_recovery": {
                    "recovered_tracks": r.get("reid_recovery_summary", {}).get("recovered_tracks"),
                    "new_tracks": r.get("reid_recovery_summary", {}).get("new_tracks"),
                    "reid_attempts": r.get("reid_recovery_summary", {}).get("reid_attempts"),
                    "best_recover_score": r.get("reid_recovery_summary", {}).get("best_recover_score"),
                    "average_attempt_best_score": r.get("reid_recovery_summary", {}).get("average_attempt_best_score"),
                    "recovery_rate_per_similarity_attempt": r.get("reid_recovery_summary", {}).get("recovery_rate_per_similarity_attempt"),
                    "confirmation_frames": r.get("reid_recovery_summary", {}).get("confirmation_frames"),
                    "confirmation_min_hits": r.get("reid_recovery_summary", {}).get("confirmation_min_hits"),
                    "reid_confirmation_observations": r.get("reid_recovery_summary", {}).get("reid_confirmation_observations"),
                    "wrong_class_crop_events": r.get("reid_recovery_summary", {}).get("wrong_class_crop_events"),
                    "timing_summary": r.get("timing_summary"),
                } if r.get("use_reid") else None,
            }
            for r in report["mode_reports"]
        ],
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
