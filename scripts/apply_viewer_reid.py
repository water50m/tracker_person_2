from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import cv2

from predict_video_clothing_viewer import file_url, id_color, write_viewer


TOP_CLASSES = {"short_sleeve", "long_sleeve"}
BOTTOM_CLASSES = {"shorts", "trousers", "skirt"}


def color_distribution(crop) -> dict[str, float]:
    if crop is None or crop.size == 0:
        return {}
    hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
    h = hsv[:, :, 0]
    s = hsv[:, :, 1]
    v = hsv[:, :, 2]
    masks = {
        "black": v < 45,
        "white": (v > 205) & (s < 35),
        "gray": (s < 40) & (v >= 45) & (v <= 205),
        "red": ((h < 8) | (h >= 170)) & (s >= 40) & (v >= 45),
        "orange": (h >= 8) & (h < 22) & (s >= 40) & (v >= 45),
        "yellow": (h >= 22) & (h < 35) & (s >= 40) & (v >= 45),
        "green": (h >= 35) & (h < 85) & (s >= 40) & (v >= 45),
        "cyan": (h >= 85) & (h < 100) & (s >= 40) & (v >= 45),
        "blue": (h >= 100) & (h < 130) & (s >= 40) & (v >= 45),
        "purple": (h >= 130) & (h < 155) & (s >= 40) & (v >= 45),
        "pink": (h >= 155) & (h < 170) & (s >= 40) & (v >= 45),
    }
    total = float(h.size)
    values = {name: round(float(mask.sum()) * 100.0 / total, 4) for name, mask in masks.items()}
    return {name: pct for name, pct in values.items() if pct >= 1.0}


def color_score(a: dict[str, float], b: dict[str, float]) -> float | None:
    if not a or not b:
        return None
    keys = set(a) | set(b)
    distance = sum(abs(a.get(key, 0.0) - b.get(key, 0.0)) for key in keys)
    return max(0.0, 1.0 - distance / 200.0)


def average_color_maps(maps: list[dict[str, float]]) -> dict[str, float]:
    maps = [item for item in maps if item]
    if not maps:
        return {}
    keys = set().union(*(item.keys() for item in maps))
    return {key: sum(item.get(key, 0.0) for item in maps) / len(maps) for key in keys}


def slot_for_class(class_name: str) -> str | None:
    if class_name in TOP_CLASSES:
        return "top"
    if class_name in BOTTOM_CLASSES:
        return "bottom"
    return None


def profile_from_person(person: dict[str, Any]) -> dict[str, Any]:
    profile: dict[str, Any] = {}
    for item in person.get("result_clothing") or person.get("clothing") or []:
        slot = slot_for_class(item.get("class", ""))
        if slot is None:
            continue
        current = profile.get(slot)
        if current is None or float(item.get("confidence", 0.0)) > float(current.get("confidence", 0.0)):
            profile[slot] = {
                "class": item.get("class"),
                "confidence": float(item.get("confidence", 0.0)),
                "colors": item.get("detailed_colors") or item.get("reid_colors", {}),
                "color_source": "detailed_colors" if item.get("detailed_colors") else "reid_colors",
            }
    return profile


def aggregate_slot(observations: list[dict[str, Any]], slot: str, limit: int) -> dict[str, Any] | None:
    slot_items = [obs["profile"][slot] for obs in observations if slot in obs.get("profile", {})]
    if not slot_items:
        return None
    class_name = Counter(item["class"] for item in slot_items).most_common(1)[0][0]
    matching = [item for item in slot_items if item["class"] == class_name][-limit:]
    return {
        "class": class_name,
        "colors": average_color_maps([item.get("colors", {}) for item in matching]),
        "count": len(matching),
    }


def compare_segment(lost_observations: list[dict[str, Any]], new_observations: list[dict[str, Any]], args) -> dict[str, Any]:
    lost_profile = {
        slot: aggregate_slot(lost_observations, slot, args.aggregate_slot_history)
        for slot in ("top", "bottom")
    }
    hits = {"top": 0, "bottom": 0}
    score_sums = {"top": 0.0, "bottom": 0.0}
    observations = 0
    for obs in new_observations[: args.confirmation_frames]:
        observations += 1
        for slot in ("top", "bottom"):
            lost_slot = lost_profile.get(slot)
            new_slot = obs.get("profile", {}).get(slot)
            if not lost_slot or not new_slot:
                continue
            if lost_slot["class"] != new_slot["class"]:
                continue
            score = color_score(lost_slot.get("colors", {}), new_slot.get("colors", {}))
            if score is None:
                continue
            if score >= args.color_threshold:
                hits[slot] += 1
                score_sums[slot] += score
    top_ok = hits["top"] >= args.min_hits
    bottom_ok = hits["bottom"] >= args.min_hits
    matched_slots = [slot for slot in ("top", "bottom") if hits[slot] > 0]
    avg_scores = {
        slot: (score_sums[slot] / hits[slot] if hits[slot] else None)
        for slot in ("top", "bottom")
    }
    final_scores = [score for score in avg_scores.values() if score is not None]
    return {
        "recover": top_ok and bottom_ok,
        "mode": "both_slots" if top_ok and bottom_ok else "not_recovered",
        "hits": hits,
        "avg_scores": avg_scores,
        "final_score": sum(final_scores) / len(final_scores) if final_scores else None,
        "matched_slots": matched_slots,
        "observations": observations,
        "lost_profile": lost_profile,
    }


