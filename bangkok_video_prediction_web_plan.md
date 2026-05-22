# แผนเว็บดูผล Predict Video 2 นาทีแรก

## เป้าหมาย

สร้างเว็บสำหรับเปิดคลิป 2 นาทีแรกของวิดีโอ Bangkok Earthquake พร้อมอ่านผล predict/tracking จากไฟล์ local แล้ววาด overlay บน video ระหว่างเล่น

ข้อมูลที่ต้องแสดง:

- bbox คน พร้อม `id`
- bbox เสื้อผ้า พร้อมชื่อ class และ confidence
- จุดสีที่กึ่งกลางด้านล่างของ bbox
- filter class เสื้อผ้า
- เปิด/ปิด label
- เลือกดู bbox คน, bbox เสื้อผ้า, หรือทั้งสองพร้อมกัน
- ปุ่ม stop และ play/pause

## เลือกเทคโนโลยี

ใช้ `HTML + CSS + JavaScript` ไฟล์เดียวพอสำหรับตัว viewer เพราะงานนี้ไม่ต้องมี backend:

- video เปิดจากไฟล์ `.mp4` local
- prediction โหลดจาก `prediction_data.js`
- overlay ใช้ `<canvas>` วาดทับ `<video>`
- controls ทั้งหมดทำใน browser ได้

ยังไม่จำเป็นต้องใช้ Next.js/TSX เพราะไม่มี routing, API, auth, database, หรือ server-side rendering

## ไฟล์ Output

```text
track_result/bangkok_earthquake_predict_2min/
  bangkok_earthquake_first_2min.mp4
  bangkok_earthquake_frames_1000_1999.mp4
  prediction_results.json
  prediction_results_compact.json
  prediction_data.js
  prediction_summary.txt
  video_prediction_viewer.html
```

## Flow Predict

อ้างอิง flow จาก `reid_no_embedding_implementation_plan.md`:

```text
video frame
  |
  |-- YOLO person detector + ByteTrack
  |      ได้ person bbox + person id
  |
  |-- crop person
  |
  |-- clothing model predict บน crop คน
  |
  |-- post-process clothing class
  |      short_sleeve, long_sleeve, shorts, trousers, skirt, dress
  |
  |-- แปลง bbox เสื้อผ้าจากพิกัด crop กลับเป็นพิกัด frame เต็ม
  |
  |-- เก็บผลต่อ frame ลง JSON
```

รอบนี้เป็นงาน predict/viewer เท่านั้น ยังไม่บันทึกลง database และยังไม่ทำ Re-ID recovery

## Web Viewer Flow

```text
เปิด video_prediction_viewer.html
  |
  |-- โหลด prediction_data.js
  |
  |-- เปิด clip 2 นาทีแรกเป็น default
  |
  |-- ระหว่าง video เล่น
  |      อ่าน currentTime
  |      แปลงเป็น frame number
  |      หา prediction ของ frame นั้น
  |      วาด bbox บน canvas
  |
  |-- ผู้ใช้เปลี่ยน control
         filter class
         show/hide label
         show/hide dot
         person/clothing/both
```

## Clip ที่ต้องตัด

1. `bangkok_earthquake_first_2min.mp4`
   - เวลา `0:00-2:00`
   - ใช้เป็น video หลักของ viewer

2. `bangkok_earthquake_frames_1000_1999.mp4`
   - frame `1000-1999`
   - ใช้ตรวจช่วงเดียวกับงาน tracking test ก่อนหน้า

## Control ในเว็บ

- `Box mode`
  - default: `คน`
  - ตัวเลือก: `คน`, `เสื้อผ้า`, `ทั้งคู่`

- `Filter class`
  - `short_sleeve`
  - `long_sleeve`
  - `shorts`
  - `trousers`
  - `skirt`
  - `dress`

- toggle:
  - แสดง/ซ่อนชื่อ class + id
  - แสดง/ซ่อนจุดสีด้านล่าง bbox
  - แสดง final clothing boxes หรือ raw clothing boxes

## เกณฑ์ตรวจสอบ

- เปิด HTML แล้ว video เล่นได้
- canvas overlay ตรงกับขนาด video
- default เห็น bbox คน
- เปิด mode เสื้อผ้าแล้วเห็น bbox clothing
- filter class แล้ว box class อื่นหาย
- label แสดง `ID` และชื่อ class
- stop หยุดและกลับไปต้นคลิป
- มีไฟล์ JSON/text ให้ตรวจผลย้อนหลังได้
