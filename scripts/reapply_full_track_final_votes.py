from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path


WORKSPACE = Path(__file__).resolve().parents[1]
SCRIPT_DIR = WORKSPACE / "scripts"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from predict_video_clothing_viewer import file_url, update_track_votes, write_viewer  # noqa: E402
from predict_video_full_pipeline import apply_final_outfit_votes  # noqa: E402


def reapply_stable_votes(data: dict) -> None:
    vote_history = defaultdict(dict)
    for frame in sorted(data.get("frames", []), key=lambda item: int(item.get("frame", 0))):
        for person in frame.get("persons", []):
            track_id = int(person.get("id", -1))
            if track_id < 0:
                continue
            items = person.get("result_clothing") or person.get("clothing") or []
            stable = update_track_votes(vote_history, track_id, items)
            person["stable_clothing"] = stable
            person["stable_label"] = stable.get("label", "unknown")


def reapply(result_dir: Path) -> None:
    result_path = result_dir / "prediction_results.json"
    data = json.loads(result_path.read_text(encoding="utf-8"))
    lost_timeout = int(data.get("metadata", {}).get("final_outfit_lost_timeout_frames") or 30)
    reapply_stable_votes(data)
    apply_final_outfit_votes(data, lost_timeout)
    metadata = data.get("metadata", {})
    clips = metadata.get("clips") or {}
    first_clip = Path(clips.get("first_clip") or metadata["source_video"])
    frame_clip = Path(clips.get("frame_clip") or first_clip)

    result_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    (result_dir / "prediction_results_compact.json").write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    (result_dir / "prediction_data.js").write_text(
        "window.PREDICTION_DATA = " + json.dumps(data, ensure_ascii=False) + ";\n",
        encoding="utf-8",
    )
    write_viewer(
        result_dir / "video_prediction_viewer.html",
        file_url(first_clip),
        file_url(frame_clip),
        int(metadata.get("frame_clip_start", 0)),
    )
    print(result_dir)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("result_dirs", nargs="+")
    args = parser.parse_args()
    for item in args.result_dirs:
        path = Path(item)
        if not path.is_absolute():
            path = WORKSPACE / path
        reapply(path.resolve())


if __name__ == "__main__":
    main()
