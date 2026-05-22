# Realtime Pipeline Optimization Results

## Current Runs

| Phase | Change | Display FPS | Runtime Excl. Clip Cut | GPU Avg | CPU Avg | Person Time | Clothing Time | Color Time | Re-ID | Notes |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| Baseline local JSON opt | DB/MinIO off, JSON only, FP16, imgsz_person 512, clothing cache 5, monitor every 10 frames, clip_cut still included in reported total | 6.946 | 143.971s | 27.83% | 70.65% | 60.857s | 30.830s | 8.760s | 0.482s | FPS here excludes `clip_cut` manually. |
| Phase 1 | Added `--skip-clip-cut`, monitor every 10 frames | 9.036 | 110.052s | see run logs | see run logs | 45.156s | 24.223s | 7.242s | 0.314s | Big improvement because benchmark no longer does clip generation. |
| Phase 2 | Same as Phase 1, GPU/resource monitor every 60 frames | 7.667 | 130.225s | see run logs | see run logs | 63.036s | 33.405s | 8.500s | 0.369s | Monitor overhead dropped, but detector/clothing timings regressed. Treat as noisy run; repeat before deciding. |
| Phase 3A | `imgsz_person=416` | 9.140 | 109.116s | 21.29% | see run logs | 50.867s | 27.060s | 6.866s | 0.398s | Person rows dropped from 1147 to 951, so speed is partly from fewer detections. |
| Phase 3B | `imgsz_person=384` | 9.514 | 104.967s | 27.71% | see run logs | 52.987s | 24.920s | 6.009s | 0.304s | Fastest so far, but person rows dropped heavily to 717. Likely too aggressive without visual QA. |
| Phase 4A | `clothing_temporal_cache_frames=10`, imgsz_person back to 512 | 6.903 | 144.606s | see run logs | see run logs | 77.078s | 32.086s | 6.779s | 0.463s | Clothing calls dropped, but person detector run was unusually slow. |
| Phase 4B | `clothing_temporal_cache_frames=15`, imgsz_person 512 | 7.986 | 124.818s | see run logs | see run logs | 72.545s | 21.331s | 4.313s | 0.391s | Clothing calls dropped strongly; total still dominated by person detector variability. |
| Phase 5A | `imgsz_clothing=192`, cache 15, imgsz_person 512 | 14.005 | 71.129s | see run logs | see run logs | 37.135s | 11.913s | 3.464s | 0.239s | Best speed so far with same person rows. Needs clothing visual QA because class distribution changed. |
| Phase 5B | `imgsz_clothing=160`, cache 15, imgsz_person 512 | 10.566 | 94.433s | see run logs | see run logs | 51.659s | 15.980s | 3.890s | 0.273s | Slower than 192 and clothing class counts drift more. Not recommended. |

## Phase 1 Details

Output:

```text
E:\ALL_CODE\my-project\track_result\opt_phase1_skip_clip_cut
```

Important metrics:

```text
display frames: 1000
processed frames: 500
person rows after IoU: 1147
ByteTrack new IDs: 28
Re-ID recovered: 1
display FPS: 9.036
total_without_file_db_write: 110.052s
person_detect_track: 45.156s
clothing_predict: 24.223s
detailed_color_analysis: 7.242s
gpu_monitor_sample: 14.601s
```

Result:

`--skip-clip-cut` should stay enabled for benchmark runs. `clip_cut` is not part of realtime inference and was hiding the true pipeline speed.

## Phase 2 Details

Output:

```text
E:\ALL_CODE\my-project\track_result\opt_phase2_monitor60
```

Important metrics:

```text
display frames: 1000
processed frames: 500
person rows after IoU: 1147
ByteTrack new IDs: 28
Re-ID recovered: 1
display FPS: 7.667
total_without_file_db_write: 130.225s
person_detect_track: 63.036s
clothing_predict: 33.405s
detailed_color_analysis: 8.500s
gpu_monitor_sample: 4.082s
```

Result:

Lower monitor frequency worked as intended:

```text
gpu_monitor_sample: 14.601s -> 4.082s
```

