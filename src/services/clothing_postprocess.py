"""Shared clothing post-processing for production frame/video flows.

The classifier output is still treated as raw model evidence. This module
applies the same domain rules used during evaluation before the result is used
for display, storage, or track-level voting.
"""
from __future__ import annotations

from collections import Counter, defaultdict, deque
from dataclasses import dataclass, field
from typing import Any, Deque, Iterable, Mapping, Sequence

from services.ai_processing_types import BoundingBox, ClothingCategory, DetectedItem


TOP_CLASSES = {"short_sleeve", "long_sleeve"}
BOTTOM_CLASSES = {"shorts", "trousers", "skirt"}
DRESS_CLASS = "dress"
VALID_CLASSES = TOP_CLASSES | BOTTOM_CLASSES | {DRESS_CLASS}
CLASS_ORDER = ["short_sleeve", "long_sleeve", "dress", "shorts", "trousers", "skirt"]
RESULT_RULE_TEXT = (
    "max 2 objects; top/bottom/dress groups; dress companion only trousers or "
    "top confidence >= 0.76; skirt confidence x3 against dress; dress-only "
    "observations vote as no companion"
)


@dataclass(frozen=True)
class ClothingRuleConfig:
    dress_top_companion_min_conf: float = 0.76
    skirt_vs_dress_multiplier: float = 3.0
    vote_window: int = 30


@dataclass
class ClothingSelectionResult:
    raw_items: list[DetectedItem] = field(default_factory=list)
    items: list[DetectedItem] = field(default_factory=list)
    rule: str = RESULT_RULE_TEXT

    @property
    def label(self) -> str:
        return ", ".join(ordered_class_names(item.class_name for item in self.items))


@dataclass
class VotedOutfit:
    classes: list[str]
    items: list[DetectedItem]
    label: str
    votes: list[dict[str, Any]] = field(default_factory=list)


def normalize_class_name(class_name: Any) -> str:
    value = str(class_name or "").strip().lower().replace("-", "_").replace(" ", "_")
    aliases = {
        "dress": "dress",
        "short_sleeve_shirt": "short_sleeve",
        "long_sleeve_shirt": "long_sleeve",
        "pants": "trousers",
        "jeans": "trousers",
    }
    return aliases.get(value, value)


def clothing_slot(class_name: str) -> str | None:
    class_name = normalize_class_name(class_name)
    if class_name in TOP_CLASSES:
        return "top"
    if class_name == DRESS_CLASS:
        return "dress"
    if class_name in BOTTOM_CLASSES:
        return "bottom"
    return None


def clothing_category(class_name: str) -> ClothingCategory:
    slot = clothing_slot(class_name)
    if slot == "top":
        return ClothingCategory.TOP
    if slot == "bottom":
        return ClothingCategory.BOTTOM
    if slot == "dress":
        return ClothingCategory.FULL_BODY
    return ClothingCategory.UNKNOWN


def ordered_class_names(classes: Iterable[str]) -> list[str]:
    seen = set()
    normalized = []
    for class_name in classes:
        name = normalize_class_name(class_name)
        if name and name not in seen:
            seen.add(name)
            normalized.append(name)
    return sorted(normalized, key=lambda name: CLASS_ORDER.index(name) if name in CLASS_ORDER else 99)


def _bbox_from_prediction_bbox(bbox: Any) -> BoundingBox | None:
    if bbox is None:
        return None
    try:
        x1, y1, x2, y2 = [int(v) for v in bbox]
    except Exception:
        return None
    if x2 <= x1 or y2 <= y1:
        return None
    return BoundingBox.from_xyxy(x1, y1, x2, y2)


def item_from_prediction(prediction: Sequence[Any]) -> DetectedItem | None:
    if len(prediction) < 2:
        return None
    class_name = normalize_class_name(prediction[0])
    if class_name not in VALID_CLASSES:
        return None
    try:
        confidence = float(prediction[1] or 0.0)
    except Exception:
        confidence = 0.0
    if confidence <= 0:
        return None
    bbox = prediction[2] if len(prediction) > 2 else None
    return DetectedItem(
        class_name=class_name,
        category=clothing_category(class_name),
        confidence=confidence,
        relative_bbox=_bbox_from_prediction_bbox(bbox),
    )


def _best_by_class(items: Iterable[DetectedItem]) -> dict[str, DetectedItem]:
    best: dict[str, DetectedItem] = {}
    for item in items:
        class_name = normalize_class_name(item.class_name)
        current = best.get(class_name)
        if current is None or item.confidence > current.confidence:
            best[class_name] = item
    return best


