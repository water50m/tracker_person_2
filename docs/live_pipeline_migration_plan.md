# LiveStreamPipeline Migration Plan
**Migrate from custom `_PipelineState` → shared `FrameProcessor` + `HybridTracker`**

---

## 1. Goal & Scope

Replace the custom detection/tracking stack inside `LiveStreamPipeline` (`src/services/live_pipeline.py`) with the same `FrameProcessor` + `HybridTracker` used by `VideoProcessor`. This unifies the two pipelines, removes dead code (per-stream model loading, `OnlineReID`, `voting` etc.), and makes live streams benefit from the Re-ID improvements already applied to the batch pipeline.

**Out of scope**: MJPEG relay machinery, asyncio task structure, `active_event`/`stop_event` logic, dashboard API routes, `prediction_results.json` schema.

---

## 2. Current Architecture

```
LiveStreamPipeline
└─ _PipelineState (per-camera)
    ├─ ultralytics.YOLO  (own instance, loads model file)
    ├─ YoloPredictor     (clothing classifier, own instance)
    ├─ OnlineReID        (scripts/pipeline_shared.py, legacy)
    ├─ vote_history, clothing_temporal_cache, detailed_color_cache
    └─ process_frame(frame, frame_count)
         → (annotated_frame, persons_list[dict])
```

Output person dict format (consumed by `dashboard_api.on_detection`):
```python
{
    "id": int,              # persistent track ID
    "original_id": int,     # byte_track ID
    "bbox": [x1,y1,x2,y2],
    "confidence": float,
    "color": [r,g,b],       # id_color(track_id) — for annotation only
    "clothing": [...],      # final_detections list
    "raw_clothing": [...],
    "result_clothing": [...],
    "stable_clothing": {"label": str, "classes": [...], "items": [...]},
    "stable_label": str,
    "label": str,
    "reid_profile": {...},  # from pipeline_shared.profile_from_person
}
```

---

## 3. Target Architecture

```
LiveStreamPipeline
└─ _LiveState (per-camera)  ← replaces _PipelineState
    ├─ FrameProcessor        (shared, ModelManager singleton)
    ├─ HybridTracker         (get_hybrid_tracker() singleton)
    └─ process_frame(frame, frame_count)
         → (annotated_frame, persons_list[dict])   ← same output contract
```

Key differences:
- Model loading uses `ModelManager` singleton → no per-stream reload
- ID assignment: `HybridTracker.match_or_create_track()` → persistent IDs
- Re-ID: same `_calculate_similarity` (color+clothes, no embedding by default)
- `update_lost_tracks()` called once per processed frame
- No `OnlineReID`, no `voting`, no `clothing_temporal_cache`, no `scripts/` path manipulation

---

## 4. Step-by-Step Implementation

### Step 1 — Create `_LiveState` class (replaces `_PipelineState`)

In `live_pipeline.py`, add a new class `_LiveState`:

```python
class _LiveState:
    def __init__(self, camera_id: str):
        from src.services.frame_processor import FrameProcessor
        from src.services.hybrid_tracker import get_hybrid_tracker

        self.camera_id = camera_id
        self.frame_processor = FrameProcessor(
            enable_classification=True,
            enable_color_analysis=False,   # color deferred to first-seen
            enable_embedding=True,         # respects get_reid_config().use_embedding
        )
        self.hybrid_tracker = get_hybrid_tracker()

    def process_frame(self, frame, frame_count: int) -> tuple:
        """Returns (annotated_frame, persons_list[dict])."""
        ...
```

### Step 2 — Implement `_LiveState.process_frame`

