from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import cv2
import numpy as np


CLASS_COLORS = {
    "short_sleeve": (44, 125, 255),
    "long_sleeve": (0, 180, 255),
    "shorts": (70, 200, 70),
    "trousers": (255, 120, 40),
    "skirt": (180, 80, 255),
    "dress": (255, 80, 180),
}


def clamp_bbox(bbox: list[int], width: int, height: int) -> list[int]:
    x1, y1, x2, y2 = [int(v) for v in bbox]
    x1 = max(0, min(width - 1, x1))
    y1 = max(0, min(height - 1, y1))
    x2 = max(x1 + 1, min(width, x2))
    y2 = max(y1 + 1, min(height, y2))
    return [x1, y1, x2, y2]


def expanded_crop(frame: np.ndarray, bbox: list[int], pad_ratio: float = 0.0) -> tuple[np.ndarray, tuple[int, int]]:
    height, width = frame.shape[:2]
    x1, y1, x2, y2 = clamp_bbox(bbox, width, height)
    bw = x2 - x1
    bh = y2 - y1
    pad_x = int(bw * pad_ratio)
    pad_y = int(bh * pad_ratio)
    cx1 = max(0, x1 - pad_x)
    cy1 = max(0, y1 - pad_y)
    cx2 = min(width, x2 + pad_x)
    cy2 = min(height, y2 + pad_y)
    return frame[cy1:cy2, cx1:cx2].copy(), (cx1, cy1)


def draw_label(img: np.ndarray, text: str, x: int, y: int, color: tuple[int, int, int]) -> None:
    font = cv2.FONT_HERSHEY_SIMPLEX
    scale = 0.54
    thickness = 1
    (tw, th), baseline = cv2.getTextSize(text, font, scale, thickness)
    y = max(th + 6, y)
    cv2.rectangle(img, (x, y - th - baseline - 8), (x + tw + 8, y + 4), color, -1)
    cv2.putText(img, text, (x + 4, y - baseline - 2), font, scale, (255, 255, 255), thickness, cv2.LINE_AA)