But total runtime regressed because model inference timings were slower in this run:

```text
person_detect_track: 45.156s -> 63.036s
clothing_predict: 24.223s -> 33.405s
```

This looks like run-to-run/system-load variability, not a bad change. Repeat Phase 2 later or average multiple runs before making it the official baseline.

## Current Bottleneck

After Phase 1-3, the largest costs are still:

```text
person_detect_track
clothing_predict
detailed_color_analysis
```

Re-ID is not a bottleneck:

```text
reid_online_step < 1 ms/frame
```

## Detailed Timing Implementation

Added detailed timers in `scripts/predict_video_full_pipeline.py`:

```text
person_yolo_preprocess
person_yolo_inference
person_yolo_postprocess
person_boxes_extract_crop
clothing_cache_eval
clothing_yolo_preprocess
clothing_yolo_inference
clothing_yolo_postprocess
clothing_basic_color
```

Smoke test output:

```text
E:\ALL_CODE\my-project\track_result\detailed_timing_smoke_200f
```

Key finding from 200 source frames:

```text
person_detect_track outer: 21.058s
person YOLO reported total: 14.172s
extra model.track/tracker/Python/sync overhead: about 6.886s

clothing_predict outer: 5.755s
clothing YOLO reported total: 4.282s
extra wrapper/Python overhead: about 1.473s
```

This confirms that the large timers are not pure GPU work. The remaining bottleneck is a mix of actual YOLO inference and wrapper/tracking/synchronization overhead.

## Person Mode Comparison

Added benchmark options:

```text
--person-inference-mode track|predict
--disable-clothing
--disable-reid
```

Purpose:

```text
Compare Ultralytics model.track() against plain predict() without clothing/Re-ID noise.
```

1000 source frame result:

| Run | Mode | Display FPS | Person Rows | New IDs | Outer Person Timer | YOLO Inference | YOLO Preprocess | YOLO Postprocess | Notes |
|---|---|---:|---:|---:|---:|---:|---:|---:|---|
| person_only_track_1000f | track | 18.034 | 1147 | 28 | 39.101s | 29.263s | 1.727s | 3.485s | Valid track IDs from ByteTrack. |
| person_only_predict_1000f | predict | 14.027 | 1198 | 1198 | 49.749s | 40.945s | 2.285s | 4.460s | No real track IDs; every detection becomes a new pseudo ID. |

Interpretation:

```text
Plain predict() was not faster in the 1000-frame run.
model.track() should not be replaced blindly.
```

The 200-frame smoke test briefly showed `predict` faster, but the longer run contradicted that. Treat the 200-frame result as warmup/run variability.

Current practical conclusion:

```text
Keep model.track() for now.
Focus next on reducing person_yolo_inference itself:
  - TensorRT / ONNX FP16
  - stable imgsz tests with visual QA
  - frame prefetch to reduce CPU wait around inference
```

## Frame Prefetch Test

Added options:

```text
--frame-prefetch
--frame-prefetch-size 32
```

Person-only comparison:

| Run | Frame Prefetch | Display FPS | Person Rows | Outer Person Timer | YOLO Inference | Total Runtime |
|---|---:|---:|---:|---:|---:|---:|
| person_only_track_1000f | off | 18.034 | 1147 | 39.101s | 29.263s | 55.400s |
| person_only_track_prefetch_1000f | on | 10.425 | 1147 | 80.937s | 61.621s | 95.876s |

Result:

```text
Frame prefetch made this workload slower.
```

Likely cause:

```text
The reader thread competes for CPU/memory bandwidth with YOLO preprocessing/tracking.
Video decode is not the current bottleneck, so prefetch adds contention instead of hiding latency.
```

Decision:

```text
Do not enable frame prefetch for this pipeline yet.
Keep the option for future tests, but default should stay off.
```

## TensorRT / ONNX Export Test

Environment check:

```text
tensorrt: not installed
onnx: not installed
onnxruntime: not installed
onnxruntime-gpu: not installed
```

ONNX export command attempted:

