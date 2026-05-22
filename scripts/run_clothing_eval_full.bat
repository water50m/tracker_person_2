@echo off
setlocal
set "UV_CACHE_DIR=E:\ALL_CODE\my-project\.uv-cache"
cd /d E:\ALL_CODE\my-project

uv run --frozen python tests\evaluation\evaluate_clothing_model.py ^
  --dataset "C:\Users\pmach\Downloads\clothing_me.v1i.yolov11\train" ^
  --data-yaml "C:\Users\pmach\Downloads\clothing_me.v1i.yolov11\data.yaml" ^
  --output-dir "track_result\clothing_model_eval_multilabel_videos" ^
  --model "models\prepare_dataset.pt" ^
  --thresholds 0.25,0.50,0.70 ^
  --top-k 20 ^
  --image-eval-mode multilabel-person ^
  --image-input-mode full ^
  --batch-size 32 ^
  --imgsz 224 ^
  --video-short "E:\ALL_CODE\my-project\tracked_results\combined_results\combined_target_ids.mp4" ^
  --video-long "E:\ALL_CODE\my-project\temp_videos\CAM-01_4p-c0-new.mp4" ^
  --video-long-start-frame 1000 ^
  --video-long-end-frame 1999 ^
  --video-frame-stride 1 ^
  --log-every 50