def draw_person_panel(
    frame: np.ndarray,
    person: dict[str, Any],
    title: str,
    subtitle: str,
    target_width: int = 620,
    target_height: int = 520,
    draw_boxes: bool = False,
) -> np.ndarray:
    height, width = frame.shape[:2]
    person_bbox = clamp_bbox(person["bbox"], width, height)
    crop, (off_x, off_y) = expanded_crop(frame, person_bbox)
    ch, cw = crop.shape[:2]

    def shift(bbox: list[int]) -> list[int]:
        x1, y1, x2, y2 = clamp_bbox(bbox, width, height)
        return [x1 - off_x, y1 - off_y, x2 - off_x, y2 - off_y]

    if draw_boxes:
        px1, py1, px2, py2 = shift(person_bbox)
        cv2.rectangle(crop, (px1, py1), (px2, py2), (0, 255, 255), 3)
        label = person.get("final_label") or person.get("result_label") or person.get("label") or "unknown"
        draw_label(
            crop,
            f"ID {person.get('id')} / original {person.get('original_id', person.get('id'))}: {label}",
            px1,
            py1 - 8,
            (0, 170, 220),
        )

        for item in person.get("result_clothing") or person.get("clothing") or []:
            bbox = item.get("bbox")
            if not bbox:
                continue
            cx1, cy1, cx2, cy2 = shift(bbox)
            cls = item.get("class", "unknown")
            color = CLASS_COLORS.get(cls, (180, 180, 180))
            cv2.rectangle(crop, (cx1, cy1), (cx2, cy2), color, 2)
            conf = item.get("confidence")
            conf_text = f"{float(conf):.2f}" if isinstance(conf, (int, float)) else ""
            draw_label(crop, f"{cls} {conf_text}".strip(), cx1, cy1 - 4, color)

    scale = min(target_width / max(1, cw), target_height / max(1, ch))
    resized = cv2.resize(crop, (max(1, int(cw * scale)), max(1, int(ch * scale))), interpolation=cv2.INTER_AREA)
    canvas = np.full((target_height + 76, target_width, 3), 245, dtype=np.uint8)
    y0 = 76 + (target_height - resized.shape[0]) // 2
    x0 = (target_width - resized.shape[1]) // 2
    canvas[y0 : y0 + resized.shape[0], x0 : x0 + resized.shape[1]] = resized
    cv2.putText(canvas, title, (16, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.72, (20, 20, 20), 2, cv2.LINE_AA)
    cv2.putText(canvas, subtitle, (16, 58), cv2.FONT_HERSHEY_SIMPLEX, 0.52, (70, 70, 70), 1, cv2.LINE_AA)
    return canvas


def frame_index(frames: list[dict[str, Any]]) -> dict[int, dict[str, Any]]:
    return {int(frame["frame"]): frame for frame in frames}


def find_person(frame: dict[str, Any] | None, ids: list[int]) -> dict[str, Any] | None:
    if not frame:
        return None
    for wanted in ids:
        for person in frame.get("persons", []):
            if person.get("original_id") == wanted or person.get("id") == wanted:
                return person
    return None


def nearest_frame_with_person(
    frames_by_no: dict[int, dict[str, Any]],
    target_frame: int,
    ids: list[int],
    radius: int = 8,
) -> tuple[int, dict[str, Any]] | tuple[None, None]:
    for delta in range(radius + 1):
        for frame_no in ([target_frame] if delta == 0 else [target_frame - delta, target_frame + delta]):
            person = find_person(frames_by_no.get(frame_no), ids)
            if person:
                return frame_no, person
    return None, None


def read_video_frame(cap: cv2.VideoCapture, frame_no: int) -> np.ndarray:
    cap.set(cv2.CAP_PROP_POS_FRAMES, int(frame_no))
    ok, frame = cap.read()
    if not ok or frame is None:
        raise RuntimeError(f"Could not read video frame {frame_no}")
    return frame


def make_event_images(result_dir: Path, out_root: Path, label: str, draw_boxes: bool) -> list[dict[str, Any]]:
    data = json.loads((result_dir / "prediction_results.json").read_text(encoding="utf-8"))
    metadata = data.get("metadata", {})
    events = (metadata.get("viewer_reid") or {}).get("events", [])
    frames_by_no = frame_index(data.get("frames", []))
    video_path = Path(metadata.get("source_video", ""))
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise RuntimeError(f"Could not open source video: {video_path}")

    out_dir = out_root / label
    out_dir.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, Any]] = []
    for idx, event in enumerate(events, start=1):
        lost_frame = int(event["lost_last_frame"])
        recovered_frame = int(event["recovered_at_frame"])
        lost_ids = [int(event.get("candidate_id", event["recovered_id"])), int(event["recovered_id"])]
        recovered_ids = [int(event["new_id"]), int(event["recovered_id"])]
        lost_frame_no, lost_person = nearest_frame_with_person(frames_by_no, lost_frame, lost_ids)
        recovered_frame_no, recovered_person = nearest_frame_with_person(frames_by_no, recovered_frame, recovered_ids)
        if lost_person is None or recovered_person is None:
            rows.append(
                {
                    "run": label,
                    "index": idx,
                    "missing": True,
                    "event": event,
                }
            )
            continue

        lost_img = read_video_frame(cap, int(lost_frame_no))
        recovered_img = read_video_frame(cap, int(recovered_frame_no))
        score = event.get("final_score", 0.0)
        hits = event.get("hits", {})
        avg = event.get("avg_scores", {})
        lost_panel = draw_person_panel(
            lost_img,
            lost_person,
            f"Before lost: frame {lost_frame_no}",
            f"candidate ID {event.get('candidate_id')} -> recovered ID {event.get('recovered_id')}",
            draw_boxes=draw_boxes,
        )
        recovered_panel = draw_person_panel(
            recovered_img,
            recovered_person,
            f"Recovered: frame {recovered_frame_no}",
            f"new ID {event.get('new_id')} -> display ID {event.get('recovered_id')}",
            draw_boxes=draw_boxes,
        )
        gap = np.full((lost_panel.shape[0], 18, 3), 220, dtype=np.uint8)
        combined = np.hstack([lost_panel, gap, recovered_panel])
        header = np.full((72, combined.shape[1], 3), 30, dtype=np.uint8)
        title = (
            f"{label} event {idx}: new {event.get('new_id')} -> ID {event.get('recovered_id')} | "
            f"score {float(score):.3f} | hits top/bottom {hits.get('top', 0)}/{hits.get('bottom', 0)}"
        )
        cv2.putText(header, title, (18, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.72, (255, 255, 255), 2, cv2.LINE_AA)
        detail = f"top {float(avg.get('top', 0.0)):.3f}, bottom {float(avg.get('bottom', 0.0)):.3f}, gap {event.get('gap_frames')} frames"
        cv2.putText(header, detail, (18, 58), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (210, 230, 255), 1, cv2.LINE_AA)
        final = np.vstack([header, combined])
        filename = f"tight_event_{idx:02d}_new_{event.get('new_id')}_to_{event.get('recovered_id')}_f{lost_frame_no}_f{recovered_frame_no}.jpg"
        out_path = out_dir / filename
        cv2.imwrite(str(out_path), final, [int(cv2.IMWRITE_JPEG_QUALITY), 92])
        rows.append(
            {
                "run": label,
                "index": idx,
                "image": f"reid_captures/{label}/{filename}",
                "new_id": event.get("new_id"),
                "recovered_id": event.get("recovered_id"),
                "candidate_id": event.get("candidate_id"),
                "lost_frame": lost_frame_no,
                "recovered_frame": recovered_frame_no,
                "final_score": round(float(score), 4),
                "top_score": round(float(avg.get("top", 0.0)), 4),
                "bottom_score": round(float(avg.get("bottom", 0.0)), 4),
                "top_hits": hits.get("top", 0),
                "bottom_hits": hits.get("bottom", 0),
                "missing": False,
            }
        )
    cap.release()
    return rows


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--viewer-dir", default="track_result/bangkok_earthquake_2min_compare_viewer")
    parser.add_argument(
        "--run",
        action="append",
        nargs=2,
        metavar=("LABEL", "RESULT_DIR"),
        required=True,
        help="Run label and prediction result directory.",
    )
    parser.add_argument(
        "--draw-boxes",
        action="store_true",
        help="Draw person/clothing boxes on captures. Default is clean crops without overlays.",
    )
    args = parser.parse_args()

    viewer_dir = Path(args.viewer_dir)
    out_root = viewer_dir / "reid_captures"
    all_rows: list[dict[str, Any]] = []
    for label, result_dir in args.run:
        all_rows.extend(make_event_images(Path(result_dir), out_root, label, draw_boxes=args.draw_boxes))

    payload = {"events": all_rows}
    (viewer_dir / "reid_capture_data.js").write_text(
        "window.REID_CAPTURE_DATA = " + json.dumps(payload, ensure_ascii=False, indent=2) + ";\n",
        encoding="utf-8",
    )
    print(json.dumps({"viewer_dir": str(viewer_dir), "events": len(all_rows), "output": str(out_root)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