def select_clothing_items(
    predictions: Sequence[Sequence[Any]],
    config: ClothingRuleConfig | None = None,
) -> ClothingSelectionResult:
    """Apply production clothing rules to raw classifier predictions."""
    config = config or ClothingRuleConfig()
    raw_items = [item for item in (item_from_prediction(pred) for pred in predictions) if item]
    best = _best_by_class(raw_items)

    top = max((best[name] for name in TOP_CLASSES if name in best), key=lambda item: item.confidence, default=None)
    bottom = max(
        (best[name] for name in BOTTOM_CLASSES if name in best),
        key=lambda item: item.confidence,
        default=None,
    )
    dress = best.get(DRESS_CLASS)

    def strength(item: DetectedItem | None) -> float:
        if item is None:
            return 0.0
        if dress is not None and item.class_name == "skirt":
            return item.confidence * config.skirt_vs_dress_multiplier
        return item.confidence

    if dress is not None and strength(dress) >= max(strength(top), strength(bottom)):
        companions: list[DetectedItem] = []
        if top is not None and top.confidence >= config.dress_top_companion_min_conf:
            companions.append(top)
        if bottom is not None and bottom.class_name == "trousers":
            companions.append(bottom)
        companion = max(companions, key=lambda item: item.confidence, default=None)
        selected = [dress] + ([companion] if companion else [])
    else:
        selected = [item for item in (top, bottom) if item is not None]

    selected = sorted(selected[:2], key=lambda item: CLASS_ORDER.index(item.class_name))
    top_predictions = [(item.class_name, item.confidence) for item in raw_items]
    for item in selected:
        item.top_predictions = top_predictions
    return ClothingSelectionResult(raw_items=raw_items, items=selected)


def _clone_or_placeholder(class_name: str, current_items: Mapping[str, DetectedItem], confidence: float = 0.0) -> DetectedItem:
    class_name = normalize_class_name(class_name)
    current = current_items.get(class_name)
    if current is not None:
        return current
    return DetectedItem(
        class_name=class_name,
        category=clothing_category(class_name),
        confidence=confidence,
    )


class StableClothingVoter:
    """Rolling vote used while a video or stream is still being processed."""

    def __init__(self, config: ClothingRuleConfig | None = None):
        self.config = config or ClothingRuleConfig()
        self._history: dict[Any, dict[str, Deque[str]]] = defaultdict(
            lambda: {
                "top": deque(maxlen=self.config.vote_window),
                "dress": deque(maxlen=self.config.vote_window),
                "bottom": deque(maxlen=self.config.vote_window),
            }
        )

    def update(self, track_key: Any, items: Sequence[DetectedItem]) -> VotedOutfit:
        slots = self._history[track_key]
        current_by_class = {normalize_class_name(item.class_name): item for item in items}
        for item in items:
            slot = clothing_slot(item.class_name)
            if slot:
                slots[slot].append(normalize_class_name(item.class_name))

        slot_items: dict[str, dict[str, Any]] = {}
        for slot, history in slots.items():
            if not history:
                continue
            class_name, votes = Counter(history).most_common(1)[0]
            slot_items[slot] = {
                "slot": slot,
                "class": class_name,
                "votes": votes,
                "total": len(history),
                "ratio": votes / len(history),
            }

        top = slot_items.get("top")
        dress = slot_items.get("dress")
        bottom = slot_items.get("bottom")
        top_score = (top["votes"], top["ratio"]) if top else (0, 0.0)
        bottom_score = (bottom["votes"], bottom["ratio"]) if bottom else (0, 0.0)

        if dress and (dress["votes"], dress["ratio"]) >= max(top_score, bottom_score):
            companions = []
            if top:
                current_top = current_by_class.get(top["class"])
                if current_top is None or current_top.confidence >= self.config.dress_top_companion_min_conf:
                    companions.append(top)
            if bottom and bottom["class"] == "trousers":
                companions.append(bottom)
            companion = max(companions, key=lambda item: (item["votes"], item["ratio"]), default=None)
            selected_votes = [dress] + ([companion] if companion else [])
        else:
            selected_votes = [item for item in (top, bottom) if item]

        classes = ordered_class_names(item["class"] for item in selected_votes)
        items_out = [
            _clone_or_placeholder(class_name, current_by_class, confidence=next((v["ratio"] for v in selected_votes if v["class"] == class_name), 0.0))
            for class_name in classes
        ]
        return VotedOutfit(classes=classes, items=items_out, label=", ".join(classes), votes=selected_votes)