```powershell
$env:YOLO_CONFIG_DIR='E:\ALL_CODE\my-project\.ultralytics'
uv run --frozen python -c "from ultralytics import YOLO; YOLO('yolo11s.pt').export(format='onnx', imgsz=512, half=True, device=0, simplify=False)"
```

Result:

```text
Failed: No module named 'onnx'
Ultralytics tried to install onnx automatically, but network access to PyPI was blocked.
```

TensorRT export command attempted:

```powershell
$env:YOLO_CONFIG_DIR='E:\ALL_CODE\my-project\.ultralytics'
uv run --frozen python -c "from ultralytics import YOLO; YOLO('yolo11s.pt').export(format='engine', imgsz=512, half=True, device=0, workspace=1)"
```

Result:

```text
Failed: No module named 'onnx'
TensorRT export requires ONNX export first, plus onnxslim / onnxruntime-gpu / TensorRT support.
PyPI access was blocked, so export could not proceed.
```

Decision:

```text
TensorRT/ONNX is not testable in the current environment until dependencies are installed.
Needed packages include at least onnx and TensorRT/onnxruntime-gpu related dependencies.
```

Current best optimization path without new dependencies:

```text
Keep frame prefetch off.
Keep model.track().
Keep local-only output for realtime benchmarks.
Use clothing temporal cache 15 after visual QA.
Next useful test: clothing imgsz sweep 224/192/160, or install TensorRT stack and retry export.
```

## Controlled imgsz_person 640 vs 512

Both runs used the same current code and config except `imgsz_person`.

| Metric | imgsz 640 | imgsz 512 | Change |
|---|---:|---:|---:|
| Output FPS | 9.797 | 14.789 | +50.96% |
| Total runtime | 101.764s | 67.457s | -33.71% |
| Person rows after IoU | 1524 | 1147 | -24.74% |
| ByteTrack new IDs | 29 | 28 | -1 |
| Recovered tracks | 0 | 1 | +1 |
| person_detect_track | 43.371s | 29.867s | -31.13% |
| person_yolo_inference | 32.110s | 21.728s | -32.33% |
| clothing_predict count | 549 | 425 | -22.59% |
| clothing_predict time | 28.290s | 16.588s | -41.36% |

Interpretation:

```text
512 is much faster, but detects fewer person rows.
The FPS gain is not only from faster person YOLO; it also reduces downstream clothing work because fewer people/crops are produced.
```

Decision:

```text
Use imgsz_person=512 for speed-focused local realtime runs.
Keep 640 as the quality/reference option when missing small/far people is unacceptable.
```

## Phase 3 Details - Person Image Size Sweep

| Run | imgsz_person | Display FPS | Person Rows | New IDs | Recovered | Person Time | Clothing Time | Color Time |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Phase 1 reference | 512 | 9.036 | 1147 | 28 | 1 | 45.156s | 24.223s | 7.242s |
| Phase 3A | 416 | 9.140 | 951 | 23 | 2 | 50.867s | 27.060s | 6.866s |
| Phase 3B | 384 | 9.514 | 717 | 21 | 1 | 52.987s | 24.920s | 6.009s |

Interpretation:

```text
384 is fastest but loses many person detections.
416 is only slightly faster than 512 and still loses about 17% of person rows.
512 remains the safer default until visual QA confirms 416 is acceptable.
```

Why person time did not reliably decrease:

```text
The run is noisy, and ByteTrack/YOLO overhead is not only raw image size.
Lower imgsz also changes how many detections/crops proceed downstream.
```

## Next Phase

Phase 4 should test clothing temporal cache:

```text
5
10
15
```

Keep:

```text
--skip-clip-cut
--json-only-output
--fp16
--frame-stride 2
--clothing-temporal-cache-frames 5
--color-analysis-resize 64
```

Use monitor interval 60 to reduce benchmark overhead, but compare person/clothing timings carefully because Phase 2 showed variability.

## Phase 4 Details - Clothing Temporal Cache Sweep