```python
def process_frame(self, frame, frame_count: int) -> tuple:
    import cv2
    from src.ai.color_system import analyze_detailed_colors, get_color_groups
    from src.services.ai_processing_types import ProcessingStatus

    result = self.frame_processor.process_frame(frame, frame_number=frame_count)

    persons = []
    if result.status == ProcessingStatus.SUCCESS and result.detections:
        active_our_ids = []

        for det in result.detections:
            byte_id = det.track_id if det.track_id >= 0 else None
            x1, y1, x2, y2 = det.bbox.to_xyxy()
            person_crop = frame[max(0,y1):min(frame.shape[0],y2),
                                max(0,x1):min(frame.shape[1],x2)]

            # Resolve persistent ID via HybridTracker
            our_id, is_new, is_recovered = self.hybrid_tracker.match_or_create_track(
                camera_id=self.camera_id,
                byte_id=byte_id,
                person_crop=person_crop,
                embedder=None,   # embedder passed only when use_embedding=True
                detailed_colors=None,
                color_groups=None,
            )
            active_our_ids.append(our_id)

            # Store features on first appearance
            if is_new and person_crop.size > 0:
                detailed_colors = analyze_detailed_colors(person_crop)
                color_groups = get_color_groups(detailed_colors)
                clothes = [item.class_name for item in (det.items or []) if item.class_name]
                emb = det.embedding.tolist() if det.embedding is not None else None
                self.hybrid_tracker.store_track_features(
                    self.camera_id, our_id,
                    detailed_colors=detailed_colors,
                    color_groups=color_groups,
                    embedding=emb,
                    clothes=clothes,
                )

            # Build output dict (same contract as old _PipelineState)
            clothing_items = _to_clothing_dicts(det.items or [])
            raw_clothing   = _to_clothing_dicts(det.raw_items or [])
            label = ", ".join(
                item["class_name"] for item in clothing_items if item.get("class_name")
            )
            person_dict = {
                "id": our_id,
                "original_id": byte_id if byte_id is not None else our_id,
                "bbox": [x1, y1, x2, y2],
                "confidence": det.confidence,
                "color": _id_color(our_id),
                "clothing": clothing_items,
                "raw_clothing": raw_clothing,
                "result_clothing": clothing_items,
                "stable_clothing": {"label": label, "classes": [], "items": clothing_items},
                "stable_label": label,
                "label": label,
                "reid_profile": {},
            }
            persons.append(person_dict)

        # Mark disappeared tracks as lost
        self.hybrid_tracker.update_lost_tracks(self.camera_id, active_our_ids)

    # Draw annotations
    annotated = _draw_annotations(frame, persons)
    return annotated, persons
```

### Step 3 — Add helper functions

```python
def _to_clothing_dicts(items) -> list:
    """Convert DetectedItem list → dict list (old format)."""
    out = []
    for item in items:
        d = {
            "class_name": item.class_name,
            "confidence": item.confidence,
            "bbox": list(item.bbox.to_xyxy()) if item.bbox else None,
        }
        if item.detailed_colors:
            d["detailed_colors"] = item.detailed_colors
        out.append(d)
    return out


def _id_color(track_id: int) -> list:
    """Deterministic color from ID (same palette as old id_color)."""
    palette = [
        [255,0,0],[0,255,0],[0,0,255],[255,255,0],[255,0,255],
        [0,255,255],[255,128,0],[128,0,255],[0,128,255],[255,0,128],
    ]
    c = palette[track_id % len(palette)]
    return c


def _draw_annotations(frame, persons: list):
    import cv2
    annotated = frame.copy()
    for p in persons:
        x1,y1,x2,y2 = p["bbox"]
        cv2.rectangle(annotated, (x1,y1), (x2,y2), (0,255,255), 2)
        label = f"ID:{p['id']}"
        if p.get("stable_label"):
            label += f" {p['stable_label']}"
        (tw,th),_ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.45, 1)
        y_lbl = y1 - 10
        cv2.rectangle(annotated, (x1, y_lbl-th-2), (x1+tw+4, y_lbl+2), (0,255,255), -1)
        cv2.putText(annotated, label, (x1+2, y_lbl), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0,0,0), 1)
    return annotated
```

### Step 4 — Update `LiveStreamPipeline.__init__` and `run()`

In `run()`, replace:
```python
state = await run_in_exec(_PipelineState)
```
with:
```python
state = await run_in_exec(_LiveState, self.camera_id)
```

Add cleanup in `finally`:
```python
from src.services.hybrid_tracker import cleanup_hybrid_tracker
cleanup_hybrid_tracker(self.camera_id)
```

### Step 5 — Remove dead code

Delete from `live_pipeline.py`:
- `_PipelineState` class (entire class)
- `_ensure_scripts_on_path` and `_scripts_path` helpers
- All `sys.path` manipulation for `scripts/`
- imports: `pipeline_shared`, `predict_video_clothing_viewer`, `OnlineReID`, `SimpleNamespace`, `copy`, `defaultdict`

---

## 5. Files Modified

| File | Change |
|------|--------|
| `src/services/live_pipeline.py` | Replace `_PipelineState` with `_LiveState`; update `run()`; remove dead code |
| *(no other files)* | `FrameProcessor`, `HybridTracker`, `ModelManager` unchanged |

---

## 6. Test Plan

### 6.1 Regression Tests (existing behavior must not break)

**File**: `tests/unit/test_live_pipeline_regression.py`

