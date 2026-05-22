# สรุปผลการทดสอบ Re-ID ล่าสุด

## ขอบเขตการทดสอบ

- วิดีโอ: `temp_videos/CAM-01_4p-c0-new.mp4`
- ช่วง frame: `500-999`
- จำนวน frame: `500`
- frame skip: `1`
- device: `cuda`
- output ล่าสุด: `track_result/reid_test_500_999_slot_hits_thr06_confirm30_hit10/tracking-reid-eval.json`
- crop recover ล่าสุด: `track_result/reid_test_500_999_slot_hits_thr06_confirm30_hit10/recovered_crops`
- crop class gate ไม่ผ่าน: `track_result/reid_test_500_999_slot_hits_thr06_confirm30_hit10/class_failed_crops`
- crop class ทายผิดจาก expected classes: `track_result/reid_test_500_999_slot_hits_thr06_confirm30_hit10/wrong_class_crops`
- ไม่บันทึกผลลง database

## Logic ล่าสุดที่ใช้ Recover

รอบล่าสุดเปลี่ยนจาก `4/10` เป็น `10/30`:

- class ที่คาดว่าจะเจอใน clip นี้คือ `long_sleeve` และ `trousers`
- class อื่น เช่น `short_sleeve`, `shorts`, `skirt` จะถูกแยกเป็น wrong-class crop และไม่เอาเข้า profile
- lost profile เก็บสถิติแยก `top` และ `bottom`
- แต่ละ slot ใช้ class ที่เจอบ่อยสุดของ slot นั้น แล้วเฉลี่ยสีจาก `10` observation ล่าสุดของ class ที่ถูกเลือก
- ใช้เฉพาะค่าเฉลี่ย (`average`) ไม่ใช้ `min/max range` เป็นตัวตัดสิน recover
- threshold score = `0.600`
- ยืนยันต่อเนื่องสูงสุด `30` observations
- ต้อง hit อย่างน้อย `10` ครั้งทั้ง `top` และ `bottom` ใน lost ID เดียวกัน จึง recover

ถ้าเจอแค่เสื้อหรือแค่กางเกง แม้ score จะสูงมาก จะยังไม่ recover ทันที แต่จะสะสม hit ของ slot นั้นไว้ก่อน รอจนอีก slot hit ครบด้วย

คะแนนราย slot:

```text
top_slot_score    = average(embedding_score, shirt_color_score)
bottom_slot_score = average(embedding_score, pants_color_score)
recover ได้เมื่อ top_hits >= 10 และ bottom_hits >= 10
```

`final_score` ที่ log ไว้ยังคำนวณจากคะแนนรวม:

```text
final_score = average(embedding_score, shirt_color_score, pants_color_score)
```

แต่ decision รอบล่าสุดไม่ได้ดูแค่ final_score เดี่ยว ๆ แล้ว ต้องผ่านจำนวน hit แยกบน/ล่างด้วย

## ผลภาพรวม

| Mode | Processed Frames | Detections | Unique IDs | Output FPS | Recovered Tracks | New Tracks | Re-ID Attempts |
|---|---:|---:|---:|---:|---:|---:|---:|
| `bytetrack_only` | `500` | `1303` | `13` | `12.483` | `-` | `-` | `-` |
| `reid` slot-hit บน+ล่าง threshold 0.6 confirm 10 hit 4 | `500` | `1303` | `11` | `1.116` | `2` | `13` | `10` |
| `reid` slot-hit บน+ล่าง threshold 0.6 confirm 30 hit 10 ล่าสุด | `500` | `1303` | `11` | `1.006` | `2` | `13` | `10` |

สรุปล่าสุด:

- ByteTrack-only แตกเป็น `13` IDs
- Re-ID `10/30` ล่าสุดเหลือ `11` IDs
- recover ได้ `2 / 10` attempts
- recovery rate = `20%`
- `best_recover_score` = `0.869`
- `average_attempt_best_score` = `0.575`
- confirmation observations ทั้งหมด `124`
- class-failed crop events `35`
- wrong-class crop events `148`

เทียบกับ `4/10`:

- จำนวน recover เท่าเดิม: `2`
- unique IDs เท่าเดิม: `11`
- ใช้เวลานานขึ้น เพราะ pending candidate ถูกเทียบนานขึ้น
- `reid_candidate_scoring` เพิ่มจาก `69` เป็น `134` ครั้ง
- `output_fps` ลดจาก `1.116` เหลือ `1.006`

