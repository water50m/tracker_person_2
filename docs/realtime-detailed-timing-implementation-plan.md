# Detailed Timing Implementation Plan

## Purpose

Before changing the whole realtime architecture, split the large timers into smaller parts so we can answer:

```text
Is the slow part actual GPU inference?
Or CPU preprocess/postprocess/tracking/crop/result extraction?
```

## Step 1 - Add YOLO Internal Speed Timers

Use `result.speed` from Ultralytics for:

```text
person_yolo_preprocess
person_yolo_inference
person_yolo_postprocess
clothing_yolo_preprocess
clothing_yolo_inference
clothing_yolo_postprocess
```

These are model-reported times and should be compared against the outer timers:

```text
person_detect_track
clothing_predict
```

If outer timer is much larger than YOLO speed, the bottleneck is Python/CPU/tracker/sync overhead.

## Step 2 - Add CPU-Side Timers

Add:

```text
person_boxes_extract_crop
clothing_cache_eval
clothing_result_postprocess
clothing_color_basic
clothing_detailed_color
```

`detailed_color_analysis` already exists, but the new names make the summary easier to read.

## Step 3 - Run Short Verification

Run 200 source frames with:

```text
--skip-clip-cut
--json-only-output
--fp16
--monitor-gpu
--monitor-resources
```

Confirm the new timing keys appear in:

```text
timing_summary.json
summary.md
```

## Step 4 - Use Timing To Choose Next Optimization

Decision rules:

```text
If person_yolo_inference dominates:
  try TensorRT / lower imgsz / smaller model

If person_detect_track >> person_yolo_*:
  optimize tracker/postprocess/extraction or avoid model.track()

If clothing_yolo_inference dominates:
  try TensorRT / lower imgsz_clothing / bigger batch

If clothing_predict >> clothing_yolo_*:
  optimize crop batching / Python result extraction

If CPU/color dominates:
  move color to background worker
```

## Step 5 - Next Architecture Work

After detailed timing confirms the bottleneck, implement in this order:

```text
frame prefetch
|
cross-frame clothing batch queue
|
background color worker
|
background JSON writer
|
TensorRT trial
```

