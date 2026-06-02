"""
test_api.py — endpoints for the TEST tab in the frontend.

POST /api/test/color-analyze
  Accept base64 image, run full pipeline:
  person detect → clothing classify → color analyze
  Return annotated image + structured results.
"""
from __future__ import annotations

import base64
import io
import sys
from pathlib import Path
from typing import Any

import cv2
import numpy as np
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter()

# Ensure scripts/ on path (same pattern as video_controller)
_WORKSPACE = Path(__file__).resolve().parents[3]
_SCRIPTS_DIR = str(_WORKSPACE / "scripts")
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)


# ── Lazy model cache ─────────────────────────────────────────────────────────

_detector = None
_clothing = None


def _load_models():
    global _detector, _clothing
    if _detector is not None:
        return _detector, _clothing

    from ultralytics import YOLO
    from src.ai.clothing_predictor import YoloPredictor
    from src.config_loader import get_detector_model_path, get_classifier_model_path, get_device

    device = get_device()
    _detector = YOLO(str(Path(get_detector_model_path()).resolve()))
    _detector.to(device)
    _clothing = YoloPredictor(
        Path(get_classifier_model_path()).resolve(),
        device=device,
        imgsz=224,
        conf=0.25,
        half=False,
    )
    return _detector, _clothing


# ── Request/Response schemas ─────────────────────────────────────────────────

class ColorAnalyzeRequest(BaseModel):
    image: str          # base64-encoded image (data URI or raw)
    remove_bg: bool | None = None   # override config; None = use config


class ColorResult(BaseModel):
    color_name: str
    percentage: float


class ItemResult(BaseModel):
    slot: str           # "top" | "bottom" | "dress"
    cls: str
    confidence: float
    bbox: list[int]     # [x1,y1,x2,y2] in original frame coords
    detailed_colors: dict[str, float]
    color_groups: dict[str, float]
    primary_color: str
    primary_group: str


class PersonResult(BaseModel):
    track_id: int
    bbox: list[int]
    confidence: float
    stable_label: str
    items: list[ItemResult]


class ColorAnalyzeResponse(BaseModel):
    persons: list[PersonResult]
    annotated_image: str    # base64 JPEG with boxes drawn
    width: int
    height: int


# ── Helpers ──────────────────────────────────────────────────────────────────

