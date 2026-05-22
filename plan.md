# JSON Storage Mode Implementation Plan

## เป้าหมาย

ทำให้ระบบหลังบ้านสลับโหมดบันทึกข้อมูลได้จาก config:

```text
storage.mode = db
หรือ
storage.mode = json
```

โดยโหมด `json` ต้องใช้ได้กับ flow หลักของระบบ:

```text
VIDEO PROCESSING
|
Predict person + clothing + Re-ID
|
Save result เป็น JSON/local assets
|
Investigation/Search อ่านจาก JSON
|
Web viewer แสดงผลและค้นหาบุคคล
```

หลักสำคัญคือไม่ลบ DB flow เดิมทันที แต่เพิ่ม JSON mode เป็นอีก backend path เพื่อให้ทดสอบเทียบกันได้ และ rollback กลับไป DB ได้ง่าย

## สถานะปัจจุบัน

- [x] เพิ่ม `storage.mode` ใน `config/system_settings.json`
- [x] เพิ่ม config getter สำหรับ `storage.mode`, `json_root`, `json_index`
- [x] เพิ่ม settings API ให้ update `storage` ได้
- [x] เพิ่ม JSON controller แยกที่ `/api/json/...`
- [x] `main.py` skip DB startup cleanup เมื่อใช้ `storage.mode=json`
- [x] ทำ `DetectionController` เป็น lazy เพื่อไม่รีบต่อ DB ตั้งแต่ app start
- [x] VIDEO PROCESSING เลือก `/api/json/queue/...` เมื่อ `storage.mode=json`
- [ ] Investigation/Search ยังอ่านจาก DB endpoint เดิม
- [x] Pipeline register/update job เข้า `json_index` เมื่อส่ง `--job-id`

## JSON Data Contract

โครงไฟล์ต่อ 1 processing job:

```text
track_result/{job_id}/
|
+-- prediction_results.json
+-- prediction_results_compact.json
+-- viewer_reid_summary.json
+-- timing_summary.json
+-- gpu_progress.json
+-- resource_progress.json
+-- timing_progress.json
+-- summary.md
+-- video_prediction_viewer.html
+-- crops/
+-- captures/
```

ไฟล์ index กลาง:

```text
track_result/json_jobs/index.json
```

ตัวอย่าง job record:

```json
{
  "id": "bangkok_earthquake_2min_640_stride2",
  "label": "Bangkok earthquake 2min",
  "source": "E:/ALL_CODE/my-project/temp_videos/example.mp4",
  "status": "completed",
  "output_dir": "bangkok_earthquake_2min_640_stride2",
  "path": "E:/ALL_CODE/my-project/track_result/bangkok_earthquake_2min_640_stride2",
  "metadata": {
    "camera_id": "CAM-001",
    "frame_stride": 2,
    "person_conf": 0.45,
    "clothing_conf": 0.25,
    "processed_frames": 1800,
    "fps_output": 7.36,
    "recovered_tracks": 7
  }
}
```

## Backend Flow

```text
Load config
|
Check storage.mode
|
+-- db   -> ใช้ DatabaseService + MinIO flow เดิม
|
+-- json -> ใช้ JsonStorageController + local JSON/local assets
```

## Phase 1: Storage Adapter

เพิ่ม service กลางเพื่อซ่อนว่าเก็บ DB หรือ JSON:

```text
StorageAdapter
|
+-- DbStorageAdapter
|
+-- JsonStorageAdapter
```

งานที่ต้องทำ:

- [x] สร้าง `src/services/storage_adapter.py`
- [x] เพิ่ม interface กลาง เช่น `register_job`, `update_job`, `save_detection_batch`, `finalize_job`
- [ ] ย้าย logic ที่เลือก `db/json` มาไว้ใน adapter แทนการ if กระจายหลายไฟล์
- [x] ให้ `storage.mode` เป็นจุดเลือก adapter เดียวสำหรับงานใหม่ที่เพิ่มในรอบนี้

## Phase 2: JSON Job Controller

ต่อยอด controller ที่มีแล้วให้พร้อมใช้กับ UI:

