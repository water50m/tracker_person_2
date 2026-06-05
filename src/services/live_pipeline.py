"""
LiveFrameProcessor — same pipeline as stream-analyze (YOLO ByteTrack + clothing + ReID + color),
designed for live RTSP/MJPEG sources.

Runs blocking work in thread-pool executors so the asyncio event loop stays free.
Pushes annotated JPEG bytes to an asyncio.Queue for zero-poll-delay MJPEG relay.
"""
from __future__ import annotations

import asyncio
import copy
import sys
import time
import threading
from collections import defaultdict
from pathlib import Path
from types import SimpleNamespace
from typing import Callable, Optional


# ── helpers ──────────────────────────────────────────────────────────────────

def _scripts_path() -> str:
    return str(Path(__file__).resolve().parents[2] / "scripts")


def _ensure_scripts_on_path():
    p = _scripts_path()
    if p not in sys.path:
        sys.path.insert(0, p)


# ── per-instance state ────────────────────────────────────────────────────────

class _PipelineState:
    """Holds all mutable per-stream state; lives for the lifetime of one stream."""

    def __init__(self):
        _ensure_scripts_on_path()

        from src.config_loader import get_detector_model_path, get_classifier_model_path, get_device
        from src.ai.clothing_predictor import YoloPredictor
        from pipeline_shared import OnlineReID

        device = get_device()

        from ultralytics import YOLO
        detector = YOLO(str(Path(get_detector_model_path()).resolve()))
        detector.to(device)

        classifier = YoloPredictor(get_classifier_model_path())

        reid_args = SimpleNamespace(
            reid_color_threshold=0.70,
            reid_confirmation_frames=30,
            reid_min_hits=10,
            reid_max_gap_frames=45,
            reid_aggregate_slot_history=10,
            disable_reid=False,
        )

        self.detector = detector
        self.classifier = classifier
        self.device = device
        self.vote_history: dict = defaultdict(dict)
        self.clothing_temporal_cache: dict = {}
        self.detailed_color_cache: dict = {}
        self.online_reid = OnlineReID(reid_args)

        self.PERSON_CONF = 0.45
        self.IOU_THRESHOLD = 0.50
        self.TOP_K = 20
        self.BATCH_SIZE = 32
        self.CLOTHING_TEMPORAL_CACHE_FRAMES = 0  # disabled

    # ── per-frame processing (runs in executor thread) ────────────────────────

    def process_frame(self, frame, frame_count: int) -> tuple:
        """
        Process one frame with the full stream-analyze pipeline.
        Returns (annotated_frame, persons_list).
        Runs synchronously — call via loop.run_in_executor.
        """
        import cv2
        _ensure_scripts_on_path()
        from predict_video_clothing_viewer import (
            clamp_bbox, dedupe_persons_by_iou, update_track_votes,
        )
        from pipeline_shared import (
            apply_detailed_color_with_cache, class_summary,
            id_color, profile_from_person,
        )
        from src.ai.clothing_predictor import prediction_result

        h, w = frame.shape[:2]

        # ── YOLO + ByteTrack ─────────────────────────────────────────────────
        result = self.detector.track(
            frame,
            persist=True,
            tracker="bytetrack.yaml",
            classes=[0],
            conf=self.PERSON_CONF,
            imgsz=640,
            device=self.device,
            verbose=False,
        )[0]

        persons = []
        crop_meta = []
        boxes = getattr(result, "boxes", None)
        if boxes is not None and len(boxes) > 0:
            ids = boxes.id
            if ids is not None:
                for i, box in enumerate(boxes):
                    bbox = clamp_bbox([int(v) for v in box.xyxy[0].tolist()], w, h)
                    if bbox is None:
                        continue
                    track_id = int(ids[i].item())
                    if track_id < 0:
                        continue
                    x1, y1, x2, y2 = bbox
                    crop = frame[y1:y2, x1:x2]
                    if crop.size == 0:
                        continue
                    person = {
                        "id": track_id,
                        "original_id": track_id,
                        "bbox": [x1, y1, x2, y2],
                        "confidence": float(box.conf.item()),
                        "color": id_color(track_id),
                        "clothing": [],
                        "raw_clothing": [],
                        "result_clothing": [],
                        "stable_clothing": {"label": "", "classes": []},
                        "stable_label": "",
                        "label": "",
                        "reid_profile": {},
                    }
                    persons.append(person)
                    crop_meta.append({"person": person, "crop": crop, "offset": (x1, y1)})

        # ── Clothing classifier + color ───────────────────────────────────────
        predict_metas, predict_crops = [], []
        for meta in crop_meta:
            p = meta["person"]
            tid = int(p["id"])
            cached = self.clothing_temporal_cache.get(tid)
            cache_age = (
                frame_count - int(cached.get("frame", -(10 ** 9)))
                if cached else 10 ** 9
            )
            if self.CLOTHING_TEMPORAL_CACHE_FRAMES > 0 and cached and cache_age < self.CLOTHING_TEMPORAL_CACHE_FRAMES:
                raw_items = copy.deepcopy(cached.get("raw_clothing") or [])
                final_items = copy.deepcopy(cached.get("result_clothing") or [])
                p["raw_clothing"] = raw_items
                p["clothing"] = final_items
                p["result_clothing"] = final_items
                p["label"] = class_summary(final_items)
                p["stable_clothing"] = update_track_votes(self.vote_history, p["id"], final_items)
                p["stable_label"] = p["stable_clothing"]["label"]
                p["reid_profile"] = profile_from_person(p)
            else:
                predict_metas.append(meta)
                predict_crops.append(meta["crop"])

        if predict_crops:
            preds = self.classifier.predict_batch_top_n(predict_crops, self.TOP_K, self.BATCH_SIZE)
            for meta, top_preds in zip(predict_metas, preds):
                processed = prediction_result(top_preds, 0.25, "outfit")
                x_off, y_off = meta["offset"]
                p = meta["person"]
                raw_items, final_items = [], []
                for src_list, tgt_list in (
                    (processed["raw_detections"], raw_items),
                    (processed["final_detections"], final_items),
                ):
                    for det in src_list:
                        item = dict(det)
                        if item.get("bbox"):
                            cx1, cy1, cx2, cy2 = item["bbox"]
                            item["bbox"] = clamp_bbox(
                                [cx1 + x_off, cy1 + y_off, cx2 + x_off, cy2 + y_off], w, h
                            )
                        if tgt_list is final_items:
                            apply_detailed_color_with_cache(
                                frame, item, w, h,
                                int(p["id"]), frame_count,
                                1, self.detailed_color_cache,
                            )
                        tgt_list.append(item)
                p["raw_clothing"] = raw_items
                p["clothing"] = final_items
                p["result_clothing"] = final_items
                p["label"] = class_summary(final_items)
                p["stable_clothing"] = update_track_votes(self.vote_history, p["id"], final_items)
                p["stable_label"] = p["stable_clothing"]["label"]
                p["reid_profile"] = profile_from_person(p)
                self.clothing_temporal_cache[tid] = {
                    "frame": frame_count,
                    "raw_clothing": copy.deepcopy(raw_items),
                    "result_clothing": copy.deepcopy(final_items),
                }

        # ── IoU dedup + ReID ──────────────────────────────────────────────────
        persons = dedupe_persons_by_iou(persons, self.IOU_THRESHOLD)
        self.online_reid.update(frame_count, persons)

        # ── Draw annotated frame ──────────────────────────────────────────────
        annotated = frame.copy()
        for p in persons:
            x1, y1, x2, y2 = p["bbox"]
            stable_items = (p.get("stable_clothing") or {}).get("items") or p.get("result_clothing") or []
            cv2.rectangle(annotated, (x1, y1), (x2, y2), (0, 255, 255), 2)
            labels = [f"ID:{p['id']}"]
            if p.get("stable_label"):
                labels.append(p["stable_label"])
            y_lbl = y1 - 10
            for lbl in labels:
                (tw, th), _ = cv2.getTextSize(lbl, cv2.FONT_HERSHEY_SIMPLEX, 0.45, 1)
                cv2.rectangle(annotated, (x1, y_lbl - th - 2), (x1 + tw + 4, y_lbl + 2), (0, 255, 255), -1)
                cv2.putText(annotated, lbl, (x1 + 2, y_lbl), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 0, 0), 1)
                y_lbl -= (th + 6)

        return annotated, persons


