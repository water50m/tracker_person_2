@echo off
setlocal
set "UV_CACHE_DIR=E:\ALL_CODE\my-project\.uv-cache"
set "YOLO_CONFIG_DIR=E:\ALL_CODE\my-project\.ultralytics"
cd /d E:\ALL_CODE\my-project

uv run --frozen python scripts\evaluate_clothing_videos_before_after.py ^
  --output-dir track_result\clothing_video_before_after_eval_full ^
  --frame-stride 1 ^
  --device auto ^
  --log-every 100
