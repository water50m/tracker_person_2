# Evaluation Suite for Chapter 4

ชุดนี้เป็น benchmark/evaluation สำหรับข้อมูลจริง แยกจาก unit test ปกติ เพราะต้องใช้โมเดล วิดีโอ รูปภาพ และ annotation ที่อาจใช้เวลานาน

## 1. Clothing Model Test

ใช้ทดสอบโมเดลเสื้อผ้ากับรูป crop หรือ DeepFashion2 crop

Manifest รองรับ CSV/JSON/JSONL:

```csv
image_path,label,x1,y1,x2,y2
img/0001.jpg,long_sleeve,,,,
img/0002.jpg,trousers,120,50,260,430
```

คำสั่ง:

```powershell
python tests/evaluation/evaluate_clothing_model.py `
  --manifest datasets/deepfashion2_crops_eval.csv `
  --image-root datasets/deepfashion2 `
  --model models/prepare_dataset.pt `
  --output my-thesis-report/qa/clothing-model-eval.json
```

Metrics:

- accuracy
- macro F1
- precision / recall / F1 ราย class
- confusion matrix
- average latency ต่อภาพ

## 2. Color Analysis Test

ใช้ทดสอบว่าสีหลักที่ระบบจับตรงกับ label/manual review แค่ไหน

Manifest:

```csv
image_path,primary_color,x1,y1,x2,y2
crop/001.jpg,black,,,,
crop/002.jpg,navy_blue,,,,
```

คำสั่ง:

```powershell
python tests/evaluation/evaluate_color_analysis.py `
  --manifest datasets/color_crops_eval.csv `
  --image-root datasets/color_crops `
  --output my-thesis-report/qa/color-analysis-eval.json
```

Metrics:

- primary color accuracy
- macro F1
- confusion matrix
- average color-analysis latency

## 3. Tracking / Re-ID Comparison

ใช้เปรียบเทียบ ByteTrack only กับ ByteTrack + Re-ID

คำสั่ง:

```powershell
python tests/evaluation/evaluate_tracking_reid.py `
  --video datasets/videos/eval_occlusion.mp4 `
  --ground-truth datasets/videos/eval_occlusion_mot.csv `
  --frame-skip 5 `
  --mode both `
  --output-dir my-thesis-report/qa/tracking-reid
```

Ground truth เป็น MOT-like CSV/JSON/JSONL:

```csv
frame,identity,x,y,w,h
1,P01,100,80,60,180
2,P01,105,82,60,180
```

ถ้าไม่มี ground truth สคริปต์ยังรันได้ แต่จะรายงานได้แค่ proxy metrics เช่นจำนวน unique track id และ average track length ไม่สามารถสรุปว่า Re-ID กู้ถูกหรือผิดได้

Metrics เมื่อมี ground truth:

- matched / missed / false positive
- ID switches
- fragmentation
- unique predicted IDs ต่อ identity
- fragmentation reduction เมื่อเปิด Re-ID
- input FPS, processed FPS, output FPS

Metrics เฉพาะตอนเปิด Re-ID:

- `byte_id_new_events`: จำนวนครั้งที่ ByteTrack สร้าง ID ใหม่ที่ HybridTracker ยังไม่เคย map
- `reid_candidate_events`: จำนวนครั้งที่มีข้อมูลพอให้ลอง Re-ID
- `reid_similarity_attempts`: จำนวนครั้งที่มี lost track ให้เปรียบเทียบจริง
- `recovered_tracks`: จำนวนครั้งที่ Re-ID กู้ persistent ID เดิมสำเร็จ
- `new_tracks`: จำนวนครั้งที่ต้องสร้าง persistent ID ใหม่
- `recovery_rate_per_similarity_attempt`: recovered_tracks / reid_similarity_attempts

วิธีเปรียบเทียบ Re-ID ใน HybridTracker ปัจจุบัน:

- embedding ใช้ cosine similarity ระหว่าง vector ใหม่กับ vector ที่เก็บไว้ใน lost track
- color groups ใช้ Jaccard/IoU ของชุดชื่อกลุ่มสี เช่น intersection / union
- final score คือค่าเฉลี่ยของคะแนนที่คำนวณได้
- ถ้า final score >= threshold `0.7` จะถือว่าเป็นคนเดิมและ recover ID
- `detailed_colors` ถูกเก็บไว้ใน track history แต่ similarity function ปัจจุบันยังไม่ได้นำเปอร์เซ็นต์ detailed colors มาเทียบโดยตรง

ไฟล์ output:

- `tracking-reid-eval.json`
- `tracking-detections.csv`

## 4. Search Accuracy Test

ใช้วัด search precision จากผลลัพธ์ที่ export ออกมาแล้ว

Queries:

```csv
query_id,criteria,relevant_ids
Q001,"black shirt",P01,P07
```

Results:

```csv
query_id,result_id
Q001,P01
Q001,P03
Q001,P07
```

ถ้าระบบ export เป็น detection id แทน person id ให้ใช้ id แบบเดียวกันทั้ง `relevant_ids` และ `result_id`

คำสั่ง:

```powershell
python tests/evaluation/evaluate_search_results.py `
  --queries datasets/search_eval_queries.csv `
  --results datasets/search_eval_results.csv `
  --output my-thesis-report/qa/search-eval.json
```

Metrics:

- precision@5
- precision@10
- recall@10
- mAP

## 5. Database / Storage Audit

ใช้ตรวจ exported detection rows ว่าข้อมูลสำคัญครบ และมี duplicate ผิดปกติไหม

คำสั่ง:

```powershell
python tests/evaluation/audit_detection_export.py `
  --input my-thesis-report/qa/tracking-reid/tracking-detections.csv `
  --output my-thesis-report/qa/detection-export-audit.json
```

ตรวจ:

- `camera_id`
- `track_id`
- `class_name`
- `bbox`
- `image_path`
- `video_time_offset`
- duplicate detection key
- duplicate image path
- embedding dimension distribution

## Run All

คัดลอก `evaluation_config.example.json` เป็น config ของงานจริง แล้วแก้ path ให้ตรงข้อมูลของคุณ

```powershell
python tests/evaluation/run_evaluation_suite.py `
  --config tests/evaluation/evaluation_config.example.json `
  --skip-missing
```

ใช้ `--only` เพื่อรันบางชุด:

```powershell
python tests/evaluation/run_evaluation_suite.py --only clothing color --skip-missing
```

## Chapter 4 Mapping

- Clothing model: `4.1 การทดสอบโมเดลตรวจจับเสื้อผ้า`
- Color analysis: `4.2 การทดสอบระบบวิเคราะห์สี`
- Tracking/Re-ID: `4.3-4.4 การติดตามและการกู้คืน Track ID`
- FPS/latency: อยู่ใน tracking report และ clothing/color latency
- Search: `4.5 การทดสอบการค้นหาข้อมูลย้อนหลัง`
- DB/storage: `4.6 การตรวจสอบความถูกต้องของข้อมูลที่บันทึก`