# ── main pipeline runner ──────────────────────────────────────────────────────

class LiveStreamPipeline:
    """
    Reads a live source (RTSP/MJPEG/HTTP) and processes frames with the
    full stream-analyze pipeline. Pushes annotated JPEG bytes directly into
    output_queue — no polling, zero relay delay.
    """

    def __init__(
        self,
        source: str,
        camera_id: str,
        frame_skip: int = 2,
        output_queue: Optional[asyncio.Queue] = None,
        on_detection: Optional[Callable] = None,
        stop_event: Optional[asyncio.Event] = None,
        active_event: Optional[asyncio.Event] = None,
    ):
        self.source = source
        self.camera_id = camera_id
        self.frame_skip = max(1, frame_skip)
        self.output_queue: asyncio.Queue = output_queue or asyncio.Queue(maxsize=4)
        self.on_detection = on_detection
        self.stop_event = stop_event or asyncio.Event()
        # When active_event is cleared, AI inference pauses (no viewers) but
        # track/ReID state is preserved. Set = run. Default always-on.
        self.active_event = active_event
        self._frame_count = 0
        self._last_persons: list = []
        self._last_persons_frame: int = 0

    async def run(self):
        """Run the pipeline until stop_event is set. Call this as an asyncio task."""
        from concurrent.futures import ThreadPoolExecutor

        loop = asyncio.get_running_loop()

        # Dedicated executor so this pipeline's cap.read / YOLO / encode work never
        # competes for threads with the global pool (MJPEG relays for other cameras —
        # including unreachable ones that stall on connect — use the default pool).
        executor = ThreadPoolExecutor(max_workers=3, thread_name_prefix=f"live-{self.camera_id}")

        def run_in_exec(fn, *args):
            return loop.run_in_executor(executor, fn, *args)

        print(f"[LivePipeline] Initializing models for camera {self.camera_id}…")
        try:
            state = await run_in_exec(_PipelineState)
        except Exception as e:
            print(f"[LivePipeline] Model init failed: {e}")
            executor.shutdown(wait=False)
            return
        print(f"[LivePipeline] Models ready for camera {self.camera_id}")

        import cv2

        def _open_capture():
            open_ms = getattr(cv2, "CAP_PROP_OPEN_TIMEOUT_MSEC", None)
            read_ms = getattr(cv2, "CAP_PROP_READ_TIMEOUT_MSEC", None)
            if open_ms is not None and read_ms is not None:
                try:
                    return cv2.VideoCapture(self.source, cv2.CAP_FFMPEG, [
                        int(open_ms), 5000,
                        int(read_ms), 5000,
                    ])
                except Exception:
                    pass
            return cv2.VideoCapture(self.source)

        cap = await run_in_exec(_open_capture)
        if not await run_in_exec(cap.isOpened):
            print(f"[LivePipeline] Cannot open source: {self.source}")
            await run_in_exec(cap.release)
            return
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        cap.set(cv2.CAP_PROP_READ_TIMEOUT_MSEC, 2000)

        print(f"[LivePipeline] Stream open — camera {self.camera_id} skip={self.frame_skip}")

        # Stage 1: reader task feeds frames into frame_queue
        frame_queue: asyncio.Queue = asyncio.Queue(maxsize=4)

        async def _reader():
            consecutive_errors = 0
            first = False
            t0 = time.time()
            while not self.stop_event.is_set():
                ret, frame = await run_in_exec(cap.read)
                if ret:
                    if not first:
                        first = True
                        print(f"[LivePipeline] First frame — camera {self.camera_id} latency={(time.time()-t0)*1000:.0f}ms")
                    consecutive_errors = 0
                    if frame_queue.full():
                        try:
                            frame_queue.get_nowait()
                        except asyncio.QueueEmpty:
                            pass
                    await frame_queue.put(frame)
                else:
                    if self.stop_event.is_set():
                        break
                    consecutive_errors += 1
                    if consecutive_errors >= 10:
                        print(f"[LivePipeline] Too many read errors, stopping")
                        self.stop_event.set()
                        break
                    await asyncio.sleep(0.1)
            await frame_queue.put(None)  # sentinel

        reader_task = asyncio.create_task(_reader())

        def _push_jpeg(jpeg_bytes: bytes, frame_number: int):
            """Called from executor thread — pushes to output_queue via threadsafe call."""
            try:
                loop.call_soon_threadsafe(_put_nowait_dropping, self.output_queue, jpeg_bytes)
            except Exception:
                pass

        def _put_nowait_dropping(q: asyncio.Queue, item):
            if q.full():
                try:
                    q.get_nowait()
                except asyncio.QueueEmpty:
                    pass
            try:
                q.put_nowait(item)
            except asyncio.QueueFull:
                pass

        def _process_and_push(frame, frame_count: int):
            """Runs in thread pool: AI processing + encode + push."""
            import cv2
            try:
                annotated, persons = state.process_frame(frame, frame_count)
            except Exception as e:
                import traceback
                print(f"[LivePipeline] process_frame error frame {frame_count}: {e}")
                traceback.print_exc()
                annotated, persons = frame, []

            # Update detection cache so skipped frames can reuse it
            self._last_persons = persons
            self._last_persons_frame = frame_count

            if frame_count % 30 == 0 or persons:
                print(f"[LivePipeline] frame {frame_count}: {len(persons)} person(s) detected")

            # Notify detection callback (sync, in thread)
            if self.on_detection and persons:
                for p in persons:
                    try:
                        self.on_detection(p, frame_count)
                    except Exception:
                        pass

            ok, jpeg = cv2.imencode(".jpg", annotated, [cv2.IMWRITE_JPEG_QUALITY, 85])
            if ok:
                _push_jpeg(jpeg.tobytes(), frame_count)
            else:
                print(f"[LivePipeline] imencode FAILED frame {frame_count}")

        def _encode_cached(frame, frame_count: int):
            """Skipped frame — draw cached persons and push without AI."""
            import cv2
            annotated = frame.copy()
            if self._last_persons:
                h, w = annotated.shape[:2]
                for p in self._last_persons:
                    bbox = p.get("bbox", [])
                    if not (isinstance(bbox, (list, tuple)) and len(bbox) == 4):
                        continue
                    x1, y1, x2, y2 = [int(v) for v in bbox]
                    x1c, y1c = max(0, x1), max(0, y1)
                    x2c, y2c = min(w, x2), min(h, y2)
                    if x2c <= x1c or y2c <= y1c:
                        continue
                    cv2.rectangle(annotated, (x1c, y1c), (x2c, y2c), (0, 255, 255), 2)
                    text = f"ID:{p.get('id', '?')} {p.get('stable_label') or ''}"
                    (tw, th), _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, 0.45, 1)
                    ty = max(y1c - 4, th + 2)
                    cv2.rectangle(annotated, (x1c, ty - th - 2), (x1c + tw + 4, ty + 2), (0, 255, 255), -1)
                    cv2.putText(annotated, text, (x1c + 2, ty), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 0, 0), 1)
            ok, jpeg = cv2.imencode(".jpg", annotated, [cv2.IMWRITE_JPEG_QUALITY, 85])
            if ok:
                _push_jpeg(jpeg.tobytes(), frame_count)

        # Stage 2: AI processing loop
        # IMPORTANT: _process_and_push calls YOLO which is NOT thread-safe.
        # We must await it (sequential) to avoid concurrent tracker state corruption.
        # _encode_cached has no YOLO call so it can be fire-and-forget.
        try:
            while True:
                try:
                    frame = await asyncio.wait_for(frame_queue.get(), timeout=2.5)
                except asyncio.TimeoutError:
                    if self.stop_event.is_set():
                        break
                    continue

                if frame is None:  # sentinel
                    break

                # Auto-pause: when no viewers, idle here without running YOLO.
                # Track/ReID state stays intact; reader keeps cap warm so resume
                # picks up the freshest frame instantly.
                if self.active_event is not None and not self.active_event.is_set():
                    print(f"[LivePipeline] Paused (no viewers) — camera {self.camera_id}")
                    try:
                        await asyncio.wait_for(self.active_event.wait(), timeout=2.0)
                        print(f"[LivePipeline] Resumed — camera {self.camera_id}")
                    except asyncio.TimeoutError:
                        if self.stop_event.is_set():
                            break
                    continue

                self._frame_count += 1
                fc = self._frame_count

                if fc % self.frame_skip != 0:
                    # Skipped frame — fire-and-forget encode (no YOLO, thread-safe)
                    run_in_exec(_encode_cached, frame, fc)
                else:
                    # AI frame — await to keep YOLO calls sequential
                    await run_in_exec(_process_and_push, frame, fc)

        finally:
            reader_task.cancel()
            try:
                await reader_task
            except (asyncio.CancelledError, Exception):
                pass
            try:
                await run_in_exec(cap.release)
            except Exception:
                pass
            executor.shutdown(wait=False)
            print(f"[LivePipeline] Stopped — camera {self.camera_id} frames={self._frame_count}")
