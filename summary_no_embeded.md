# สรุปผลการทดสอบ Re-ID ล่าสุด

## ขอบเขตการทดสอบ

- วิดีโอ: `temp_videos/CAM-01_4p-c0-new.mp4`
- ช่วง frame: `500-999`
- จำนวน frame: `500`
- frame skip: `1`
- device: `cuda`
- output ล่าสุด: `track_result/reid_test_500_999_no_embedding_single_slot_fallback/tracking-reid-eval.json`
- crop recover ล่าสุด: `track_result/reid_test_500_999_no_embedding_single_slot_fallback/recovered_crops`
- crop class gate ไม่ผ่าน: `track_result/reid_test_500_999_no_embedding_single_slot_fallback/class_failed_crops`
- crop class ทายผิดจาก expected classes: `track_result/reid_test_500_999_no_embedding_single_slot_fallback/wrong_class_crops`
- ไม่บันทึกผลลง database

## Logic ล่าสุดที่ใช้ Recover

รอบล่าสุดเป็น `10/30` แบบไม่ใช้ embedding และเปิด single-slot fallback:

- ปิด `embedding_score` ด้วย flag `--disable-reid-embedding`
- ไม่เรียก `ClothingEmbedder.get_embedding()`
- ใช้ class เสื้อผ้า + สีของ slot เท่านั้น
- class ที่คาดว่าจะเจอใน clip นี้คือ `long_sleeve` และ `trousers`
- class อื่นจะถูกแยกเป็น wrong-class crop และไม่เอาเข้า profile
- lost profile เก็บสถิติแยก `top` และ `bottom`
- แต่ละ slot ใช้ class ที่เจอบ่อยสุด แล้วเฉลี่ยสีจาก `10` observation ล่าสุดของ class นั้น
- threshold ปกติ = `0.600`
- ยืนยันต่อเนื่องสูงสุด `30` observations
- recover ปกติเมื่อ `top_hits >= 10` และ `bottom_hits >= 10`

## Single-Slot Fallback

เพิ่มกติกา fallback สำหรับกรณี lost และ new เห็นแค่ส่วนเดียวเหมือนกัน:

```text
single_slot_min_hits = 18 / 30
single_slot_threshold = 0.75
single_slot_min_coverage = 0.60
missing_slot_max_coverage = 0.15
dominance_ratio = 4.0
ambiguity_margin = 0.08
```

นิยาม `top_only`:

```text
top_coverage >= 0.60
bottom_coverage <= 0.15 หรือ bottom_seen <= 3
top_seen / max(bottom_seen, 1) >= 4
```

นิยาม `bottom_only`:

```text
bottom_coverage >= 0.60
top_coverage <= 0.15 หรือ top_seen <= 3
bottom_seen / max(top_seen, 1) >= 4
```

recover แบบ slot เดียวจะเกิดเฉพาะเมื่อ:

```text
lost เป็น top_only และ new เป็น top_only
หรือ lost เป็น bottom_only และ new เป็น bottom_only

slot_hits >= 18
average_slot_score >= 0.75
best_score - second_best_score >= 0.08
```

slot ที่นับว่า “เจอใช้งานได้” ต้องมี:

- class อยู่ใน expected classes
- confidence >= `0.25`
- bbox area >= `3%` ของ person crop
- มี detailed colors ไม่ว่าง

## ผลภาพรวม

| Mode | Processed Frames | Detections | Unique IDs | Output FPS | Recovered Tracks | Single-Slot Recover | New Tracks | Re-ID Attempts |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| `bytetrack_only` | `500` | `1303` | `13` | `12.483` | `-` | `-` | `-` | `-` |
| `reid` no embedding `10/30` ก่อน fallback | `500` | `1303` | `11` | `2.906` | `2` | `0` | `13` | `10` |
| `reid` no embedding `10/30` + single-slot fallback ล่าสุด | `500` | `1303` | `12` | `2.309` | `2` | `0` | `13` | `10` |

สรุปล่าสุด:

- recover ได้ `2 / 10` attempts
- single-slot fallback recover ได้ `0`
- recovered ทั้ง 2 เคสยังเป็น mode `both_slots`
- unique IDs = `12`
- recovery rate = `20%`
- `best_recover_score` = `0.920`
- `average_attempt_best_score` = `0.533`
- confirmation observations ทั้งหมด `131`
- class-failed crop events `43`
- wrong-class crop events `148`

## Final Score และ Slot Hits แต่ละ Attempt ล่าสุด

| ByteTrack ID ใหม่ | Frame ที่เทียบ | Max Score | Best Lost | Top Hits | Bottom Hits | Both Min | Result |
|---:|---|---:|---:|---:|---:|---:|---|
| `8` | `715-744` | `0.747` | `1` | `0` | `17` | `0` | ไม่ recover |
| `10` | `751-768` | `0.627` | `2` | `9` | `1` | `1` | ไม่ recover |
| `18` | `791` | `0.401` | `1` | `1` | `0` | `0` | ไม่ recover |
| `20` | `820-822` | `0.604` | `5` | `0` | `1` | `0` | ไม่ recover |
| `22` | `827-853` | `0.852` | `1` | `12` | `10` | `10` | recover เป็น our `1` |
| `24` | `837-868` | `0.811` | `8` | `10` | `12` | `10` | recover เป็น our `8` |
| `30` | `842-867` | `0.873` | `2` | `4` | `0` | `0` | ไม่ recover |
| `45` | `874` | `0.764` | `9` | `0` | `1` | `0` | ไม่ recover |
| `49` | `887-930` | `0.920` | `2` | `16` | `3` | `3` | ไม่ recover |
| `55` | `894-913` | `0.893` | `2` | `13` | `0` | `0` | ไม่ recover |

