# Summary: No-Embedding Re-ID Threshold 0.7

## Test Scope

- Video: `temp_videos/CAM-01_4p-c0-new.mp4`
- Frame range: `1000-1999`
- Frames processed: `1000`
- Mode: `reid`
- Embedding: disabled with `--disable-reid-embedding`
- Recovery threshold: `0.7`
- Confirmation: `10 / 30`
- Single-slot fallback: enabled, `18 / 30`
- Expected clothing classes: `long_sleeve,trousers`
- Output: `track_result/reid_no_embedding_thr07_1000_1999/tracking-reid-eval.json`

## Overall Result

| Metric | Value |
|---|---:|
| Unique IDs | `31` |
| Recovered tracks | `8` |
| New tracks | `39` |
| Re-ID attempts | `36` |
| Recovery rate | `22.22%` |
| Output FPS | `1.870` |
| Best recover score | `0.950` |
| Average attempt best score | `0.688` |
| Confirmation observations | `408` |
| Single-slot recovered tracks | `0` |
| Wrong-class crop events | `419` |
| Class-failed crop events | `161` |

## Working Flow

```text
Frame input
|
YOLO person detector + ByteTrack
|
ได้ byte_id + bbox คน
|
Crop คนจาก frame
|
Clothing classifier
|
แยก clothing profile เป็น top / bottom
|
วิเคราะห์ detailed colors ของ top / bottom
|
เช็กว่า byte_id นี้เคย map กับ our_id แล้วหรือยัง
|
+-- ถ้าเคย map แล้ว
|   |
|   อัปเดต profile history ของ our_id เดิม
|   |
|   ใช้ our_id เดิมต่อ
|
+-- ถ้าเป็น byte_id ใหม่
    |
    เช็กว่ามี lost_tracks ให้เทียบไหม
    |
    +-- ถ้าไม่มี lost_tracks
    |   |
    |   สร้าง our_id ใหม่
    |
    +-- ถ้ามี lost_tracks
        |
        นับเป็น 1 Re-ID attempt
        |
        สร้าง provisional our_id ชั่วคราว
        |
        เริ่ม pending confirmation สูงสุด 30 observations
        |
        ในแต่ละ observation:
        |
        aggregate lost profile แยก top / bottom
        |
        class gate: top ต้องชน top, bottom ต้องชน bottom
        |
        คำนวณ color score:
        top_score = shirt_color_score
        bottom_score = pants_color_score
        |
        ถ้า top_score >= 0.7 ให้ top_hits +1
        ถ้า bottom_score >= 0.7 ให้ bottom_hits +1
        |
        ถ้า top_hits >= 10 และ bottom_hits >= 10
        |
        recover เป็น lost our_id เดิม
        |
        ถ้าครบ 30 observations แล้วยังไม่ผ่าน
        |
        ยืนยันเป็น new track
```

Single-slot fallback:

```text
ถ้ากติกา top+bottom ไม่ผ่าน
|
เช็กว่า lost และ new เห็นเฉพาะ slot เดียวเหมือนกันไหม
|
เช่น top_only + top_only หรือ bottom_only + bottom_only
|
ถ้า slot_hits >= 18/30
และ average_slot_score >= 0.75
และ best_score ไม่ใกล้ second_best เกิน 0.08
|
recover ด้วย single_slot_top หรือ single_slot_bottom
```



แบบคร่าวๆ
```
Frame
|
YOLO + ByteTrack หาคนและให้ byte_id
|
แยกเสื้อ/กางเกง + วิเคราะห์สี
|
ถ้า byte_id เดิม
    ใช้ our_id เดิมต่อ
|
ถ้า byte_id ใหม่
    ลองเทียบกับ lost_tracks
|
ถ้าสีเสื้อและกางเกง match ครบ 10 ครั้งใน 30 frame
    recover เป็น our_id เดิม
|
ถ้าไม่ครบ
    ถือว่าเป็นคนใหม่
```

shortest
```
Frame
|
Detect + Track
|
Clothing + Color
|
Compare with lost IDs
|
Confirm 10/30
|
Recover ID หรือ New ID
```
ในรอบล่าสุด:

```text
Re-ID attempts = 36
confirmation observations = 408
recovered = 8
single-slot recovered = 0
```

## Recover Events

All recovered events used `both_slots`. No recovery came from single-slot fallback.

| Byte ID | Recover Frame | Our ID | Mode | Hits | Score | Pair Crop |
|---:|---:|---:|---|---:|---:|---|
| `35` | `1268` | `6` | `both_slots` | `10` | `0.768` | `track_result/reid_no_embedding_thr07_1000_1999/recovered_crops/frame_01268_our_6_byte_35/pair_lost_01235_recovered_01268_our_6.jpg` |
| `42` | `1309` | `6` | `both_slots` | `10` | `0.738` | `track_result/reid_no_embedding_thr07_1000_1999/recovered_crops/frame_01309_our_6_byte_42/pair_lost_01277_recovered_01309_our_6.jpg` |
| `47` | `1328` | `1` | `both_slots` | `10` | `0.751` | `track_result/reid_no_embedding_thr07_1000_1999/recovered_crops/frame_01328_our_1_byte_47/pair_lost_01309_recovered_01328_our_1.jpg` |
| `51` | `1380` | `2` | `both_slots` | `10` | `0.785` | `track_result/reid_no_embedding_thr07_1000_1999/recovered_crops/frame_01380_our_2_byte_51/pair_lost_01348_recovered_01380_our_2.jpg` |
| `58` | `1447` | `2` | `both_slots` | `10` | `0.816` | `track_result/reid_no_embedding_thr07_1000_1999/recovered_crops/frame_01447_our_2_byte_58/pair_lost_01416_recovered_01447_our_2.jpg` |
| `82` | `1649` | `2` | `both_slots` | `10` | `0.819` | `track_result/reid_no_embedding_thr07_1000_1999/recovered_crops/frame_01649_our_2_byte_82/pair_lost_01619_recovered_01649_our_2.jpg` |
| `106` | `1835` | `3` | `both_slots` | `10` | `0.805` | `track_result/reid_no_embedding_thr07_1000_1999/recovered_crops/frame_01835_our_3_byte_106/pair_lost_01132_recovered_01835_our_3.jpg` |
| `143` | `1983` | `5` | `both_slots` | `10` | `0.819` | `track_result/reid_no_embedding_thr07_1000_1999/recovered_crops/frame_01983_our_5_byte_143/pair_lost_01708_recovered_01983_our_5.jpg` |

## Timing

| Section | Total ms | Count | Avg ms |
|---|---:|---:|---:|
| `clothing_profile_class_color` | `455043.2` | `3641` | `124.98` |
| `person_detector_track` | `68680.3` | `1000` | `68.68` |
| `reid_candidate_scoring` | `3495.9` | `444` | `7.87` |
| `class_failed_crop_saving` | `2582.3` | `444` | `5.82` |
| `wrong_class_crop_saving` | `2420.4` | `349` | `6.94` |
| `recovered_crop_saving` | `61.1` | `8` | `7.64` |
| `update_lost_tracks` | `152.1` | `1000` | `0.15` |

## Notes

- Threshold was changed from `0.6` to `0.7`.
- This run is a continuous `1000`-frame test from `1000-1999`, so it is not perfectly comparable to the previous two separate 500-frame runs because tracker state is continuous across frame `1499 -> 1500`.
- Raising threshold to `0.7` makes every recovery require stronger per-slot color evidence.
- The known false case around byte `58` from the previous `1500-1999` no-embedding run does not appear in the same form here; byte `58` now recovers earlier at frame `1447` as `our_id 2`.