class FinalOutfitVoter:
    """Track-level vote used when a finite video finishes, or a stream stops."""

    def __init__(self, config: ClothingRuleConfig | None = None):
        self.config = config or ClothingRuleConfig()
        self._tracks: dict[Any, dict[str, Any]] = {}

    def record(self, track_key: Any, frame_number: int, items: Sequence[DetectedItem]) -> None:
        track = self._tracks.setdefault(
            track_key,
            {
                "first_frame": frame_number,
                "last_frame": frame_number,
                "observations": 0,
                "slot_votes": {"top": [], "dress": [], "bottom": [], "none_companion": []},
            },
        )
        track["first_frame"] = min(track["first_frame"], frame_number)
        track["last_frame"] = max(track["last_frame"], frame_number)
        track["observations"] += 1

        frame_slots = set()
        for item in items:
            class_name = normalize_class_name(item.class_name)
            slot = clothing_slot(class_name)
            if not slot:
                continue
            frame_slots.add(slot)
            track["slot_votes"][slot].append(
                {"frame": frame_number, "class": class_name, "confidence": float(item.confidence or 0.0)}
            )

        if "dress" in frame_slots and not ({"top", "bottom"} & frame_slots):
            track["slot_votes"]["none_companion"].append(
                {"frame": frame_number, "class": "none", "confidence": 1.0}
            )

    @staticmethod
    def _vote_item(slot: str, votes: list[dict[str, Any]], total_observations: int) -> dict[str, Any] | None:
        if not votes:
            return None
        grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for vote in votes:
            grouped[vote["class"]].append(vote)
        class_name, best_votes = max(
            grouped.items(),
            key=lambda item: (
                len(item[1]),
                sum(float(v.get("confidence") or 0.0) for v in item[1]) / max(len(item[1]), 1),
            ),
        )
        avg_conf = sum(float(v.get("confidence") or 0.0) for v in best_votes) / max(len(best_votes), 1)
        return {
            "slot": slot,
            "class": class_name,
            "votes": len(best_votes),
            "slot_observations": len(votes),
            "total_observations": total_observations,
            "ratio": round(len(best_votes) / max(total_observations, 1), 4),
            "slot_ratio": round(len(best_votes) / max(len(votes), 1), 4),
            "avg_confidence": round(avg_conf, 4),
        }

    @staticmethod
    def _strength(item: dict[str, Any] | None) -> tuple[int, float]:
        if not item:
            return (0, 0.0)
        return (int(item.get("votes") or 0), float(item.get("avg_confidence") or 0.0))

    def _choose(self, slot_results: dict[str, dict[str, Any] | None]) -> list[dict[str, Any]]:
        top = slot_results.get("top")
        dress = slot_results.get("dress")
        bottom = slot_results.get("bottom")
        no_companion = slot_results.get("none_companion")

        if dress and self._strength(dress) >= max(self._strength(top), self._strength(bottom)):
            allowed = []
            if top and float(top.get("avg_confidence") or 0.0) >= self.config.dress_top_companion_min_conf:
                allowed.append(top)
            if bottom and bottom.get("class") == "trousers":
                allowed.append(bottom)
            companion = max(allowed, key=self._strength, default=None)
            selected = [dress]
            if companion and self._strength(companion) > self._strength(no_companion):
                selected.append(companion)
        else:
            selected = [item for item in (top, bottom) if item]

        return sorted(selected[:2], key=lambda item: CLASS_ORDER.index(item["class"]) if item["class"] in CLASS_ORDER else 99)

    def summary(self) -> dict[str, Any]:
        tracks = {}
        for track_key, track in self._tracks.items():
            total = int(track["observations"])
            slot_results = {
                slot: self._vote_item(slot, votes, total)
                for slot, votes in track["slot_votes"].items()
            }
            selected = self._choose(slot_results)
            classes = ordered_class_names(item["class"] for item in selected)
            tracks[str(track_key)] = {
                "first_frame": track["first_frame"],
                "last_frame": track["last_frame"],
                "observations": total,
                "label": ", ".join(classes),
                "classes": classes,
                "items": selected,
                "slot_results": slot_results,
            }
        return {
            "enabled": True,
            "rule": RESULT_RULE_TEXT,
            "track_count": len(tracks),
            "tracks": tracks,
        }