## Crop Recover ล่าสุด

สร้าง crop เฉพาะเคสที่ recover สำเร็จ `2` events:

| Recover Frame | Lost Frame | Our ID | ByteTrack ID ใหม่ | Mode | Score | Pair Crop |
|---:|---:|---:|---:|---|---:|---|
| `853` | `618` | `1` | `22` | `both_slots` | `0.686` | `track_result/reid_test_500_999_no_embedding_single_slot_fallback/recovered_crops/frame_00853_our_1_byte_22/pair_lost_00618_recovered_00853_our_1.jpg` |
| `868` | `851` | `8` | `24` | `both_slots` | `0.725` | `track_result/reid_test_500_999_no_embedding_single_slot_fallback/recovered_crops/frame_00868_our_8_byte_24/pair_lost_00851_recovered_00868_our_8.jpg` |

## วิเคราะห์ผล Single-Slot

- byte `8` มี `bottom_hits = 17` แต่ยังไม่ถึง single-slot min hits `18` และ lost ไม่เข้าเงื่อนไข bottom-only แบบชัดพอ จึงไม่ recover
- byte `49` มี `top_hits = 16`, `bottom_hits = 3`; ยังไม่ถึง single-slot min hits `18`
- byte `55` มี `top_hits = 13`, `bottom_hits = 0`; ยังไม่ถึง single-slot min hits `18`
- ดังนั้น fallback ที่ออกแบบไว้ยัง conservative อยู่ และไม่เปิด recover เพิ่มใน clip นี้
- รอบนี้ byte `24` recover เป็น our `8` ไม่ใช่ our `1` แบบรอบก่อน ซึ่งดีกว่าในเชิงแยก track แต่ทำให้ unique IDs รวมออกมา `12`

## Timing ล่าสุด

| ส่วนงาน | Total ms | Count | Avg ms |
|---|---:|---:|---:|
| `clothing_profile_class_color` | `174444.2` | `1303` | `133.88` |
| `person_detector_track` | `37786.9` | `500` | `75.57` |
| `wrong_class_crop_saving` | `2415.1` | `127` | `19.02` |
| `reid_candidate_scoring` | `492.3` | `141` | `3.49` |
| `class_failed_crop_saving` | `491.0` | `141` | `3.48` |
| `recovered_crop_saving` | `17.4` | `2` | `8.69` |
| `update_lost_tracks` | `29.3` | `500` | `0.06` |

## สรุป

- กติกา single-slot fallback ถูกเพิ่มและรันแล้ว แต่ไม่ recover เพิ่มใน clip นี้
- เหตุผลหลักคือเคส slot เดียวที่น่าสนใจยังไม่ถึง `18/30`
- ถ้าต้องการให้ fallback ทำงานใน clip นี้ อาจลองลดเป็น `16/30` หรือ `13/30`
- แต่ค่า `18/30` ปลอดภัยกว่า เพราะลดโอกาส recover ผิดจากเสื้อ/กางเกงสีคล้ายกัน

## Crop สำหรับเทียบ Threshold Single-Slot

สร้าง crop สำหรับ near-miss candidates ไว้ที่:

```text
track_result/reid_test_500_999_no_embedding_single_slot_fallback/single_slot_candidate_crops
```

สรุป threshold:

| Threshold | Byte ที่ผ่านตามจำนวน hit | หมายเหตุ |
|---|---|---|
| `18/30` | ไม่มี | ปลอดภัยสุดในชุดนี้ |
| `16/30` | `8`, `49` | เปิดโอกาสให้ recover เพิ่ม 2 เคส |
| `13/30` | `8`, `49`, `55` | หลวมกว่าและเสี่ยงกว่า |

pair crop หลัก:

| Byte | Slot | Hits | Pair Crop |
|---:|---|---:|---|
| `8` | `bottom` | `17/30` | `track_result/reid_test_500_999_no_embedding_single_slot_fallback/single_slot_candidate_crops/threshold_16_30_medium/byte_8_lost_1_bottom_17_of_30/pair_lost_00618_new_00744_byte_8.jpg` |
| `49` | `top` | `16/30` | `track_result/reid_test_500_999_no_embedding_single_slot_fallback/single_slot_candidate_crops/threshold_16_30_medium/byte_49_lost_2_top_16_of_30/pair_lost_00886_new_00930_byte_49.jpg` |
| `55` | `top` | `13/30` | `track_result/reid_test_500_999_no_embedding_single_slot_fallback/single_slot_candidate_crops/threshold_13_30_loose/byte_55_lost_2_top_13_of_30/pair_lost_00893_new_00913_byte_55.jpg` |
