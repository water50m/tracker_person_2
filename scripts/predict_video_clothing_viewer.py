from __future__ import annotations

import argparse
import json
import math
import os
import subprocess
import sys
from collections import Counter, defaultdict, deque
from pathlib import Path
from typing import Any

import cv2
import imageio_ffmpeg
import torch

WORKSPACE = Path(__file__).resolve().parents[1]
os.environ.setdefault("YOLO_CONFIG_DIR", str(WORKSPACE / ".ultralytics"))
os.environ.setdefault("MPLCONFIGDIR", str(WORKSPACE / ".matplotlib"))

from ultralytics import YOLO

EVAL_DIR = WORKSPACE / "tests" / "evaluation"
if str(EVAL_DIR) not in sys.path:
    sys.path.insert(0, str(EVAL_DIR))

from evaluate_clothing_model import TARGET_CLASSES, YoloPredictor, prediction_result  # noqa: E402


CLASS_COLORS = {
    "short_sleeve": "#00a6fb",
    "long_sleeve": "#7b2cbf",
    "shorts": "#f77f00",
    "trousers": "#2a9d8f",
    "skirt": "#d62828",
    "dress": "#6a994e",
}

TOP_CLASSES = {"short_sleeve", "long_sleeve"}
DRESS_CLASSES = {"dress"}
BOTTOM_CLASSES = {"shorts", "trousers", "skirt"}
CLASS_DISPLAY_ORDER = ["short_sleeve", "long_sleeve", "dress", "shorts", "trousers", "skirt"]
VOTE_WINDOW = 30


def file_url(path: Path) -> str:
    return "file:///" + path.resolve().as_posix().replace(" ", "%20").replace("#", "%23")


def run_ffmpeg(args: list[str]) -> None:
    exe = imageio_ffmpeg.get_ffmpeg_exe()
    completed = subprocess.run([exe, *args], text=True, capture_output=True)
    if completed.returncode != 0:
        raise RuntimeError(
            "ffmpeg failed\n"
            + " ".join([exe, *args])
            + "\nSTDOUT:\n"
            + completed.stdout[-2000:]
            + "\nSTDERR:\n"
            + completed.stderr[-4000:]
        )


def cut_clips(video_path: Path, output_dir: Path, first_seconds: float, frame_start: int, frame_end: int) -> dict[str, str]:
    first_clip = output_dir / "bangkok_earthquake_first_2min.mp4"
    frame_clip = output_dir / f"bangkok_earthquake_frames_{frame_start}_{frame_end}.mp4"

    run_ffmpeg(
        [
            "-y",
            "-i",
            str(video_path),
            "-t",
            str(first_seconds),
            "-c",
            "copy",
            str(first_clip),
        ]
    )
    run_ffmpeg(
        [
            "-y",
            "-i",
            str(video_path),
            "-vf",
            f"select='between(n\\,{frame_start}\\,{frame_end})',setpts=N/FRAME_RATE/TB",
            "-an",
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "20",
            "-pix_fmt",
            "yuv420p",
            str(frame_clip),
        ]
    )
    return {"first_clip": str(first_clip), "frame_clip": str(frame_clip)}


def clamp_bbox(bbox: list[int], width: int, height: int) -> list[int] | None:
    x1, y1, x2, y2 = bbox
    x1 = max(0, min(width - 1, int(x1)))
    y1 = max(0, min(height - 1, int(y1)))
    x2 = max(0, min(width, int(x2)))
    y2 = max(0, min(height, int(y2)))
    if x2 <= x1 or y2 <= y1:
        return None
    return [x1, y1, x2, y2]


def id_color(track_id: int) -> str:
    hue = (track_id * 47) % 360
    return f"hsl({hue}, 76%, 48%)"


def bbox_iou(a: list[int], b: list[int]) -> float:
    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b
    ix1 = max(ax1, bx1)
    iy1 = max(ay1, by1)
    ix2 = min(ax2, bx2)
    iy2 = min(ay2, by2)
    iw = max(0, ix2 - ix1)
    ih = max(0, iy2 - iy1)
    inter = iw * ih
    area_a = max(0, ax2 - ax1) * max(0, ay2 - ay1)
    area_b = max(0, bx2 - bx1) * max(0, by2 - by1)
    union = area_a + area_b - inter
    return inter / union if union else 0.0


