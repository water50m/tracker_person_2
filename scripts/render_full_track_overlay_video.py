from __future__ import annotations

import argparse
import json
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Any

import cv2
import imageio_ffmpeg
import numpy as np


WORKSPACE = Path(__file__).resolve().parents[1]

CLASS_COLORS = {
    "short_sleeve": "#00a6fb",
    "long_sleeve": "#7b2cbf",
    "shorts": "#f77f00",
    "trousers": "#2a9d8f",
    "skirt": "#d62828",
    "dress": "#6a994e",
}


def hex_to_bgr(value: str) -> tuple[int, int, int]:
    text = value.lstrip("#")
    if len(text) != 6:
        return (255, 255, 255)
    r = int(text[0:2], 16)
    g = int(text[2:4], 16)
    b = int(text[4:6], 16)
    return (b, g, r)


def hsl_to_bgr(value: str) -> tuple[int, int, int]:
    match = re.match(r"hsl\((\d+),\s*(\d+)%?,\s*(\d+)%?\)", value or "")
    if not match:
        return (250, 204, 21)
    hue = int(match.group(1)) / 2
    sat = int(match.group(2)) / 100 * 255
    light = int(match.group(3)) / 100 * 255
    hls = [[[hue, light, sat]]]
    pixel = cv2.cvtColor(np.array(hls, dtype="uint8"), cv2.COLOR_HLS2BGR)[0][0]
    return (int(pixel[0]), int(pixel[1]), int(pixel[2]))


def clamp_box(box: list[Any], width: int, height: int) -> tuple[int, int, int, int] | None:
    if not isinstance(box, list) or len(box) != 4:
        return None
    x1, y1, x2, y2 = [int(round(float(v))) for v in box]
    x1 = max(0, min(width - 1, x1))
    y1 = max(0, min(height - 1, y1))
    x2 = max(0, min(width - 1, x2))
    y2 = max(0, min(height - 1, y2))
    if x2 <= x1 or y2 <= y1:
        return None
    return x1, y1, x2, y2


def put_label(frame, text: str, x: int, y: int, color: tuple[int, int, int]) -> None:
    font = cv2.FONT_HERSHEY_SIMPLEX
    scale = 0.52
    thickness = 1
    (tw, th), base = cv2.getTextSize(text, font, scale, thickness)
    y_top = max(0, y - th - base - 8)
    x_left = max(0, min(frame.shape[1] - tw - 8, x))
    cv2.rectangle(frame, (x_left, y_top), (x_left + tw + 8, y_top + th + base + 8), color, -1)
    cv2.putText(frame, text, (x_left + 4, y_top + th + 3), font, scale, (255, 255, 255), thickness, cv2.LINE_AA)


