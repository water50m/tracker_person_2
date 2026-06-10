"""
LiveStreamPipeline — live RTSP/MJPEG source processing.

Uses the shared FrameProcessor + HybridTracker (same stack as VideoProcessor)
so Re-ID, color analysis, and ID assignment are consistent between batch and
live modes.

Annotated JPEG bytes are pushed to output_queue; on_detection callback is
called per person per processed frame.
"""
from __future__ import annotations

import asyncio
import time
from typing import Callable, Optional


# ── helpers ──────────────────────────────────────────────────────────────────

_ANNOTATION_PALETTE = [
    [255, 0, 0], [0, 255, 0], [0, 0, 255], [255, 255, 0], [255, 0, 255],
    [0, 255, 255], [255, 128, 0], [128, 0, 255], [0, 128, 255], [255, 0, 128],
]


def _id_color(track_id: int) -> list:
    return _ANNOTATION_PALETTE[track_id % len(_ANNOTATION_PALETTE)]


def _to_clothing_dicts(items) -> list:
    """Convert DetectedItem list → dict list compatible with dashboard_api."""
    out = []
    for item in items:
        d = {
            "class_name": item.class_name,
            "confidence": item.confidence,
            "bbox": None,
        }
        if item.detailed_colors:
            d["detailed_colors"] = item.detailed_colors
        if item.color_groups:
            d["color_groups"] = item.color_groups
        out.append(d)
    return out


def _draw_annotations(frame, persons: list):
    import cv2
    annotated = frame.copy()
    for p in persons:
        x1, y1, x2, y2 = p["bbox"]
        cv2.rectangle(annotated, (x1, y1), (x2, y2), (0, 255, 255), 2)
        label = f"ID:{p['id']}"
        if p.get("stable_label"):
            label += f" {p['stable_label']}"
        (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.45, 1)
        y_lbl = y1 - 10
        cv2.rectangle(annotated, (x1, y_lbl - th - 2), (x1 + tw + 4, y_lbl + 2), (0, 255, 255), -1)
        cv2.putText(annotated, label, (x1 + 2, y_lbl), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 0, 0), 1)
    return annotated


# ── per-instance state ────────────────────────────────────────────────────────