def person_dedupe_score(person: dict[str, Any]) -> tuple[int, float, int]:
    result_count = len(person.get("result_clothing") or person.get("clothing") or [])
    confidence = float(person.get("confidence") or 0)
    x1, y1, x2, y2 = person["bbox"]
    area = max(0, x2 - x1) * max(0, y2 - y1)
    return (result_count, confidence, area)


def dedupe_persons_by_iou(persons: list[dict[str, Any]], threshold: float) -> list[dict[str, Any]]:
    kept: list[dict[str, Any]] = []
    for person in sorted(persons, key=person_dedupe_score, reverse=True):
        duplicate_of = None
        duplicate_iou = 0.0
        for kept_person in kept:
            overlap = bbox_iou(person["bbox"], kept_person["bbox"])
            if overlap >= threshold:
                duplicate_of = kept_person["id"]
                duplicate_iou = overlap
                break
        person["dedupe"] = {
            "suppressed": duplicate_of is not None,
            "duplicate_of": duplicate_of,
            "iou": duplicate_iou,
            "threshold": threshold,
        }
        if duplicate_of is None:
            kept.append(person)
    return sorted(kept, key=lambda item: item.get("_order", 0))


def class_summary(detections: list[dict[str, Any]]) -> str:
    classes = ordered_class_names(det["class"] for det in detections)
    if not classes:
        return "unknown"
    return ", ".join(classes)


def class_slot(class_name: str) -> str:
    if class_name in TOP_CLASSES:
        return "top"
    if class_name in DRESS_CLASSES:
        return "dress"
    if class_name in BOTTOM_CLASSES:
        return "bottom"
    return "other"


def ordered_class_names(classes: Any) -> list[str]:
    classes = list(classes)
    seen = set()
    result = []
    for class_name in CLASS_DISPLAY_ORDER:
        if class_name in classes and class_name not in seen:
            result.append(class_name)
            seen.add(class_name)
    for class_name in classes:
        if class_name not in seen:
            result.append(class_name)
            seen.add(class_name)
    return result


def update_track_votes(
    vote_history: dict[int, dict[str, deque[str]]],
    track_id: int,
    detections: list[dict[str, Any]],
    window: int = VOTE_WINDOW,
) -> dict[str, Any]:
    slots = vote_history[track_id]
    for det in detections:
        class_name = det.get("class")
        if not class_name:
            continue
        slot = class_slot(class_name)
        if slot == "other":
            continue
        if slot not in slots:
            slots[slot] = deque(maxlen=window)
        slots[slot].append(class_name)

    slot_items: dict[str, dict[str, Any]] = {}
    for slot in ("top", "dress", "bottom"):
        history = slots.get(slot)
        if not history:
            continue
        counts = Counter(history)
        class_name, votes = counts.most_common(1)[0]
        slot_items[slot] = {
            "slot": slot,
            "class": class_name,
            "votes": votes,
            "total": len(history),
            "ratio": votes / len(history) if history else 0,
        }

    stable: list[dict[str, Any]]
    dress = slot_items.get("dress")
    top = slot_items.get("top")
    bottom = slot_items.get("bottom")
    if dress and (dress["votes"], dress["ratio"]) >= max(
        (top["votes"], top["ratio"]) if top else (0, 0.0),
        (bottom["votes"], bottom["ratio"]) if bottom else (0, 0.0),
    ):
        companions = []
        if top:
            companions.append(top)
        if bottom and bottom["class"] == "trousers":
            companions.append(bottom)
        companion = max(companions, key=lambda item: (item["votes"], item["ratio"]), default=None)
        stable = [dress] + ([companion] if companion else [])
    else:
        stable = [item for item in (top, bottom) if item]

    stable = sorted(stable[:2], key=lambda item: {"top": 0, "dress": 1, "bottom": 2}.get(item["slot"], 99))
    classes = ordered_class_names(item["class"] for item in stable)
    return {"items": stable, "classes": classes, "label": ", ".join(classes) if classes else "unknown"}


