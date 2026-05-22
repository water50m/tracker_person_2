# แผน Implement Re-ID แบบไม่ใช้ Embedding ในระบบจริง

## เป้าหมาย

ใช้ Re-ID decision แบบใหม่ในระบบจริง:

```text
ไม่ใช้ embedding ในการ recover ID
ใช้ class gate + สีเสื้อ + สีกางเกง
ยืนยัน 10/30
single-slot fallback 18/30
```

embedding จะไม่ใช้ตัดสิน recover แล้ว อาจปิด extraction ไปเลยเพื่อความเร็ว หรือเก็บไว้ debug เท่านั้น

## กติกาหลัก

```text
top_slot_score    = shirt_color_score
bottom_slot_score = pants_color_score

recover ได้เมื่อ:
top_hits >= 10
bottom_hits >= 10
ภายใน 30 observations
```

## Single-Slot Fallback

ใช้หลังจากกติกาปกติไม่ผ่าน:

```text
lost top_only + new top_only
หรือ lost bottom_only + new bottom_only
```

เงื่อนไข:

```text
single_slot_min_hits = 18 / 30
single_slot_threshold = 0.75
single_slot_min_coverage = 0.60
missing_slot_max_coverage = 0.15
dominance_ratio = 4.0
ambiguity_margin = 0.08
```

นิยาม slot ที่ “เจอใช้งานได้”:

- class อยู่ใน expected classes
- confidence >= `0.25`
- bbox area >= `3%` ของ person crop
- มี detailed colors ไม่ว่าง

## Config ที่ควรเพิ่ม

```text
REID_USE_EMBEDDING=false
REID_RECOVERY_THRESHOLD=0.6
REID_CONFIRMATION_FRAMES=30
REID_CONFIRMATION_MIN_HITS=10
REID_SINGLE_SLOT_FALLBACK=true
REID_SINGLE_SLOT_MIN_HITS=18
REID_SINGLE_SLOT_THRESHOLD=0.75
REID_EXPECTED_CLASSES=long_sleeve,trousers
REID_AGGREGATE_SLOT_HISTORY=10
```

## กฎ Predict Cloth ที่ใช้ทดสอบล่าสุด

กฎนี้คือ post-process หลังจากโมเดลเสื้อผ้า predict ออกมาแล้ว ใช้กับชุดทดสอบ `conf=0.10` และ dataset คนที่ crop มาแล้ว:

```text
raw prediction:
- เก็บทุก detection ที่ confidence >= 0.10
- เก็บ class, confidence, bbox, raw_class ไว้ทุกภาพ

slot หลัก:
- top = เลือกผู้ชนะจาก short_sleeve, long_sleeve
- bottom = เลือกผู้ชนะจาก shorts, trousers, skirt
- dress = พิจารณาแยกต่างหาก
```

กฎเดรสและกระโปรง:

```text
ถ้าเจอ skirt และ dress พร้อมกัน:
    ใช้ skirt_conf * 3 เฉพาะตอนตัดสินกฎ
    แล้วค่อยหา winner ระหว่าง skirt/dress

ถ้า dress ชนะ:
    dress อยู่ร่วมกับ trousers ได้
    dress อยู่ร่วมกับ short_sleeve หรือ long_sleeve ได้เฉพาะเมื่อ top_conf >= 0.76
    ถ้า top_conf < 0.76 ให้ตัด top ออก ถือว่าเจอ dress อย่างเดียว
    ถ้า bottom เป็น shorts หรือ skirt ให้ตัด bottom ออก
```

เหตุผลการตัดถูกเก็บไว้ใน `removed_reason` เช่น:

- `removed_by_skirt_x3_rule`
- `removed_by_dress_top_conf_0p76_rule`
- `removed_by_dress_rule`
- `removed_by_dress_skirt_rule`
- `not_best_in_slot`

ผลลัพธ์รายภาพถูกเก็บใน:

```text
track_result/clothing_model_eval_tune_conf_0p10_postprocess_viewer/image_label_comparison.csv
track_result/clothing_model_eval_tune_conf_0p10_postprocess_viewer/detection_viewer.html
```

ใน HTML viewer สามารถค้นหาได้ เช่น:

```text
missing:short_sleeve
extra:dress
true:skirt
pred:trousers
reason:top_conf
```

## ขั้นตอน Implement

### 1. เพิ่ม config สำหรับ Re-ID rule

เพิ่มค่าควบคุม rule ใหม่ใน config loader หรือ `.env` แล้วให้ระบบอ่านจากจุดเดียว

ค่าที่ต้องมี:

- `REID_USE_EMBEDDING`
- `REID_RECOVERY_THRESHOLD`
- `REID_CONFIRMATION_FRAMES`
- `REID_CONFIRMATION_MIN_HITS`
- `REID_SINGLE_SLOT_FALLBACK`
- `REID_SINGLE_SLOT_MIN_HITS`
- `REID_SINGLE_SLOT_THRESHOLD`
- `REID_EXPECTED_CLASSES`
- `REID_AGGREGATE_SLOT_HISTORY`

### 2. แก้ `FrameProcessor` ให้ไม่ extract embedding เป็น default

ไฟล์หลัก:

```text
src/services/frame_processor.py
```

ตอนนี้ `_process_person()` ยังเรียก `ClothingEmbedder.get_embedding()` ถ้า `enable_embedding=True`

ให้เปลี่ยน default production เป็น:

```python
enable_embedding=False
```

เพื่อไม่เสียเวลา generate embedding

### 3. สร้าง Clothing Profile จริงต่อคน

ย้าย helper จาก evaluator ไปเป็น production module เช่น:

```text
src/services/reid_profile.py
```

profile ที่ต้องการ:

```python
clothing_profile = {
    "top": {
        "class_name": "long_sleeve",
        "confidence": 0.82,
        "bbox_area_ratio": 0.31,
        "detailed_colors": {...}
    },
    "bottom": {
        "class_name": "trousers",
        "confidence": 0.76,
        "bbox_area_ratio": 0.28,
        "detailed_colors": {...}
    },
    "classes": {
        "top": "long_sleeve",
        "bottom": "trousers"
    }
}
```

### 4. แก้ `HybridTracker` ให้เลิกใช้ `_calculate_similarity()` เดิม

ไฟล์หลัก:

```text
src/services/hybrid_tracker.py
```

ของเดิมใช้:

```text
embedding cosine
+ color_groups IoU
```

ให้เปลี่ยนเป็น:

```text
clothing class gate
-> compare top color
-> compare bottom color
-> count hits per lost candidate
-> recover เมื่อ top_hits >= 10 และ bottom_hits >= 10
```

### 5. เพิ่ม pending confirmation state ใน production

ตอนนี้ production recover ทันทีเมื่อเจอ ByteTrack ID ใหม่

ต้องเปลี่ยนเป็น:

```text
ByteTrack ID ใหม่
-> assign provisional our_id ก่อน
-> เก็บ pending_reid[byte_id]
-> เทียบต่อเนื่องสูงสุด 30 observations
-> ถ้าผ่านค่อย remap เป็น lost our_id
-> ถ้าไม่ผ่านใน 30 observations ถือเป็น new ID จริง
```

เมื่อ recover สำเร็จและ `provisional_our_id` ถูก remap กลับไปเป็น `lost_our_id`:

```text
ให้ retire/discard provisional_our_id ทันที
ไม่เอา provisional_our_id ไปเป็น lost candidate อีก
ไม่เก็บเป็นตัวแทนคนใหม่
ไม่ใช้ profile/history ของ provisional_our_id ในการ reid รอบถัดไป
```

เหตุผลคือ provisional ID เป็นแค่ ID ชั่วคราวระหว่างรอยืนยัน ถ้าถูก recover ทับแล้วแปลว่ามันคือคนเดิม ไม่ใช่ identity ใหม่

ข้อมูล pending ที่ควรเก็บ:

```python
pending_reid[byte_id] = {
    "provisional_our_id": our_id,
    "start_frame": frame_number,
    "observations": 0,
    "slot_hit_counts": {},
    "single_slot_hit_counts": {},
    "single_slot_score_sums": {},
    "new_slot_seen_counts": {"top": 0, "bottom": 0},
    "initial_lost_ids": [...]
}
```

### 6. เพิ่ม aggregate history แยก top/bottom

เก็บ history ต่อ `our_id`:

```text
track_profile_history[our_id] = last 60 observations
```

เวลา lost แล้วเอาไปเทียบ ให้ใช้:

```text
top: class ที่เจอบ่อยสุด + สีเฉลี่ย 10 frame ล่าสุดของ class นั้น
bottom: class ที่เจอบ่อยสุด + สีเฉลี่ย 10 frame ล่าสุดของ class นั้น
```

### 7. เพิ่ม single-slot fallback

ใช้หลังจากกติกาปกติไม่ผ่าน

recover แบบ slot เดียวได้เมื่อ:

```text
lost เป็น top_only และ new เป็น top_only
หรือ lost เป็น bottom_only และ new เป็น bottom_only

slot_hits >= 18/30
average_slot_score >= 0.75
best_score - second_best_score >= 0.08
```

ถ้า best กับ second-best ใกล้กันเกินไป ให้ถือว่า ambiguous และไม่ recover

### 8. แก้ `VideoProcessor` ให้ส่ง profile เข้า tracker

ไฟล์หลัก:

```text
src/services/video_processor.py
```

ของเดิมมีการส่ง:

```python
match_or_create_track(..., precomputed_embedding=person.embedding)
store_track_features(..., embedding=embedding)
```

ให้เปลี่ยนเป็นแนวทาง:

```python
match_or_create_track(..., clothing_profile=person.clothing_profile)
store_track_features(..., clothing_profile=person.clothing_profile, embedding=None)
```

### 9. คง embedding ไว้แค่ optional/debug

ไม่ต้องลบ `ClothingEmbedder` ทิ้งทันที แต่ default production ต้องเป็น:

```text
REID_USE_EMBEDDING=false
```

เพื่อให้ย้อนกลับไป test ได้ถ้าต้องการ

### 10. เพิ่ม log/metrics

ต้อง log ต่อ recovery event:

```text
byte_id
recovered_our_id
recovery_mode = both_slots / single_slot_top / single_slot_bottom
top_hits
bottom_hits
final_score
top_score
bottom_score
rejected_reason
fps
```

## ลำดับทำงานที่แนะนำ

1. ย้าย helper จาก `tests/evaluation/evaluate_tracking_reid.py` ไปเป็น production module
2. ปรับ `HybridTracker` ให้ใช้ pending confirmation + no-embedding score
3. ปรับ `FrameProcessor` / `VideoProcessor` ให้ส่ง clothing profile เข้า tracker
4. ปิด embedding default
5. รันเทียบ video เดิมช่วง `500-999` และ `1000-1499`
6. ตรวจ crop recover ก่อนถือว่าเสร็จ

## เกณฑ์ยอมรับ

- ระบบจริงไม่ใช้ embedding ใน Re-ID decision
- recover ใช้ทั้ง `top` และ `bottom` แบบ `10/30`
- single-slot fallback ใช้ `18/30`
- มี log บอกว่า recover ด้วย mode ไหน
- ผลช่วง `1000-1499` ไม่เกิด false recover แบบ embedding เดิม
- FPS ดีขึ้นเมื่อเทียบกับ mode ที่ใช้ embedding