```text
POST /api/json/jobs
PATCH /api/json/jobs/{job_id}
GET /api/json/jobs
GET /api/json/jobs/{job_id}
GET /api/json/jobs/{job_id}/results
GET /api/json/jobs/{job_id}/summary
GET /api/json/jobs/{job_id}/files/{file_path}
```

งานที่ต้องทำ:

- [x] เพิ่ม controller พื้นฐาน
- [x] อ่าน result/timing/reid summary จาก JSON
- [x] register/update job เข้า `json_index`
- [ ] เพิ่ม pagination สำหรับ `prediction_results.json` ขนาดใหญ่
- [ ] เพิ่ม endpoint สำหรับ crop/capture จาก bbox แบบ on demand
- [ ] เพิ่ม endpoint สำหรับ compact result ที่เหมาะกับ web viewer

## Phase 3: Video Processing JSON Mode

ทำให้ `/E:/ALL_CODE/my-project/scripts/predict_video_full_pipeline.py` เขียนผลแบบ JSON-first และ update job status ระหว่างทำงาน

Flow:

```text
Start video job
|
Register job ใน json_index
|
Run detection/tracking/clothing/Re-ID
|
Write progress ทุก N frame
|
Write prediction_results.json
|
Write timing/reid/gpu/resource summary
|
Finalize job เป็น completed/failed
```

งานที่ต้องทำ:

- [x] เพิ่ม option `--job-id`
- [x] เพิ่ม option `--json-index`
- [x] ตอนเริ่ม run: register job เป็น `processing`
- [x] ระหว่าง run: update `frames_processed`, `progress_pct`, timing summary
- [x] ตอนจบ: update `status=completed`
- [x] ตอน error: update `status=failed` พร้อม error message
- [x] ถ้า `storage.mode=json` ให้ปิด DB/MinIO save โดย default
- [x] ยังเก็บ local JSON เสมอ
- [ ] save crop เฉพาะ recovered/suspicious/wrong clothing หรือ on demand

## Phase 4: Video Queue JSON Mode

ตอนนี้หน้า VIDEO PROCESSING ยังใช้ endpoint เดิม:

```text
/api/video-queue/db-status
/api/video-queue/add
/api/video-queue/upload-add
/api/video-queue/pause
/api/video-queue/resume
/api/video-queue/stop
```

ต้องทำให้มี JSON queue path:

```text
/api/json/queue/status
/api/json/queue/add
/api/json/queue/upload-add
/api/json/queue/pause
/api/json/queue/resume
/api/json/queue/stop
```

งานที่ต้องทำ:

- [x] แยก `JsonVideoQueueController`
- [x] เก็บ queue state ลง `track_result/json_jobs/queue.json`
- [x] upload video แล้วสร้าง job record ใน JSON index
- [x] run pipeline เป็น background process/thread
- [x] status endpoint อ่านจาก JSON ไม่แตะ DB
- [x] action pause/resume/stop ใช้ process terminate แล้ว resume/reprocess เป็นการรันใหม่

## Phase 5: Web VIDEO PROCESSING

ปรับ UI ให้เลือก backend ตาม config:

```text
GET /api/json/status
|
ถ้า storage_mode=json
|
RealtimeTab ใช้ /api/json/queue และ /api/json/jobs
```

งานที่ต้องทำ:

- [x] เพิ่ม frontend API client สำหรับ JSON mode
- [x] เปลี่ยน status polling จาก `/api/video-queue/db-status` เป็น JSON endpoint เมื่อ config เป็น JSON
- [x] job list แสดงจาก JSON queue/index state
- [ ] กดดูผลลัพเปิด viewer จาก local result
- [ ] แสดง timing/reid summary จาก JSON
- [ ] รองรับ video/youtube/ipcam/webcam เหมือนเดิม แต่บันทึก result เป็น JSON

## Phase 6: Investigation/Search JSON Mode

เป้าหมายคือค้นหาบุคคลจากข้อมูล JSON:

```text
input class/color/example image
|
อ่าน prediction_results.json หลาย job
|
เทียบ clothing class + detailed 63 colors
|
คืน candidate tracks/person rows
|
แสดงรูปโดย crop จาก bbox ตอนเปิดผลลัพ
```