def predict_first_window(
    video_path: Path,
    output_dir: Path,
    model_path: Path,
    detector_path: Path,
    seconds: float,
    person_conf: float,
    clothing_conf: float,
    imgsz_person: int,
    imgsz_clothing: int,
    top_k: int,
    batch_size: int,
    frame_stride: int,
    person_iou_dedupe_threshold: float,
    log_every: int,
    device: str,
) -> dict[str, Any]:
    if device == "auto":
        device = "cuda" if torch.cuda.is_available() else "cpu"

    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise RuntimeError(f"Could not open video: {video_path}")

    fps = float(cap.get(cv2.CAP_PROP_FPS) or 30.0)
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    max_frames = min(total_frames, int(math.floor(seconds * fps)))

    detector = YOLO(str(detector_path))
    detector.to(device)
    clothing = YoloPredictor(model_path, device=device, imgsz=imgsz_clothing, conf=clothing_conf)

    frames: list[dict[str, Any]] = []
    prediction_rows: list[dict[str, Any]] = []
    vote_history: dict[int, dict[str, deque[str]]] = defaultdict(dict)

    frame_index = -1
    while frame_index + 1 < max_frames:
        ok, frame = cap.read()
        if not ok:
            break
        frame_index += 1
        if frame_index % max(frame_stride, 1) != 0:
            continue
        if frame_index % log_every == 0:
            print(f"[predict] frame {frame_index}/{max_frames} ({frame_index / fps:.2f}s)", flush=True)

        result = detector.track(
            frame,
            persist=True,
            tracker="bytetrack.yaml",
            classes=[0],
            conf=person_conf,
            imgsz=imgsz_person,
            device=device,
            verbose=False,
        )[0]

        persons: list[dict[str, Any]] = []
        crops: list[Any] = []
        crop_meta: list[dict[str, Any]] = []
        boxes = getattr(result, "boxes", None)
        if boxes is not None and len(boxes) > 0:
            ids = boxes.id
            for det_idx, box in enumerate(boxes):
                bbox = clamp_bbox([int(v) for v in box.xyxy[0].tolist()], width, height)
                if bbox is None:
                    continue
                x1, y1, x2, y2 = bbox
                crop = frame[y1:y2, x1:x2]
                if crop.size == 0:
                    continue
                if ids is not None:
                    track_id = int(ids[det_idx].item())
                else:
                    track_id = -100000 - det_idx
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
                crop_meta.append({"person": person, "offset": (x1, y1), "crop_size": (x2 - x1, y2 - y1)})

        if crops:
            predictions = clothing.predict_batch_top_n(crops, top_k, batch_size)
            for meta, top_predictions in zip(crop_meta, predictions):
                processed = prediction_result(top_predictions, clothing_conf, "outfit")
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
                        target.append(item)
                person["raw_clothing"] = raw_items
                person["clothing"] = final_items
                person["result_clothing"] = final_items
                person["result_label"] = class_summary(final_items)
                person["frame_label"] = person["result_label"]
                person["stable_clothing"] = update_track_votes(vote_history, person["id"], final_items)
                person["stable_label"] = person["stable_clothing"]["label"]
                person["label"] = person["result_label"]
                prediction_rows.append(
                    {
                        "frame": frame_index,
                        "time": frame_index / fps,
                        "person_id": person["id"],
                        "person_bbox": person["bbox"],
                        "person_confidence": person["confidence"],
                        "predicted_classes": [det["class"] for det in final_items],
                        "result_predicted_classes": [det["class"] for det in final_items],
                        "stable_predicted_classes": person["stable_clothing"]["classes"],
                        "clothing": final_items,
                        "raw_clothing": raw_items,
                    }
                )

        persons = dedupe_persons_by_iou(persons, person_iou_dedupe_threshold)
        for person in persons:
            person.pop("_order", None)
        frames.append({"frame": frame_index, "time": frame_index / fps, "persons": persons})

    cap.release()

    metadata = {
        "source_video": str(video_path),
        "fps": fps,
        "width": width,
        "height": height,
        "source_total_frames": total_frames,
        "processed_frames": len(frames),
        "processed_seconds": seconds,
        "frame_stride": frame_stride,
        "device": device,
        "detector_model": str(detector_path),
        "person_conf": person_conf,
        "clothing_conf": clothing_conf,
        "person_iou_dedupe_threshold": person_iou_dedupe_threshold,
        "classes": TARGET_CLASSES,
        "class_colors": CLASS_COLORS,
        "class_display_order": CLASS_DISPLAY_ORDER,
        "vote_window": VOTE_WINDOW,
        "display_label_source": "result_clothing",
    }
    data = {"metadata": metadata, "frames": frames}
    (output_dir / "prediction_results.json").write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    (output_dir / "prediction_results_compact.json").write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    (output_dir / "prediction_data.js").write_text(
        "window.PREDICTION_DATA = " + json.dumps(data, ensure_ascii=False) + ";\n",
        encoding="utf-8",
    )
    write_text_summary(output_dir / "prediction_summary.txt", metadata, prediction_rows)
    return data