| Run | Cache Frames | Display FPS | Person Rows | Clothing Calls | Cache Hits | Color Calls | Recovered | Person Time | Clothing Time | Color Time |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Phase 1 reference | 5 | 9.036 | 1147 | 425 | 726 | 228 | 1 | 45.156s | 24.223s | 7.242s |
| Phase 4A | 10 | 6.903 | 1147 | 269 | 882 | 158 | 3 | 77.078s | 32.086s | 6.779s |
| Phase 4B | 15 | 7.986 | 1147 | 179 | 972 | 111 | 2 | 72.545s | 21.331s | 4.313s |

Interpretation:

```text
Cache 10/15 clearly reduces clothing workload.
Cache 15 reduced clothing calls by 57.9% versus cache 5.
Cache 15 reduced detailed color calls by 51.3% versus cache 5.
```

However, total FPS did not improve in these two runs because `person_detect_track` was much slower than the Phase 1 reference:

```text
Phase 1 person time: 45.156s
Cache 10 person time: 77.078s
Cache 15 person time: 72.545s
```

So the cache optimization is logically useful, but the benchmark needs repeated runs or a more isolated machine state to measure net FPS cleanly.

Current best practical setting:

```text
clothing_temporal_cache_frames=15
```

Reason: it cuts clothing/color workload the most while keeping person rows unchanged. It should be visually checked for label staleness before production.

## Phase 5 Details - Clothing Image Size Sweep

| Run | imgsz_clothing | Display FPS | Person Rows | New IDs | Recovered | Clothing Calls | Person Time | Clothing Time | Color Time |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Phase 4B reference | 224 | 7.986 | 1147 | 28 | 2 | 179 | 72.545s | 21.331s | 4.313s |
| Phase 5A | 192 | 14.005 | 1147 | 28 | 1 | 179 | 37.135s | 11.913s | 3.464s |
| Phase 5B | 160 | 10.566 | 1147 | 28 | 2 | 179 | 51.659s | 15.980s | 3.890s |

Class counts:

| Run | short_sleeve | long_sleeve | shorts | trousers | skirt | dress |
|---|---:|---:|---:|---:|---:|---:|
| Phase 4B 224 | 652 | 453 | 513 | 539 | 26 | 6 |
| Phase 5A 192 | 563 | 492 | 492 | 528 | 16 | 27 |
| Phase 5B 160 | 541 | 401 | 472 | 403 | 5 | 24 |

Interpretation:

```text
imgsz_clothing=192 is the fastest useful result so far.
imgsz_clothing=160 is not better and changes clothing distribution more.
```

`192` should be visually QA checked because dress count increased and short_sleeve/long_sleeve shifted. If acceptable, it is the current best speed setting.

## Current Recommended Config

```text
--skip-clip-cut
--json-only-output
--fp16
--frame-stride 2
--imgsz-person 512
--imgsz-clothing 192
--batch-size 128
--clothing-temporal-cache-frames 15
--detailed-color-stride 5
--color-analysis-resize 64
--gpu-sample-interval-frames 60
--resource-sample-interval-frames 60
```

Current best measured output:

```text
display FPS: 14.005
total runtime: 71.129s / 1000 displayed frames
person rows: 1147
ByteTrack IDs: 28
Re-ID recover: 1
```

## Latest Bottleneck Summary

With DB/MinIO/SQLite/crop-save off, the current bottleneck is now:

```text
1. person_detect_track
2. clothing_predict
3. detailed_color_analysis
4. GPU monitor overhead
```

Best run so far, Phase 5A:

```text
person_detect_track: 37.135s
clothing_predict: 11.913s
detailed_color_analysis: 3.464s
reid_online_step: 0.239s
gpu_monitor_sample: 2.330s
```

Re-ID is not a bottleneck:

```text
0.239s / 500 processed frames = 0.479 ms/frame
```

GPU is still not saturated. The practical explanation is:

```text
person detector runs per frame
CPU prepares crops/postprocesses
clothing model runs on small batches after cache filtering
GPU receives short bursts, then waits for CPU/frame loop
```

Next likely useful optimization:

```text
Frame prefetch + cross-frame clothing batch queue
```

This targets the sequential CPU/GPU waiting pattern directly.