งานที่ต้องทำ:

- [ ] สร้าง `JsonInvestigationController`
- [ ] เพิ่ม endpoint `GET /api/json/search/persons`
- [ ] เพิ่ม endpoint `POST /api/json/search/advanced`
- [ ] เพิ่ม endpoint `POST /api/json/search/detect-attributes`
- [ ] เพิ่ม endpoint trace จาก JSON track history
- [ ] ทำ search index cache เพื่อไม่ต้อง scan JSON ใหญ่ทุกครั้ง
- [ ] crop รูปสำหรับแสดงผลจาก bbox แบบ on demand และ cache ไว้

## Phase 7: Search Index

ถ้าอ่าน `prediction_results.json` ทุกครั้งจะช้า ต้องมี index:

```text
track_result/json_jobs/search_index.json
```

ข้อมูลที่ควร index:

- track/person id
- job id
- first_seen_frame / last_seen_frame
- final outfit vote
- class ต่อ slot: top/bottom/dress
- detailed colors 63 สีต่อ slot
- representative frame/bbox
- recovered status
- confidence summary

งานที่ต้องทำ:

- [ ] สร้าง script build index จาก result dir
- [ ] build/update index ตอน job completed
- [ ] ใช้ index สำหรับ Investigation ก่อน แล้วค่อยอ่าน full result เฉพาะตอนเปิด detail

## Phase 8: Asset/Crop Strategy

ไม่ save crop ทุก frame เพื่อลด IO:

```text
Save metadata JSON ก่อน
|
เมื่อ user เปิดผลลัพหรือ search result
|
อ่าน video + bbox
|
crop รูป on demand
|
cache crop ลง local folder
```

งานที่ต้องทำ:

- [ ] endpoint crop by `job_id/frame/person_id`
- [ ] endpoint crop by explicit bbox
- [ ] cache path เช่น `track_result/{job_id}/cache/person_crops/...`
- [ ] cleanup cache ได้จาก UI/system

## Phase 9: Tests

ทดสอบทีละส่วน:

- [ ] Config: เปลี่ยน `storage.mode=db/json` แล้ว backend start ได้ทั้งคู่
- [ ] JSON controller: list/read/update job ได้
- [ ] Pipeline: run 100 frames แล้ว update job progress ได้
- [ ] Pipeline: run จบแล้วได้ result/timing/reid summary ครบ
- [ ] VIDEO PROCESSING: เห็น job status จาก JSON
- [ ] Investigation: search class/color จาก JSON ได้
- [ ] Crop on demand: crop จาก bbox ถูกคน
- [ ] Performance: เปิด search index แล้ว query เร็วกว่าการ scan JSON ใหญ่

## Phase 10: Rollout

ลำดับ rollout ที่ปลอดภัย:

```text
1. เปิด storage.mode=json ใน dev
|
2. ให้ pipeline เขียน JSON + index
|
3. ให้ VIDEO PROCESSING อ่าน JSON queue
|
4. ให้ Investigation อ่าน JSON search index
|
5. ทดสอบเทียบ DB mode
|
6. ค่อยตัด DB/MinIO ออกจาก flow ที่ไม่ใช้
```

## Decision Points

ต้องตัดสินใจก่อน implement ลึก:

- JSON queue จะรองรับ pause/resume จริงแบบไหน
- จะเก็บ raw frame/video source path ยาวแค่ไหน
- crop on demand จะอ่านจาก video ต้นทางหรือจาก rendered output video
- search ด้วย example image จะใช้ clothing detector + color เท่านั้น หรือเพิ่ม visual embedding ในอนาคต
- ต้องการ compact JSON แยกสำหรับ web ทุก job หรือให้ web อ่านผ่าน API เท่านั้น

## งานถัดไปที่ควรเริ่มก่อน

แนะนำเริ่มจากส่วนนี้:

```text
JsonStorageAdapter
|
Pipeline register/update job
|
JSON queue status
|
RealtimeTab อ่าน JSON queue
```

เพราะเป็นแกนที่ทำให้ `VIDEO PROCESSING` ใช้ JSON mode ได้จริงก่อน แล้วค่อยต่อ Investigation/Search ตามมา