class _LiveState:
    """
    Per-camera state for live processing.
    Uses FrameProcessor + HybridTracker singletons (shared with VideoProcessor).
    """

    def __init__(self, camera_id: str, processing_width: int = 640):
        from src.services.frame_processor import FrameProcessor
        from src.services.hybrid_tracker import get_hybrid_tracker
        from src.config_loader import get_reid_config

        self.camera_id = camera_id
        self.processing_width = max(320, processing_width)
        self.frame_processor = FrameProcessor(
            enable_classification=True,
            enable_color_analysis=False,  # color computed once per new track below
            enable_embedding=True,        # respects reid config use_embedding flag
        )
        self.hybrid_tracker = get_hybrid_tracker()
        self._max_lost_age = float(get_reid_config().get("max_lost_age", 2.0))

    def process_frame(self, frame, frame_count: int) -> tuple:
        """
        Process one frame. Returns (annotated_frame, persons_list[dict]).
        Runs synchronously — call via loop.run_in_executor.
        """
        import cv2 as _cv2
        from src.services.ai_processing_types import ProcessingStatus
        from src.ai.color_system import analyze_detailed_colors, get_color_groups

        # Resize to processing_width before AI to reduce GPU/CPU load
        orig_h, orig_w = frame.shape[:2]
        if orig_w > self.processing_width:
            scale = self.processing_width / orig_w
            proc_frame = _cv2.resize(frame, (self.processing_width, int(orig_h * scale)))
        else:
            proc_frame = frame

        result = self.frame_processor.process_frame(proc_frame, frame_number=frame_count)

        persons = []

        active_our_ids = []
        bbox_scale = orig_w / proc_frame.shape[1]  # scale factor proc→orig (1.0 if no resize)

        if result.status == ProcessingStatus.SUCCESS and result.detections:
            from src.services.hybrid_tracker import compute_bbox_quality

            # Pre-collect all bboxes for IoU quality calculation
            all_bboxes_this_frame = []
            for det in result.detections:
                px1, py1, px2, py2 = det.bbox.to_xyxy()
                _x1c = max(0, int(px1 * bbox_scale))
                _y1c = max(0, int(py1 * bbox_scale))
                _x2c = min(orig_w, int(px2 * bbox_scale))
                _y2c = min(orig_h, int(py2 * bbox_scale))
                all_bboxes_this_frame.append((_x1c, _y1c, _x2c, _y2c))

            for det in result.detections:
                byte_id = det.track_id if det.track_id >= 0 else None
                px1, py1, px2, py2 = det.bbox.to_xyxy()
                x1 = int(px1 * bbox_scale); y1 = int(py1 * bbox_scale)
                x2 = int(px2 * bbox_scale); y2 = int(py2 * bbox_scale)
                x1c = max(0, x1); y1c = max(0, y1)
                x2c = min(orig_w, x2); y2c = min(orig_h, y2)
                person_crop = frame[y1c:y2c, x1c:x2c] if x2c > x1c and y2c > y1c else None

                quality = compute_bbox_quality(
                    (x1c, y1c, x2c, y2c), all_bboxes_this_frame, orig_w, orig_h
                )

                # Pre-compute colors
                precomp_colors = None
                precomp_groups = None
                if person_crop is not None and person_crop.size > 0:
                    precomp_colors = analyze_detailed_colors(person_crop)
                    precomp_groups = get_color_groups(precomp_colors)

                # Resolve persistent ID via HybridTracker
                our_id, is_new, is_recovered, _bt_verified = self.hybrid_tracker.match_or_create_track(
                    camera_id=self.camera_id,
                    byte_id=byte_id,
                    person_crop=person_crop,
                    embedder=None,
                    detailed_colors=precomp_colors,
                    color_groups=precomp_groups,
                )
                active_our_ids.append(our_id)

                # Store features — colors updated every frame via rolling buffer
                clothes = [
                    item.class_name for item in (det.items or [])
                    if item.class_name
                ] if is_new else None
                emb = det.embedding.tolist() if (is_new and det.embedding is not None) else None
                self.hybrid_tracker.store_track_features(
                    self.camera_id, our_id,
                    detailed_colors=precomp_colors,
                    color_groups=precomp_groups if is_new else None,
                    embedding=emb,
                    clothes=clothes,
                    bbox=(x1c, y1c, x2c, y2c),
                    frame_size=(orig_w, orig_h),
                    quality=quality,
                )

                if is_recovered:
                    print(f"🔄 [LivePipeline] Track recovered: {our_id} (camera {self.camera_id})")

                # Build output dict (same contract as old pipeline)
                clothing_items = _to_clothing_dicts(det.items or [])
                raw_clothing = _to_clothing_dicts(det.raw_items or [])
                label = ", ".join(
                    item["class_name"] for item in clothing_items if item.get("class_name")
                )

                persons.append({
                    "id": our_id,
                    "original_id": byte_id if byte_id is not None else our_id,
                    "bbox": [x1c, y1c, x2c, y2c],
                    "confidence": det.confidence,
                    "color": _id_color(our_id),
                    "clothing": clothing_items,
                    "raw_clothing": raw_clothing,
                    "result_clothing": clothing_items,
                    "stable_clothing": {"label": label, "classes": [], "items": clothing_items},
                    "stable_label": label,
                    "label": label,
                    "reid_profile": {},
                })

        # Mark disappeared tracks as lost (enables Re-ID on return)
        # Called unconditionally so tracks are marked lost even when no detections.
        self.hybrid_tracker.update_lost_tracks(self.camera_id, active_our_ids, max_age=self._max_lost_age)
        active_byte_ids = {det.track_id for det in (persons or []) if det.track_id >= 0}
        self.hybrid_tracker.update_frame_byte_ids(self.camera_id, active_byte_ids)

        annotated = _draw_annotations(frame, persons)
        return annotated, persons

    def cleanup(self):
        self.hybrid_tracker.cleanup(self.camera_id)


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
        processing_width: int = 640,
        output_height: int = 1080,
        output_queue: Optional[asyncio.Queue] = None,
        on_detection: Optional[Callable] = None,
        stop_event: Optional[asyncio.Event] = None,
        active_event: Optional[asyncio.Event] = None,
    ):
        self.source = source
        self.camera_id = camera_id
        self.frame_skip = max(1, frame_skip)
        self.processing_width = max(320, processing_width)
        # 0 = passthrough (no resize); otherwise cap output height to this value
        self.output_height = max(0, output_height)
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
            state = await run_in_exec(_LiveState, self.camera_id, self.processing_width)
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

        _out_h = self.output_height  # capture for closure

        def _resize_for_output(frame):
            """Downscale frame to output_height if needed. Never upscales."""
            if _out_h == 0:
                return frame
            h, w = frame.shape[:2]
            if h <= _out_h:
                return frame
            scale = _out_h / h
            return cv2.resize(frame, (int(w * scale), _out_h), interpolation=cv2.INTER_AREA)

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

            ok, jpeg = cv2.imencode(".jpg", _resize_for_output(annotated), [cv2.IMWRITE_JPEG_QUALITY, 85])
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
            ok, jpeg = cv2.imencode(".jpg", _resize_for_output(annotated), [cv2.IMWRITE_JPEG_QUALITY, 85])
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
            try:
                state.cleanup()
            except Exception:
                pass
            executor.shutdown(wait=False)
            print(f"[LivePipeline] Stopped — camera {self.camera_id} frames={self._frame_count}")