def draw_box(
    frame,
    box: tuple[int, int, int, int],
    color: tuple[int, int, int],
    label: str,
    thickness: int = 2,
    dot: bool = True,
) -> None:
    x1, y1, x2, y2 = box
    cv2.rectangle(frame, (x1, y1), (x2, y2), color, thickness)
    if dot:
        cv2.circle(frame, ((x1 + x2) // 2, y2), 5, color, -1)
        cv2.circle(frame, ((x1 + x2) // 2, y2), 5, (255, 255, 255), 1)
    if label:
        put_label(frame, label, x1, y1, color)


def frame_index(data: dict[str, Any]) -> dict[int, dict[str, Any]]:
    return {int(frame["frame"]): frame for frame in data.get("frames", [])}


def class_summary(items: list[dict[str, Any]]) -> str:
    labels = []
    for item in items:
        name = item.get("class", "")
        if name and name not in labels:
            labels.append(name)
    return "+".join(labels)


def label_for_person(person: dict[str, Any], label_source: str) -> str:
    if label_source == "final":
        return str(person.get("final_label") or person.get("final_outfit", {}).get("label") or "")
    if label_source == "stable":
        return str(person.get("stable_label") or person.get("stable_clothing", {}).get("label") or "")
    final_items = person.get("result_clothing") or person.get("clothing") or []
    return str(person.get("result_label") or person.get("label") or class_summary(final_items) or "")


def render_overlay(
    result_dir: Path,
    output_name: str,
    h264: bool,
    box_mode: str,
    draw_title: bool,
    label_source: str,
) -> Path:
    result_path = result_dir / "prediction_results.json"
    data = json.loads(result_path.read_text(encoding="utf-8"))
    metadata = data["metadata"]
    source_video = Path(metadata["source_video"])
    fps = float(metadata.get("fps") or 30.0)
    width = int(metadata["width"])
    height = int(metadata["height"])
    frames_by_index = frame_index(data)
    max_frame = max(frames_by_index) if frames_by_index else -1

    output_path = result_dir / output_name
    temp_path = output_path
    if h264:
        temp_file = tempfile.NamedTemporaryFile(suffix=".mp4", delete=False)
        temp_path = Path(temp_file.name)
        temp_file.close()

    cap = cv2.VideoCapture(str(source_video))
    if not cap.isOpened():
        raise RuntimeError(f"Could not open source video: {source_video}")

    writer = cv2.VideoWriter(str(temp_path), cv2.VideoWriter_fourcc(*"mp4v"), fps, (width, height))
    if not writer.isOpened():
        raise RuntimeError(f"Could not open video writer: {temp_path}")

    class_colors = {name: hex_to_bgr(color) for name, color in (metadata.get("class_colors") or CLASS_COLORS).items()}
    frame_no = -1
    while frame_no < max_frame:
        ok, frame = cap.read()
        if not ok:
            break
        frame_no += 1
        row = frames_by_index.get(frame_no)
        if row:
            persons = row.get("persons", [])
            for person in persons:
                person_box = clamp_box(person.get("bbox"), width, height)
                if not person_box:
                    continue
                person_color = hsl_to_bgr(person.get("color", ""))
                final_items = person.get("result_clothing") or person.get("clothing") or []
                person_label = label_for_person(person, label_source)
                display_id = person.get("id", "")
                original_id = person.get("original_id", display_id)
                id_text = f"ID {display_id}"
                if original_id != display_id:
                    id_text += f" (orig {original_id})"
                if person_label:
                    id_text += f" | {person_label}"
                if box_mode in {"person", "both"}:
                    draw_box(frame, person_box, person_color, id_text, thickness=2, dot=True)

                if box_mode in {"clothing", "both"}:
                    for item in final_items:
                        item_box = clamp_box(item.get("bbox"), width, height)
                        if not item_box:
                            continue
                        name = item.get("class", "unknown")
                        conf = item.get("confidence")
                        label = name if conf is None else f"{name} {float(conf):.2f}"
                        draw_box(frame, item_box, class_colors.get(name, (255, 255, 255)), label, thickness=2, dot=False)

        if draw_title:
            title = f"{result_dir.name} | {label_source} | frame {frame_no}"
            cv2.rectangle(frame, (10, 10), (min(width - 10, 620), 44), (17, 24, 39), -1)
            cv2.putText(frame, title, (18, 34), cv2.FONT_HERSHEY_SIMPLEX, 0.62, (255, 255, 255), 2, cv2.LINE_AA)
        writer.write(frame)
        if frame_no > 0 and frame_no % 100 == 0:
            print(f"[render] {result_dir.name} frame={frame_no}/{max_frame}", flush=True)

    cap.release()
    writer.release()

    if h264:
        ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
        completed = subprocess.run(
            [
                ffmpeg,
                "-y",
                "-i",
                str(temp_path),
                "-c:v",
                "libx264",
                "-preset",
                "veryfast",
                "-crf",
                "20",
                "-pix_fmt",
                "yuv420p",
                "-movflags",
                "+faststart",
                str(output_path),
            ],
            capture_output=True,
            text=True,
        )
        temp_path.unlink(missing_ok=True)
        if completed.returncode != 0:
            raise RuntimeError(completed.stderr[-4000:])
    return output_path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("result_dirs", nargs="+")
    parser.add_argument("--output-name", default="full_track_overlay.mp4")
    parser.add_argument("--box-mode", choices=["person", "clothing", "both"], default="person")
    parser.add_argument("--label-source", choices=["frame", "stable", "final"], default="final")
    parser.add_argument("--no-title", action="store_true")
    parser.add_argument("--no-h264", action="store_true")
    args = parser.parse_args()

    outputs = []
    for item in args.result_dirs:
        result_dir = (WORKSPACE / item).resolve() if not Path(item).is_absolute() else Path(item).resolve()
        outputs.append(
            str(
                render_overlay(
                    result_dir,
                    args.output_name,
                    h264=not args.no_h264,
                    box_mode=args.box_mode,
                    draw_title=not args.no_title,
                    label_source=args.label_source,
                )
            )
        )
    print(json.dumps({"outputs": outputs}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
