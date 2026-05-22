# Realtime Pipeline Optimization Plan

## Goal

Optimize the current realtime tracking pipeline step by step, then test each change separately to identify:

- what actually improves FPS
- what increases GPU utilization
- what hurts Re-ID / clothing stability
- where the bottleneck moves after each optimization

The baseline is the latest local-only optimized run:

```text
display frames: 1000
processed frames: 500
frame_stride: 2
DB/MinIO: disabled
SQLite: disabled
crop save: disabled
FP16: enabled
person imgsz: 512
clothing batch_size: 128
clothing temporal cache: 5 frames
color resize: 64 px
display FPS excluding clip_cut: 6.95 FPS
avg GPU util: 27.83%
max GPU util: 40%
avg CPU: 70.65%
```

## Metrics To Record Every Run

Use the same 1000-frame clip segment unless stated otherwise.

```text
source display frames
processed frames
display FPS excluding clip_cut
processed-frame FPS excluding clip_cut
person_detect_track total / avg
clothing_predict total / avg / count
clothing_temporal_cache_hit count
detailed_color_analysis total / avg / count
reid_online_step total / avg
image_save total
file_write total
avg GPU util / max GPU util
max VRAM used
avg CPU / max CPU
avg RAM used / min RAM available
Re-ID recovered count
ByteTrack new IDs
person rows after IoU
clothing class counts
```

Important: exclude `clip_cut` when judging realtime inference speed.

## Baseline Command

```powershell
$env:UV_CACHE_DIR='E:\ALL_CODE\my-project\.uv-cache'
uv run --frozen python scripts\predict_video_full_pipeline.py `
  --video "E:\ALL_CODE\my-project\temp_videos\YTDown.com_YouTube_LIVE-footage-Bangkok-Earthquake-28-03-25_Media_I5jaBKWPy6g_001_1080p.mp4" `
  --output-dir track_result\baseline_local_json_gpu_opt `
  --seconds 34 `
  --max-source-frames 1000 `
  --frame-start 0 `
  --frame-end 999 `
  --detector yolo11s.pt `
  --person-conf 0.45 `
  --clothing-conf 0.25 `
  --imgsz-person 512 `
  --imgsz-clothing 224 `
  --batch-size 128 `
  --frame-stride 2 `
  --detailed-color-stride 5 `
  --color-analysis-resize 64 `
  --clothing-temporal-cache-frames 5 `
  --person-iou-dedupe-threshold 0.50 `
  --device cuda `
  --fp16 `
  --json-only-output `
  --monitor-gpu `
  --gpu-sample-interval-frames 30 `
  --monitor-resources `
  --resource-sample-interval-frames 30
```

## Phase 1 - Remove Benchmark Noise

### Change

Add an option to skip clip cutting during benchmark runs.

```text
--skip-clip-cut
```

When enabled, do not generate:

- first 2 minute clip
- frame clip
- viewer video assets

### Why

The last run spent about `199.8 sec` in `clip_cut`, which is not realtime inference. It makes progress FPS look worse and adds noise.

### Test

Run baseline with `--skip-clip-cut`.

### Expected Improvement

Reported total runtime should drop sharply, but AI step timings should stay almost the same.

### Pass Criteria

- `clip_cut` is absent or near zero
- display FPS reflects inference only
- prediction outputs remain valid JSON

## Phase 2 - Lower GPU Monitor Overhead

### Change

Use lower-frequency GPU sampling:

```text
--gpu-sample-interval-frames 60
--resource-sample-interval-frames 60
```

### Why

The latest run spent `18.016 sec` calling `nvidia-smi` 100 times. This is useful for diagnosis but too expensive for clean benchmarking.

### Test

Run the same config with sample interval 60.

### Expected Improvement

Runtime should improve by roughly 10-15 seconds on 1000 source frames.

### Pass Criteria

- GPU summary still has enough samples
- `gpu_monitor_sample` total is much lower
- FPS improves without changing detection results materially

## Phase 3 - Person Detector Size Sweep

### Change

Test person detector image sizes:

```text
imgsz_person = 512
imgsz_person = 416
imgsz_person = 384
```

Keep all other settings fixed.

### Why

Current largest AI cost:

```text
person_detect_track = 60.857 sec / 500 processed frames
```

Lower image size should reduce person detection time and may raise FPS.

### Test

Run three separate outputs:

```text
track_result\opt_phase3_person512
track_result\opt_phase3_person416
track_result\opt_phase3_person384
```

### Compare

- person rows after IoU
- ByteTrack new IDs
- Re-ID recovered count
- obvious missed persons in viewer if generated later
- person_detect_track avg
- display FPS

### Pass Criteria

Choose the smallest size that does not noticeably lose important persons or destabilize IDs.

## Phase 4 - Clothing Temporal Cache Sweep

### Change

Test:

```text
clothing_temporal_cache_frames = 5
clothing_temporal_cache_frames = 10
clothing_temporal_cache_frames = 15
```

### Why

Current clothing model calls:

```text
clothing_predict count = 425
temporal cache hits = 726
```

Increasing cache window should reduce clothing model calls.

### Risk

Clothing labels may lag when a new ID is created or bbox changes sharply.

### Test

Compare:

- clothing_predict count
- clothing_temporal_cache_hit count
- final outfit labels
- Re-ID recovered count
- false or stale clothing labels in sample frames

### Pass Criteria

Use the largest cache window that does not noticeably hurt clothing stability or Re-ID.

## Phase 5 - Clothing Image Size Sweep

### Change

Test:

```text
imgsz_clothing = 224
imgsz_clothing = 192
imgsz_clothing = 160
```

### Why

Current second largest AI cost:

```text
clothing_predict = 30.830 sec
```

Lower image size should improve speed.

### Risk

Small clothing objects may become less accurate.

### Test

Compare:

- class counts
- final outfit labels for stable IDs
- wrong clothing crops if generated in inspection mode
- clothing_predict avg
- Re-ID recovered count

### Pass Criteria

Choose smallest size that keeps clothing labels acceptable.

## Phase 6 - Color Analysis Strategy

### Change

Compare:

```text
color_analysis_resize = 64
color_analysis_resize = 48
color_analysis_resize = 32
detailed_color_stride = 5
detailed_color_stride = 10
```

### Why

Current color cost:

```text
detailed_color_analysis = 8.760 sec / 228 items
```

This is no longer the biggest bottleneck but still meaningful.

### Risk

Too small color crops may reduce Re-ID quality.

### Test

Compare:

- Re-ID recovered count
- recovered event scores
- detailed_color_analysis avg
- color distributions for suspicious pairs

### Pass Criteria

Use smallest resize/stride combination that keeps Re-ID decisions stable.

## Phase 7 - Frame Prefetch

### Change

Add a frame reader thread:

```text
VideoCapture read/decode thread
|
bounded queue
|
main inference loop
```

### Why

The main loop currently reads and decodes frame synchronously. Prefetch can hide some decode/IO cost behind GPU inference.

### Implementation Notes

- Use `queue.Queue(maxsize=8-16)`
- Reader thread pushes `(frame_index, frame)`
- Main loop consumes frames
- Preserve source frame numbers
- Stop cleanly at `max_source_frames`

### Test

Compare against same config without prefetch.

### Pass Criteria

- Same number of processed frames
- Same or very similar detections
- Lower wall-clock runtime
- GPU utilization improves

## Phase 8 - Clothing Batch Queue Across Frames

### Change

Instead of running clothing prediction immediately per frame, collect crops across frames:

```text
person detect frame N
|
push person crops to clothing batch queue
|
run clothing model when batch reaches N crops or max wait is reached
|
use last cached clothing result until new result arrives
```

Suggested parameters:

```text
max_batch_size = 128
max_wait_processed_frames = 2 or 3
```

### Why

GPU utilization is low because clothing inference is bursty. Cross-frame batching gives GPU larger continuous work.

### Risk

Adds small clothing label latency.

### Test

Compare:

- clothing_predict count
- clothing_predict avg
- GPU avg/max
- label latency
- Re-ID recovered count

### Pass Criteria

FPS improves and clothing labels remain acceptable.

## Phase 9 - Background Color Worker

### Change

Move detailed color analysis out of the immediate main path:

```text
main loop creates clothing result
|
queue color jobs for ID/slot that need refresh
|
background worker updates color cache
|
Re-ID uses latest available color
```

### Why

Color is CPU work and can block the next GPU frame.

### Risk

Re-ID may need color before worker finishes. Use fallback:

```text
if no fresh color yet:
  keep candidate pending
```

### Test

Compare:

- detailed_color_analysis main-path time
- Re-ID recovered count
- number of delayed candidates
- FPS

### Pass Criteria

Main loop gets faster without reducing correct recover behavior.

## Phase 10 - Background JSON Writer

### Change

Append compact frame results to a queue and write in a separate worker.

### Why

JSON writing is not currently the largest cost, but it should not be in realtime path.

### Test

Compare:

- file_write time
- total runtime
- output JSON integrity

### Pass Criteria

Output is complete and runtime does not regress.

## Phase 11 - TensorRT / ONNX Trial

### Change

Export models after Python-level bottlenecks are reduced:

```text
YOLO11s -> TensorRT FP16
clothing model -> TensorRT FP16
```

### Why

GPU utilization is still low. TensorRT may reduce per-inference overhead and improve throughput.

### Risk

Export/setup complexity and possible numerical differences.

### Test

Run the chosen best config from Phases 1-10 with TensorRT models.

### Pass Criteria

- Faster person_detect_track and/or clothing_predict
- Similar detection counts
- Similar clothing labels
- No major Re-ID regression

## Final Comparison Table

After all phases, create:

```text
docs/realtime-pipeline-optimization-results.md
```

with this table:

| Phase | Change | Display FPS | GPU Avg | CPU Avg | Person Time | Clothing Time | Color Time | Re-ID | Notes |
|---|---|---:|---:|---:|---:|---:|---:|---:|---|
| Baseline | local JSON only | | | | | | | | |
| 1 | skip clip cut | | | | | | | | |
| 2 | lower monitor overhead | | | | | | | | |
| 3 | person imgsz sweep | | | | | | | | |
| 4 | clothing cache sweep | | | | | | | | |
| 5 | clothing imgsz sweep | | | | | | | | |
| 6 | color strategy | | | | | | | | |
| 7 | frame prefetch | | | | | | | | |
| 8 | clothing batch queue | | | | | | | | |
| 9 | color worker | | | | | | | | |
| 10 | JSON writer | | | | | | | | |
| 11 | TensorRT | | | | | | | | |

## Expected Bottleneck Movement

Current bottleneck:

```text
CPU/sequential pipeline + person detect + clothing predict
```

Expected after each major change:

```text
local only
|
person detector becomes biggest cost
|
after lower imgsz_person, clothing predictor may become biggest
|
after clothing cache/batch, CPU postprocess/color may become visible
|
after async workers, GPU inference should dominate
|
then TensorRT becomes worth testing
```

