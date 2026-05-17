# ภาพที่ 3.10 แผนภาพลำดับการประมวลผลวิดีโอและ Queue

```mermaid
flowchart TD
    A["ผู้ใช้เพิ่มวิดีโอ / RTSP / YouTube"] --> B["Next.js Input Manager"]
    B --> C["FastAPI Video API<br/>/api/video-queue หรือ /api/video"]
    C --> D["สร้างงานประมวลผล<br/>processed_videos / queue job"]
    D --> E{"โหมดการทำงาน"}

    E -->|วิดีโอไฟล์| F["VideoProcessor"]
    E -->|สตรีมสด| G["StreamProcessor"]

    F --> H["เปิดแหล่งวิดีโอด้วย OpenCV / loader"]
    G --> H
    H --> I["อ่านเฟรมและคำนวณ frame_skip"]
    I --> J{"ถึงเฟรมที่ต้องประมวลผล?"}
    J -->|ไม่ใช่| K["ข้ามเฟรม / ใช้ผล bbox ล่าสุดใน realtime"]
    K --> I
    J -->|ใช่| L["ส่งเฟรมเข้า ThreadPoolProcessor"]
    L --> M["FrameProcessor<br/>Person -> Clothing -> Color -> Embedding"]
    M --> N["อัปโหลดภาพ crop ไป MinIO<br/>(ถ้าเปิด save_images)"]
    M --> O["เตรียม detection payload"]
    N --> O
    O --> P["สะสม batch"]
    P --> Q{"ครบ batch หรือจบงาน?"}
    Q -->|ยังไม่ครบ| I
    Q -->|ครบ| R["insert_detections_batch ลง PostgreSQL"]
    R --> S["อัปเดต progress / status"]
    S --> T{"จบวิดีโอหรือหยุดงาน?"}
    T -->|ยังไม่จบ| I
    T -->|จบ| U["completed / success / paused / error"]
```

## คำอธิบายสำหรับใส่ในรายงาน

แผนภาพนี้อธิบาย flow การประมวลผลวิดีโอของระบบจริง โดยระบบไม่ได้ประมวลผลทุกเฟรมเสมอไป แต่ใช้ `frame_skip` เพื่อลดภาระ GPU และ CPU เฟรมที่ถูกเลือกจะถูกส่งเข้า `ThreadPoolProcessor` เพื่อให้ `FrameProcessor` ทำงาน AI หลัก จากนั้นระบบจะอัปโหลดภาพไปยัง MinIO และสะสมข้อมูลเป็น batch ก่อนบันทึกลง PostgreSQL วิธีนี้ช่วยลดภาระการเขียนฐานข้อมูลและเหมาะกับข้อจำกัดของเครื่องที่มี GPU VRAM 4GB

