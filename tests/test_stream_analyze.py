"""
Test stream-analyze endpoint: send first 100 frames and capture AI errors.
Run: python tests/test_stream_analyze.py
"""
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

import asyncio
import cv2

from src.api.video_controller import _realtime_analysis_generator

VIDEO_PATH = r"E:\data\Pa_training\Video\redskirt.mp4"
STREAM_ID  = "test_100frames"
MAX_FRAMES = 100


async def main():
    cap = cv2.VideoCapture(VIDEO_PATH)
    assert cap.isOpened(), f"Cannot open {VIDEO_PATH}"
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    fps   = cap.get(cv2.CAP_PROP_FPS)
    cap.release()
    print(f"Video: {total} frames @ {fps:.1f} fps")
    print(f"Sending first {MAX_FRAMES} frames to stream-analyze ...\n")

    stop_event = asyncio.Event()

    # Stop after MAX_FRAMES processed frames
    frame_count = [0]
    original_gen = _realtime_analysis_generator(
        video_path=VIDEO_PATH,
        stream_id=STREAM_ID,
        stop_event=stop_event,
        show_detector_bbox=True,
        show_detector_track_id=True,
        show_classifier_bbox=False,
        show_classifier_class_name=True,
        show_classifier_count=False,
        classifier_top_n=2,
        save_to_db=False,
        camera_id="cam-1",
        frame_skip=1,
        save_images=False,
        save_bbox_images=False,
        save_json_results=True,
        json_job_id=STREAM_ID,
    )

    t_start = time.perf_counter()
    async for chunk in original_gen:
        frame_count[0] += 1
        if frame_count[0] % 10 == 0:
            print(f"  frame {frame_count[0]} received ({len(chunk)} bytes)")
        if frame_count[0] >= MAX_FRAMES:
            stop_event.set()
            break

    elapsed = time.perf_counter() - t_start
    print(f"\nDone: {frame_count[0]} frames in {elapsed:.1f}s ({frame_count[0]/elapsed:.1f} fps)")

    # Check output file
    from src.config_loader import get_json_storage_root
    out_path = Path(get_json_storage_root()) / STREAM_ID / "prediction_results.json"
    if out_path.exists():
        import json
        data = json.loads(out_path.read_text(encoding="utf-8"))
        print(f"\nprediction_results.json saved:")
        print(f"  keys: {list(data.keys())}")
        tv = data.get("track_votes", {})
        print(f"  track_votes: {len(tv)} tracks")
        for tid, v in tv.items():
            print(f"    track {tid}: {v['stable_label']}")
    else:
        print(f"\nWARNING: {out_path} not found — data was not saved")


if __name__ == "__main__":
    asyncio.run(main())
