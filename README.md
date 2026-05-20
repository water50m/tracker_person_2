# resault-my-project

เว็บสำหรับดูผลลัพธ์ person tracking + clothing prediction + Re-ID จากวิดีโอ Bangkok earthquake 2 นาทีแรก

## เปิดดูผลลัพธ์

เปิดไฟล์นี้ใน browser หลัง clone repo:

```text
result_web/bangkok_earthquake_2min_63color/index.html
```

ไฟล์เว็บใช้ข้อมูลจาก `prediction_data.js` และวิดีโอในโฟลเดอร์เดียวกัน จึงไม่ต้องรัน backend เพิ่ม

## Run ล่าสุด

- Detector: `YOLO11s`
- Person confidence: `0.45`
- Clothing confidence: `0.25`
- IoU dedupe: `0.50`
- Re-ID: clothing class + detailed colors 63 สี
- Processed frames: `3600`
- Output FPS: `2.1464`
- ByteTrack new IDs: `243`
- System recovered IDs: `9`

รายละเอียดเต็มอยู่ใน:

```text
result_web/bangkok_earthquake_2min_63color/summary.md
```