def add_reid_colors(data: dict[str, Any], clip_path: Path) -> None:
    frame_map = {frame["frame"]: frame for frame in data.get("frames", [])}
    cap = cv2.VideoCapture(str(clip_path))
    frame_idx = -1
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        frame_idx += 1
        frame_row = frame_map.get(frame_idx)
        if frame_row is None:
            continue
        height, width = frame.shape[:2]
        for person in frame_row.get("persons", []):
            for item in person.get("result_clothing") or person.get("clothing") or []:
                x1, y1, x2, y2 = [int(v) for v in item.get("bbox", [0, 0, 0, 0])]
                x1, x2 = max(0, x1), min(width, x2)
                y1, y2 = max(0, y1), min(height, y2)
                item["reid_colors"] = color_distribution(frame[y1:y2, x1:x2])
            person["reid_profile"] = profile_from_person(person)
    cap.release()


def apply_reid(data: dict[str, Any], args) -> dict[str, Any]:
    observations_by_id: dict[int, list[dict[str, Any]]] = defaultdict(list)
    first_frame: dict[int, int] = {}
    last_frame: dict[int, int] = {}
    for frame in data.get("frames", []):
        frame_no = int(frame["frame"])
        for person in frame.get("persons", []):
            byte_id = int(person["id"])
            obs = {"frame": frame_no, "profile": person.get("reid_profile", {}), "bbox": person.get("bbox", [])}
            observations_by_id[byte_id].append(obs)
            first_frame.setdefault(byte_id, frame_no)
            last_frame[byte_id] = frame_no

    parent: dict[int, int] = {track_id: track_id for track_id in observations_by_id}
    recovered_events = []
    ordered_ids = sorted(observations_by_id, key=lambda track_id: first_frame[track_id])
    finished_ids: list[int] = []
    for new_id in ordered_ids:
        start = first_frame[new_id]
        candidates = [
            old_id
            for old_id in finished_ids
            if 0 < start - last_frame[old_id] <= args.max_gap_frames
        ]
        best_event = None
        for old_id in candidates:
            result = compare_segment(observations_by_id[old_id], observations_by_id[new_id], args)
            if not result["recover"]:
                continue
            event = {
                "new_id": new_id,
                "recovered_id": parent.get(old_id, old_id),
                "candidate_id": old_id,
                "start_frame": start,
                "lost_last_frame": last_frame[old_id],
                "gap_frames": start - last_frame[old_id],
                **result,
            }
            if best_event is None or (event.get("final_score") or 0) > (best_event.get("final_score") or 0):
                best_event = event
        if best_event:
            parent[new_id] = best_event["recovered_id"]
            recovered_events.append(best_event)
        finished_ids.append(new_id)

    remapped = 0
    for frame in data.get("frames", []):
        for person in frame.get("persons", []):
            original_id = int(person["id"])
            canonical_id = parent.get(original_id, original_id)
            if canonical_id != original_id:
                person["original_id"] = original_id
                person["id"] = canonical_id
                person["color"] = id_color(canonical_id)
                person["reid_recovered"] = True
                remapped += 1
            else:
                person["original_id"] = original_id
                person["reid_recovered"] = False

    return {
        "enabled": True,
        "color_threshold": args.color_threshold,
        "confirmation_frames": args.confirmation_frames,
        "min_hits": args.min_hits,
        "max_gap_frames": args.max_gap_frames,
        "aggregate_slot_history": args.aggregate_slot_history,
        "recovered_tracks": len(recovered_events),
        "remapped_person_rows": remapped,
        "events": recovered_events,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--color-threshold", type=float, default=0.70)
    parser.add_argument("--confirmation-frames", type=int, default=30)
    parser.add_argument("--min-hits", type=int, default=10)
    parser.add_argument("--max-gap-frames", type=int, default=45)
    parser.add_argument("--aggregate-slot-history", type=int, default=10)
    args = parser.parse_args()

    output_dir = Path(args.output_dir).resolve()
    result_path = output_dir / "prediction_results.json"
    data = json.loads(result_path.read_text(encoding="utf-8"))
    clips = data.get("metadata", {}).get("clips", {})
    clip_path = Path(clips.get("first_clip", output_dir / "bangkok_earthquake_first_2min.mp4"))
    if not clip_path.is_absolute():
        clip_path = output_dir / clip_path

    add_reid_colors(data, clip_path)
    summary = apply_reid(data, args)
    metadata = data.setdefault("metadata", {})
    metadata["viewer_reid"] = summary
    metadata["display_id_source"] = "viewer_reid_clothing_color"

    result_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    (output_dir / "prediction_results_compact.json").write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    (output_dir / "prediction_data.js").write_text(
        "window.PREDICTION_DATA = " + json.dumps(data, ensure_ascii=False) + ";\n",
        encoding="utf-8",
    )
    write_viewer(
        output_dir / "video_prediction_viewer.html",
        file_url(Path(clips.get("first_clip", output_dir / "bangkok_earthquake_first_2min.mp4"))),
        file_url(Path(clips.get("frame_clip", output_dir / "bangkok_earthquake_frames_1000_1999.mp4"))),
        int(metadata.get("frame_clip_start", 1000)),
    )
    (output_dir / "viewer_reid_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
