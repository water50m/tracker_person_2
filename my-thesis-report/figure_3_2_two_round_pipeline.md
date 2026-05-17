# ภาพที่ 3.2 Pipeline การประมวลผล 2 รอบ (Two-Round Processing Pipeline)

```mermaid
graph TB
    subgraph Round1["รอบที่ 1: Real-time Detection (เร็ว ~30fps)"]
        VideoInput[วิดีโอ Input<br/>RTSP/File/YouTube]
        YOLO[YOLO PersonDetector<br/>GPU inference<br/>~10-20ms/frame]
        ByteTrack[ByteTrack Tracking<br/>Real-time tracking<br/>~5ms/frame]
        Filter[กรองเบื้องต้น<br/>confidence > 0.6<br/>height > 100px<br/>aspect ratio > 1.2]
        Queue[Task Queue<br/>maxsize=20<br/>กันส่งงานซ้ำ]
    end

    subgraph Round2["รอบที่ 2: Detailed Analysis (Background Thread)"]
        Worker[Worker Thread<br/>ThreadPoolProcessor<br/>4 workers]
        Crop[ตัดรูปบุคคล<br/>person_crop]
        Classifier[ClothingClassifier<br/>จัดประเภทเสื้อผ้า<br/>~50-100ms]
        Color[Color Analysis<br/>วิเคราะห์สี 63 สี<br/>22 กลุ่มสี<br/>~30-50ms]
        Embedder[ClothingEmbedder<br/>สกัด feature 768-dim<br/>~30-50ms]
        HybridTrack[HybridTracker<br/>จับคู่ track ID<br/>Re-ID matching]
    end

    subgraph Storage["บันทึกข้อมูล"]
        MinIO[MinIO Storage<br/>อัปโหลดรูปภาพ]
        DB[PostgreSQL<br/>บันทึก detections<br/>batch insert]
    end

    VideoInput --> YOLO
    YOLO --> ByteTrack
    ByteTrack --> Filter
    Filter -->|ทุก 3 วินาที| Queue
    Queue --> Worker
    Worker --> Crop
    Crop --> Classifier
    Classifier --> Color
    Color --> Embedder
    Embedder --> HybridTrack
    HybridTrack --> MinIO
    HybridTrack --> DB

    style Round1 fill:#e1f5ff
    style Round2 fill:#ffe1f5
    style Storage fill:#e1ffe1

    classDef realtime fill:#90EE90,stroke:#333,stroke-width:2px
    classDef background fill:#FFB6C1,stroke:#333,stroke-width:2px
    classDef storage fill:#87CEEB,stroke:#333,stroke-width:2px

    class YOLO,ByteTrack,Filter realtime
    class Worker,Classifier,Color,Embedder,HybridTrack background
    class MinIO,DB storage
```

## คำอธิบาย:

**รอบที่ 1 (Round 1): Real-time Detection**
- ทำงานใน main loop แบบ real-time
- YOLO ตรวจหาบุคคลด้วย GPU (เร็ว ~10-20ms per frame)
- ByteTrack ทำ tracking แบบ real-time (เร็ว ~5ms per frame)
- กรอง detections ด้วย confidence, height, aspect ratio
- ส่งงานเข้า queue ทุก 3 วินาที (กันส่งซ้ำ)

**รอบที่ 2 (Round 2): Detailed Analysis**
- ทำงานใน background thread (ThreadPoolProcessor 4 workers)
- ตัดรูปบุคคล (person_crop)
- จัดประเภทเสื้อผ้า (ClothingClassifier)
- วิเคราะห์สี 63 สี แบ่งเป็น 22 กลุ่ม
- สกัด embedding 768-dim สำหรับ Re-ID
- HybridTracker จับคู่ track ID และกู้คืน lost tracks
- อัปโหลดรูปไป MinIO
- บันทึก detections ลง PostgreSQL (batch insert)