| Test | What it checks |
|------|----------------|
| `test_output_dict_keys` | Person dict has all required keys: `id, original_id, bbox, confidence, color, clothing, raw_clothing, result_clothing, stable_clothing, stable_label, label, reid_profile` |
| `test_bbox_format` | `bbox` is `[int,int,int,int]` with x2>x1, y2>y1 |
| `test_confidence_range` | `confidence` in `[0.0, 1.0]` |
| `test_id_is_positive_int` | `id` is int ≥ 1 |
| `test_stable_clothing_structure` | `stable_clothing` is dict with `label` (str) and `classes` (list) |
| `test_annotated_frame_shape` | Returned annotated frame same HxWxC as input |
| `test_annotated_frame_dtype` | Returned frame dtype uint8 |
| `test_empty_frame_returns_empty_persons` | Blank frame → persons list empty, no crash |
| `test_stop_event_terminates_pipeline` | `stop_event.set()` causes `run()` to return within 3s |
| `test_on_detection_callback_called` | `on_detection` called once per person per processed frame |
| `test_on_detection_not_called_on_skip` | Skipped frames don't trigger `on_detection` |

### 6.2 New Feature Tests (FrameProcessor + HybridTracker integration)

**File**: `tests/unit/test_live_pipeline_hybrid.py`

| Test | What it checks |
|------|----------------|
| `test_persistent_id_across_frames` | Same person in consecutive frames gets same `id` (not incrementing each frame) |
| `test_new_person_gets_new_id` | New detection after existing one gets different `id` |
| `test_id_starts_at_1` | First detected person has `id == 1` |
| `test_reid_recovery_same_id` | Person disappears 1 frame then reappears → same `id` (lost+recover via color similarity) |
| `test_update_lost_tracks_called` | After person disappears, tracker state has it in `lost_tracks` |
| `test_track_features_stored_on_new` | After first appearance, `hybrid_tracker.get_track_history(cam, id)` returns non-empty dict |
| `test_cleanup_on_stop` | After `run()` returns, `get_hybrid_tracker().get_stats(cam_id)["active_tracks"] == 0` |
| `test_frame_processor_used` | `FrameProcessor.process_frame` is called, not YOLO directly |
| `test_no_scripts_path_manipulation` | `sys.path` does not contain `scripts/` path after `_LiveState` init |

### 6.3 Integration Tests (requires models)

**File**: `tests/integration/test_live_pipeline_e2e.py`

| Test | What it checks |
|------|----------------|
| `test_rtsp_stream_processes_frames` | With a real MJPEG/RTSP URL, pipeline processes ≥1 frame without exception |
| `test_prediction_results_json_format` | `on_detection` callback produces dict compatible with `dashboard_api._save_person_to_json` |
| `test_mjpeg_output_queue_receives_bytes` | `output_queue` receives valid JPEG bytes (>1000 bytes) |

### 6.4 API-level Tests (requires running backend)

Manual test checklist for `http://localhost:3000/dashboard`:

- [ ] Click "Start New" → stream appears in browser within 5s
- [ ] Bounding boxes drawn on detected persons
- [ ] IDs are stable across frames (not flickering every frame)
- [ ] `prediction_results/<camera_id>/` JSON files are written
- [ ] Stopping stream via UI stops the pipeline cleanly (no orphaned threads)
- [ ] Re-starting same camera resets IDs from 1 (HybridTracker cleanup)

---

## 7. Risk Assessment

| Risk | Severity | Mitigation |
|------|----------|------------|
| `detection_confidence` default mismatch (old: 0.45, new: from config 0.5) | Low | Set `PERSON_CONF = get_detection_confidence()` in both paths |
| `ModelManager` singleton loads model once globally; live stream already loaded its own model | Medium | Ensure `ModelManager` is initialized before first `_LiveState` (it is via `main.py` lifespan) |
| YOLO not thread-safe: `FrameProcessor` shares detector across cameras | Medium | Current `run()` already awaits `_process_and_push` sequentially; no concurrent calls per camera |
| `id_color` palette change breaks visual color coding in frontend | Low | Reimplement `_id_color` with same 10-color palette from `pipeline_shared.id_color` |
| `reid_profile` was used by frontend | Low | Check `dashboard_api.py` — if `reid_profile` is just passed through to JSON, empty dict `{}` is fine |

---

## 8. Implementation Order

1. **Write tests first** (`test_live_pipeline_regression.py`) — mock `FrameProcessor` and `HybridTracker`
2. **Implement `_LiveState`** and helpers in `live_pipeline.py`
3. **Run regression tests** — all must pass
4. **Write hybrid feature tests** (`test_live_pipeline_hybrid.py`)
5. **Run feature tests** — verify HybridTracker integration
6. **Delete `_PipelineState`** and dead imports
7. **Manual dashboard test** — verify stream + bounding boxes + JSON output
8. **Run full test suite** — `uv run pytest tests/unit/`

---

## 9. Estimated Complexity

- `_LiveState` class: ~80 lines
- Helper functions (`_to_clothing_dicts`, `_id_color`, `_draw_annotations`): ~40 lines
- Lines removed (all of `_PipelineState` + helpers): ~120 lines
- Net change: ≈0 (replacement, not growth)
- Test files: ~150 lines total (unit mocks, no real models needed)