## Final Score และ Slot Hits แต่ละ Attempt ล่าสุด

| ByteTrack ID ใหม่ | Frame ที่เทียบ | Max Score | Best Lost | Top Hits | Bottom Hits | Both Min | Result |
|---:|---|---:|---:|---:|---:|---:|---|
| `8` | `715-744` | `0.729` | `1` | `4` | `24` | `4` | ไม่ recover |
| `10` | `751-768` | `0.717` | `2` | `11` | `2` | `2` | ไม่ recover |
| `18` | `791` | `0.544` | `1` | `1` | `0` | `0` | ไม่ recover |
| `20` | `820-822` | `0.709` | `5` | `0` | `1` | `0` | ไม่ recover |
| `22` | `827-845` | `0.849` | `1` | `10` | `10` | `10` | recover เป็น our `1` |
| `24` | `837-868` | `0.855` | `1` | `10` | `11` | `10` | recover เป็น our `1` |
| `30` | `842-867` | `0.861` | `2` | `4` | `0` | `0` | ไม่ recover |
| `45` | `874` | `0.829` | `3` | `0` | `1` | `0` | ไม่ recover |
| `49` | `887-930` | `0.869` | `2` | `17` | `3` | `3` | ไม่ recover |
| `55` | `894-913` | `0.841` | `2` | `17` | `0` | `0` | ไม่ recover |

## Crop Recover ล่าสุด

สร้าง crop เฉพาะเคสที่ recover สำเร็จ `2` events:

| Recover Frame | Lost Frame | Our ID | ByteTrack ID ใหม่ | Score | Pair Crop |
|---:|---:|---:|---:|---:|---|
| `845` | `618` | `1` | `22` | `0.770` | `track_result/reid_test_500_999_slot_hits_thr06_confirm30_hit10/recovered_crops/frame_00845_our_1_byte_22/pair_lost_00618_recovered_00845_our_1.jpg` |
| `868` | `867` | `1` | `24` | `0.850` | `track_result/reid_test_500_999_slot_hits_thr06_confirm30_hit10/recovered_crops/frame_00868_our_1_byte_24/pair_lost_00867_recovered_00868_our_1.jpg` |

## จุดที่ควรสังเกตจาก 10/30

- ByteTrack ID `8` ยังไม่ recover แม้ `bottom_hits = 24` เพราะ `top_hits = 4` ไม่ถึง 10
- ByteTrack ID `55` ยังไม่ recover เพราะ `top_hits = 17` แต่ `bottom_hits = 0`
- ByteTrack ID `49` max score สูง `0.869` แต่ไม่ recover เพราะ `bottom_hits = 3`
- ByteTrack ID `24` รอบ `10/30` recover เป็น our `1` ไม่ใช่ our `3` แบบรอบ `4/10`
- สาเหตุที่เป็นไปได้คือการรอนานขึ้นทำให้ profile/history และ mapping หลัง byte `22` recover แล้วมีผลกับ candidate ของ byte `24`

## Timing ล่าสุด

| ส่วนงาน | Total ms | Count | Avg ms |
|---|---:|---:|---:|
| `embedding_extraction` | `323302.4` | `1303` | `248.12` |
| `clothing_profile_class_color` | `141609.2` | `1303` | `108.68` |
| `person_detector_track` | `25612.9` | `500` | `51.23` |
| `reid_candidate_scoring` | `4158.5` | `134` | `31.03` |
| `wrong_class_crop_saving` | `1194.4` | `127` | `9.40` |
| `class_failed_crop_saving` | `391.5` | `134` | `2.92` |
| `recovered_crop_saving` | `14.1` | `2` | `7.03` |
| `update_lost_tracks` | `26.1` | `500` | `0.05` |

## วิเคราะห์

- `10/30` ไม่ได้เพิ่มจำนวน recover ใน clip นี้ แต่ช่วยให้ระบบรอหลักฐานนานขึ้นก่อนตัดสิน
- เคสที่เห็นแค่บนหรือแค่ล่างยังถูกกันไว้เหมือนเดิม
- ต้นทุนเวลาสูงขึ้นชัดเจน เพราะต้อง score candidate ต่อเนื่องหลาย frame กว่าเดิม
- จุดเสี่ยงใหม่คือการรอนานเกินไปอาจทำให้ candidate profile เปลี่ยนหลังมี recover อื่นเกิดขึ้นก่อน เช่น byte `24` ที่ไป recover เป็น our `1`
