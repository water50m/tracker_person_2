@echo off
setlocal
set "UV_CACHE_DIR=E:\ALL_CODE\my-project\.uv-cache"
set "YOLO_CONFIG_DIR=E:\ALL_CODE\my-project\.ultralytics"
cd /d E:\ALL_CODE\my-project

uv run --frozen python scripts\predict_video_clothing_viewer.py ^
  --video "E:\ALL_CODE\my-project\temp_videos\YTDown.com_YouTube_LIVE-footage-Bangkok-Earthquake-28-03-25_Media_I5jaBKWPy6g_001_1080p.mp4" ^
  --output-dir "track_result\bangkok_earthquake_predict_2min" ^
  --seconds 120 ^
  --frame-start 1000 ^
  --frame-end 1999 ^
  --frame-stride 30 ^
  --imgsz-person 320 ^
  --device auto ^
  --log-every 300