def write_text_summary(path: Path, metadata: dict[str, Any], rows: list[dict[str, Any]]) -> None:
    counts: dict[str, int] = {name: 0 for name in TARGET_CLASSES}
    ids = set()
    for row in rows:
        ids.add(row["person_id"])
        for name in row["predicted_classes"]:
            counts[name] = counts.get(name, 0) + 1

    lines = [
        "Bangkok earthquake video clothing/person prediction summary",
        "",
        f"Source video: {metadata['source_video']}",
        f"Processed sampled frames: {metadata['processed_frames']}",
        f"Processed seconds: {metadata['processed_seconds']}",
        f"Frame stride: {metadata['frame_stride']}",
        f"FPS: {metadata['fps']}",
        f"Resolution: {metadata['width']}x{metadata['height']}",
        f"Device: {metadata['device']}",
        f"Unique person IDs: {len(ids)}",
        f"Person prediction rows: {len(rows)}",
        "",
        "Predicted clothing counts:",
    ]
    for name, count in counts.items():
        lines.append(f"- {name}: {count}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_viewer(path: Path, video_url: str, frame_clip_url: str | None = None, frame_clip_start: int = 0) -> None:
    class_filters = "\n".join(
        f'<label><input type="checkbox" class="classFilter" value="{name}" checked> {name}</label>' for name in TARGET_CLASSES
    )
    html = f"""<!doctype html>
<html lang="th">
<head>
  <meta charset="utf-8">
  <title>Video Clothing + Person Prediction Viewer</title>
  <style>
    :root {{ font-family: Arial, sans-serif; color-scheme: light; }}
    body {{ margin: 0; background: #f3f5f7; color: #101820; }}
    header {{ padding: 12px 16px; background: #fff; border-bottom: 1px solid #d9dee5; }}
    h1 {{ margin: 0; font-size: 18px; }}
    .stage {{ position: relative; background: #111; width: 100%; max-height: 76vh; overflow: auto; text-align: center; }}
    #videoWrap {{ position: relative; display: inline-block; line-height: 0; }}
    video {{ max-width: 100vw; max-height: 76vh; display: block; }}
    canvas {{ position: absolute; left: 0; top: 0; pointer-events: none; }}
    .controls {{ display: flex; flex-wrap: wrap; gap: 10px 14px; align-items: center; padding: 12px 16px; background: #fff; border-top: 1px solid #d9dee5; }}
    button, select {{ border: 1px solid #b7c0ca; background: #fff; border-radius: 6px; padding: 7px 10px; }}
    button:hover {{ background: #edf2f7; }}
    label {{ font-size: 13px; white-space: nowrap; }}
    .filters {{ padding: 0 16px 12px; display: flex; flex-wrap: wrap; gap: 10px; background: #fff; }}
    .status {{ margin-left: auto; font-size: 13px; color: #506070; }}
  </style>
</head>
<body>
<header>
  <h1>Video Clothing + Person Prediction Viewer</h1>
</header>
<section class="stage">
  <div id="videoWrap">
    <video id="video" src="{video_url}" controls></video>
    <canvas id="overlay"></canvas>
  </div>
</section>
<section class="controls">
  <button id="playPauseBtn">Play/Pause</button>
  <button id="stopBtn">Stop</button>
  <label>Box mode
    <select id="boxMode">
      <option value="person" selected>คน</option>
      <option value="clothing">เสื้อผ้า</option>
      <option value="both">ทั้งคู่</option>
    </select>
  </label>
  <label><input id="showLabels" type="checkbox" checked> แสดงชื่อ class + id</label>
  <label><input id="showClothingConf" type="checkbox" checked> แสดง conf เสื้อผ้า</label>
  <label><input id="showDots" type="checkbox" checked> แสดงจุดสีด้านล่าง bbox</label>
  <label><input id="showRawClothing" type="checkbox"> แสดงผลก่อนจูน rules (raw boxes)</label>
  <span class="status" id="status"></span>
</section>
<section class="filters">
  <strong>Filter class:</strong>
  {class_filters}
</section>
<script src="prediction_data.js"></script>
<script>
const data = window.PREDICTION_DATA || {{ metadata: {{}}, frames: [] }};
const video = document.getElementById('video');
const canvas = document.getElementById('overlay');
const ctx = canvas.getContext('2d');
const frameByIndex = new Map(data.frames.map(row => [row.frame, row]));
const frameNumbers = data.frames.map(row => row.frame).sort((a, b) => a - b);
const colors = data.metadata.class_colors || {{}};
const classOrder = data.metadata.class_display_order || ["short_sleeve", "long_sleeve", "dress", "shorts", "trousers", "skirt"];
function activeClasses() {{
  return new Set([...document.querySelectorAll('.classFilter:checked')].map(el => el.value));
}}
function orderedClassNames(classes) {{
  const set = new Set(classes || []);
  const ordered = classOrder.filter(name => set.has(name));
  for (const name of set) {{
    if (!ordered.includes(name)) ordered.push(name);
  }}
  return ordered;
}}
function resizeCanvas() {{
  const rect = video.getBoundingClientRect();
  canvas.width = Math.round(rect.width);
  canvas.height = Math.round(rect.height);
}}
function scaledBox(bbox) {{
  const sx = canvas.width / (data.metadata.width || video.videoWidth || canvas.width);
  const sy = canvas.height / (data.metadata.height || video.videoHeight || canvas.height);
  return [bbox[0] * sx, bbox[1] * sy, bbox[2] * sx, bbox[3] * sy];
}}
function drawLabel(text, x, y, color) {{
  if (!document.getElementById('showLabels').checked) return;
  ctx.font = '13px Arial';
  const w = ctx.measureText(text).width + 10;
  const yy = Math.max(0, y - 20);
  ctx.fillStyle = color;
  ctx.fillRect(x, yy, w, 20);
  ctx.fillStyle = '#fff';
  ctx.fillText(text, x + 5, yy + 14);
}}
const analyzedColorHex = {{
  black: '#111827',
  white: '#f8fafc',
  gray: '#94a3b8',
  dark_gray: '#4b5563',
  light_gray: '#cbd5e1',
  silver: '#c0c0c0',
  red: '#dc2626',
  dark_red: '#7f1d1d',
  crimson: '#b91c1c',
  scarlet: '#ef4444',
  maroon: '#7f1d1d',
  burgundy: '#800020',
  orange: '#f97316',
  dark_orange: '#c2410c',
  amber: '#f59e0b',
  peach: '#ffc4a3',
  coral: '#fb7185',
  yellow: '#eab308',
  gold: '#d4af37',
  light_yellow: '#fef08a',
  mustard: '#ca8a04',
  khaki: '#bdb76b',
  green: '#16a34a',
  dark_green: '#166534',
  light_green: '#86efac',
  olive: '#808000',
  lime: '#84cc16',
  forest_green: '#14532d',
  mint: '#98ff98',
  teal: '#0f766e',
  cyan: '#06b6d4',
  aqua: '#00ffff',
  blue: '#2563eb',
  dark_blue: '#1e3a8a',
  light_blue: '#93c5fd',
  navy: '#172554',
  sky_blue: '#38bdf8',
  royal_blue: '#1d4ed8',
  cobalt: '#0047ab',
  turquoise: '#40e0d0',
  indigo: '#4f46e5',
  denim: '#1560bd',
  purple: '#9333ea',
  dark_purple: '#581c87',
  light_purple: '#c084fc',
  violet: '#7c3aed',
  lavender: '#c4b5fd',
  magenta: '#d946ef',
  fuchsia: '#c026d3',
  plum: '#673147',
  brown: '#92400e',
  dark_brown: '#451a03',
  light_brown: '#a16207',
  tan: '#d2b48c',
  beige: '#e7d8b8',
  camel: '#c19a6b',
  cream: '#fffdd0',
  pink: '#ec4899',
  light_pink: '#f9a8d4',
  hot_pink: '#ff1493',
  rose: '#f43f5e',
  salmon: '#fa8072',
  charcoal: '#36454f'
}};
function dominantAnalyzedColor(det) {{
  const primaryDetailed = det && det.primary_detailed_color;
  if (primaryDetailed && analyzedColorHex[primaryDetailed]) return analyzedColorHex[primaryDetailed];
  const colorMap = (det && (det.detailed_colors || det.reid_colors)) || {{}};
  let bestName = null;
  let bestValue = -1;
  for (const [name, value] of Object.entries(colorMap)) {{
    if (Number(value) > bestValue) {{
      bestName = name;
      bestValue = Number(value);
    }}
  }}
  return bestName && analyzedColorHex[bestName] ? analyzedColorHex[bestName] : null;
}}
function clothingSlot(className) {{
  if (className === 'short_sleeve' || className === 'long_sleeve') return 'top';
  if (className === 'shorts' || className === 'trousers' || className === 'skirt') return 'bottom';
  if (className === 'dress') return 'dress';
  return null;
}}
function personDotColors(person) {{
  const slotItems = {{}};
  for (const det of person.result_clothing || person.clothing || []) {{
    const slot = clothingSlot(det.class);
    if (!slot) continue;
    if (!slotItems[slot] || Number(det.confidence || 0) > Number(slotItems[slot].confidence || 0)) {{
      slotItems[slot] = det;
    }}
  }}
  const dots = [];
  for (const slot of ['top', 'dress', 'bottom']) {{
    const color = dominantAnalyzedColor(slotItems[slot]);
    if (color) dots.push(color);
  }}
  return dots.length ? dots : [person.color || '#00a6fb'];
}}
function drawDots(x1, y1, x2, y2, dotColors) {{
  if (!document.getElementById('showDots').checked) return;
  const dots = (dotColors || []).filter(Boolean);
  if (!dots.length) return;
  const spacing = 13;
  const startX = (x1 + x2) / 2 - ((dots.length - 1) * spacing) / 2;
  dots.forEach((color, index) => {{
    ctx.beginPath();
    ctx.arc(startX + index * spacing, y2, 5, 0, Math.PI * 2);
    ctx.fillStyle = color;
    ctx.fill();
    ctx.strokeStyle = '#fff';
    ctx.lineWidth = 2;
    ctx.stroke();
  }});
}}
function drawBox(bbox, color, label, dashed = false, dotColors = null) {{
  if (!bbox) return;
  const [x1, y1, x2, y2] = scaledBox(bbox);
  ctx.strokeStyle = color;
  ctx.lineWidth = 3;
  ctx.setLineDash(dashed ? [7, 5] : []);
  ctx.strokeRect(x1, y1, x2 - x1, y2 - y1);
  ctx.setLineDash([]);
  drawLabel(label, x1, y1, color);
  drawDots(x1, y1, x2, y2, dotColors || [color]);
}}
function bestDetectionsByClass(items, filters) {{
  const best = {{}};
  for (const det of items || []) {{
    if (!filters.has(det.class)) continue;
    const old = best[det.class];
    if (!old || Number(det.confidence || 0) > Number(old.confidence || 0)) {{
      best[det.class] = det;
    }}
  }}
  return orderedClassNames(Object.keys(best)).map(name => best[name]);
}}
function personClothingLabel(items, filters, includeConf) {{
  return bestDetectionsByClass(items, filters).map(det => {{
    const conf = includeConf ? ` ${{Number(det.confidence || 0).toFixed(2)}}` : '';
    return `${{det.class}}${{conf}}`;
  }}).join(', ');
}}
function currentFrameData() {{
  const fps = data.metadata.fps || 30;
  const frame = Math.round(video.currentTime * fps);
  if (frameByIndex.has(frame)) return frameByIndex.get(frame);
  let lo = 0, hi = frameNumbers.length - 1, best = frameNumbers[0];
  while (lo <= hi) {{
    const mid = Math.floor((lo + hi) / 2);
    if (frameNumbers[mid] <= frame) {{
      best = frameNumbers[mid];
      lo = mid + 1;
    }} else {{
      hi = mid - 1;
    }}
  }}
  return frameByIndex.get(best) || {{ frame, persons: [] }};
}}
function draw() {{
  if (!video.videoWidth) return requestAnimationFrame(draw);
  resizeCanvas();
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  const row = currentFrameData();
  const mode = document.getElementById('boxMode').value;
  const filters = activeClasses();
  const showRaw = document.getElementById('showRawClothing').checked;
  for (const person of row.persons || []) {{
    const resultClothing = person.result_clothing || person.clothing || [];
    if (!showRaw && resultClothing.length === 0) continue;
    if (showRaw && resultClothing.length === 0 && !(person.raw_clothing || []).length) continue;
    const labelClothing = showRaw ? (person.raw_clothing || []) : resultClothing;
    const personLabelText = personClothingLabel(labelClothing, filters, document.getElementById('showClothingConf').checked);
    const personLabel = `ID ${{person.id}}${{personLabelText ? ': ' + personLabelText : ''}}`;
    if (mode === 'person' || mode === 'both') {{
      drawBox(person.bbox, person.color || '#00a6fb', personLabel, false, personDotColors(person));
    }}
    if (mode === 'clothing' || mode === 'both') {{
      const clothing = labelClothing;
      for (const det of clothing) {{
        if (!filters.has(det.class)) continue;
        const color = colors[det.class] || '#ffffff';
        const sourceLabel = showRaw ? 'RAW ' : '';
        const confText = document.getElementById('showClothingConf').checked ? ` ${{Number(det.confidence || 0).toFixed(2)}}` : '';
        const label = `${{sourceLabel}}ID ${{person.id}} ${{det.class}}${{confText}}`;
        drawBox(det.bbox, color, label, !det.kept, [dominantAnalyzedColor(det) || color]);
      }}
    }}
  }}
  document.getElementById('status').textContent = `time ${{video.currentTime.toFixed(2)}}s | frame ${{row.frame}} | persons ${{(row.persons || []).length}}`;
  requestAnimationFrame(draw);
}}
document.getElementById('playPauseBtn').onclick = () => video.paused ? video.play() : video.pause();
document.getElementById('stopBtn').onclick = () => {{ video.pause(); video.currentTime = 0; draw(); }};
document.querySelectorAll('input, select').forEach(el => el.addEventListener('change', draw));
window.addEventListener('resize', draw);
video.addEventListener('loadedmetadata', draw);
draw();
</script>
</body>
</html>
"""
    path.write_text(html, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--video", required=True)
    parser.add_argument("--output-dir", default="track_result/bangkok_earthquake_predict_2min")
    parser.add_argument("--model", default="models/prepare_dataset.pt")
    parser.add_argument("--detector", default="yolo11n.pt")
    parser.add_argument("--seconds", type=float, default=120.0)
    parser.add_argument("--frame-start", type=int, default=1000)
    parser.add_argument("--frame-end", type=int, default=1999)
    parser.add_argument("--person-conf", type=float, default=0.25)
    parser.add_argument("--clothing-conf", type=float, default=0.25)
    parser.add_argument("--imgsz-person", type=int, default=640)
    parser.add_argument("--imgsz-clothing", type=int, default=224)
    parser.add_argument("--top-k", type=int, default=20)
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument("--frame-stride", type=int, default=30)
    parser.add_argument("--person-iou-dedupe-threshold", type=float, default=0.50)
    parser.add_argument("--log-every", type=int, default=100)
    parser.add_argument("--device", default="auto")
    args = parser.parse_args()

    output_dir = (WORKSPACE / args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    video_path = Path(args.video).resolve()
    clips = cut_clips(video_path, output_dir, args.seconds, args.frame_start, args.frame_end)
    data = predict_first_window(
        video_path=video_path,
        output_dir=output_dir,
        model_path=(WORKSPACE / args.model).resolve(),
        detector_path=(WORKSPACE / args.detector).resolve(),
        seconds=args.seconds,
        person_conf=args.person_conf,
        clothing_conf=args.clothing_conf,
        imgsz_person=args.imgsz_person,
        imgsz_clothing=args.imgsz_clothing,
        top_k=args.top_k,
        batch_size=args.batch_size,
        frame_stride=args.frame_stride,
        person_iou_dedupe_threshold=args.person_iou_dedupe_threshold,
        log_every=args.log_every,
        device=args.device,
    )
    data["metadata"]["clips"] = clips
    data["metadata"]["frame_clip_start"] = args.frame_start
    data["metadata"]["frame_clip_end"] = args.frame_end
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
        args.frame_start,
    )
    print(
        json.dumps(
            {
                "output_dir": str(output_dir),
                "viewer": str(output_dir / "video_prediction_viewer.html"),
                "first_clip": clips["first_clip"],
                "frame_clip": clips["frame_clip"],
                "processed_frames": data["metadata"]["processed_frames"],
            },
            ensure_ascii=False,
            indent=2,
        ),
        flush=True,
    )


if __name__ == "__main__":
    main()