def _decode_image(b64: str) -> np.ndarray:
    """Decode base64 (with or without data-URI header) to BGR numpy array."""
    if "," in b64:
        b64 = b64.split(",", 1)[1]
    raw = base64.b64decode(b64)
    arr = np.frombuffer(raw, dtype=np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError("Cannot decode image")
    return img


def _encode_image(img: np.ndarray, quality: int = 85) -> str:
    """Encode BGR numpy array to base64 JPEG data-URI."""
    ok, buf = cv2.imencode(".jpg", img, [int(cv2.IMWRITE_JPEG_QUALITY), quality])
    if not ok:
        raise ValueError("Cannot encode image")
    return "data:image/jpeg;base64," + base64.b64encode(buf.tobytes()).decode()


_COLORS = [
    (0, 255, 0),    # green  — person box
    (255, 128, 0),  # blue   — top item
    (0, 128, 255),  # orange — bottom item
    (180, 0, 255),  # purple — dress
]


def _slot_color(slot: str) -> tuple[int, int, int]:
    return {"top": (255, 128, 0), "bottom": (0, 128, 255), "dress": (180, 0, 255)}.get(slot, (200, 200, 200))


# ── Endpoint ─────────────────────────────────────────────────────────────────

@router.post("/api/test/color-analyze", response_model=ColorAnalyzeResponse)
async def color_analyze(body: ColorAnalyzeRequest):
    """
    Full pipeline on a single image:
    1. Person detection (YOLO tracker)
    2. Clothing classification per person crop
    3. Detailed color analysis (respects processing.color_remove_background)
    Returns annotated image + structured results.
    """
    try:
        frame = _decode_image(body.image)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Bad image: {e}")

    # Deinterlace: average even+odd row pairs, write back to both rows
    if frame.shape[0] > 1:
        even = frame[::2].astype(np.float32)
        odd  = frame[1::2].astype(np.float32)
        blended = ((even + odd) * 0.5).astype(np.uint8)
        frame = frame.copy()
        frame[::2]  = blended
        frame[1::2] = blended

    height, width = frame.shape[:2]

    try:
        detector, clothing_model = _load_models()
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Model load failed: {e}")

    from src.config_loader import get_color_remove_background
    from src.ai.clothing_predictor import prediction_result as _pred_result
    from predict_video_clothing_viewer import clamp_bbox
    from pipeline_shared import apply_detailed_color_with_cache, class_summary

    remove_bg = body.remove_bg if body.remove_bg is not None else get_color_remove_background()

    # ── 1. Detect persons ──────────────────────────────────────────────────
    _PERSON_CONF = 0.1
    _TOP_K = 20
    _BATCH_SIZE = 32

    try:
        result = detector.track(
            frame,
            persist=False,          # single image — no cross-frame state
            tracker="bytetrack.yaml",
            classes=[0],
            conf=_PERSON_CONF,
            imgsz=640,
            verbose=False,
        )[0]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Detection failed: {e}")

    # ── 2. Build person list ───────────────────────────────────────────────
    persons: list[dict[str, Any]] = []
    crop_metas: list[dict[str, Any]] = []

    boxes = getattr(result, "boxes", None)
    if boxes is not None and len(boxes) > 0:
        ids = boxes.id
        for i, box in enumerate(boxes):
            bbox = clamp_bbox([int(v) for v in box.xyxy[0].tolist()], width, height)
            if bbox is None:
                continue
            tid = int(ids[i].item()) if ids is not None else i
            x1, y1, x2, y2 = bbox
            crop = frame[y1:y2, x1:x2]
            if crop.size == 0:
                continue
            person: dict[str, Any] = {
                "id": tid,
                "bbox": bbox,
                "confidence": float(box.conf.item()),
                "clothing": [],
                "result_clothing": [],
                "stable_clothing": {"label": "", "classes": []},
                "stable_label": "",
            }
            persons.append(person)
            crop_metas.append({"person": person, "crop": crop, "offset": (x1, y1)})

    # ── 3. Classify clothing ───────────────────────────────────────────────
    if crop_metas:
        predictions = clothing_model.predict_batch_top_n(
            [m["crop"] for m in crop_metas], _TOP_K, _BATCH_SIZE
        )
        dummy_cache: dict = {}
        for meta, top_preds in zip(crop_metas, predictions):
            processed = _pred_result(top_preds, 0.25, "outfit")
            x_off, y_off = meta["offset"]
            p = meta["person"]
            person_bbox = list(p["bbox"])  # [x1,y1,x2,y2] in frame coords
            final_items = []
            for det in processed["final_detections"]:
                item = dict(det)
                has_own_bbox = False
                if item.get("bbox"):
                    # detection-mode bbox: offset from crop → frame coords
                    cx1, cy1, cx2, cy2 = item["bbox"]
                    item["bbox"] = clamp_bbox(
                        [cx1 + x_off, cy1 + y_off, cx2 + x_off, cy2 + y_off],
                        width, height,
                    )
                    has_own_bbox = item["bbox"] is not None
                else:
                    # classification-mode (probs): no bbox → use person bbox
                    # so color analysis has a region to crop from
                    item["bbox"] = person_bbox

                # ── 4. Color analysis ──────────────────────────────────────
                apply_detailed_color_with_cache(
                    frame, item, width, height,
                    track_id=int(p["id"]),
                    frame_no=0,
                    stride=1,
                    cache=dummy_cache,
                    remove_bg=remove_bg,
                )

                # Clear fallback bbox so it doesn't appear as a real clothing box
                if not has_own_bbox:
                    item["bbox"] = None

                final_items.append(item)
            p["result_clothing"] = final_items
            p["stable_label"] = class_summary(final_items)

    # ── 5. Draw annotations ────────────────────────────────────────────────
    annotated = frame.copy()
    person_results: list[PersonResult] = []

    for p in persons:
        px1, py1, px2, py2 = p["bbox"]
        cv2.rectangle(annotated, (px1, py1), (px2, py2), (0, 255, 0), 2)

        label_y = py1 - 6
        tid_label = f"ID:{p['id']} {p['stable_label']}"
        (tw, th), _ = cv2.getTextSize(tid_label, cv2.FONT_HERSHEY_SIMPLEX, 0.45, 1)
        cv2.rectangle(annotated, (px1, label_y - th - 4), (px1 + tw + 4, label_y + 2), (0, 0, 0), -1)
        cv2.putText(annotated, tid_label, (px1 + 2, label_y), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 255, 0), 1)

        item_results: list[ItemResult] = []
        for item in p["result_clothing"]:
            slot = "top" if item.get("class") in {"short_sleeve", "long_sleeve"} else \
                   "bottom" if item.get("class") in {"shorts", "trousers", "skirt"} else "dress"
            ibbox = item.get("bbox")
            if ibbox:
                ix1, iy1, ix2, iy2 = ibbox
                c = _slot_color(slot)
                cv2.rectangle(annotated, (ix1, iy1), (ix2, iy2), c, 2)
                cls_label = f"{item.get('class','?')} {item.get('primary_detailed_color','')}"
                (cw, ch), _ = cv2.getTextSize(cls_label, cv2.FONT_HERSHEY_SIMPLEX, 0.38, 1)
                cv2.rectangle(annotated, (ix1, iy2), (ix1 + cw + 4, iy2 + ch + 6), (0, 0, 0), -1)
                cv2.putText(annotated, cls_label, (ix1 + 2, iy2 + ch + 2), cv2.FONT_HERSHEY_SIMPLEX, 0.38, c, 1)

            item_results.append(ItemResult(
                slot=slot,
                cls=item.get("class", "unknown"),
                confidence=float(item.get("confidence", 0)),
                bbox=ibbox or [],
                detailed_colors=item.get("detailed_colors") or {},
                color_groups=item.get("color_groups") or {},
                primary_color=item.get("primary_detailed_color") or "unknown",
                primary_group=item.get("primary_color_group") or "unknown",
            ))

        person_results.append(PersonResult(
            track_id=p["id"],
            bbox=p["bbox"],
            confidence=p["confidence"],
            stable_label=p["stable_label"],
            items=item_results,
        ))

    return ColorAnalyzeResponse(
        persons=person_results,
        annotated_image=_encode_image(annotated),
        width=width,
        height=height,
    )
