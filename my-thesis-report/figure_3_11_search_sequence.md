# ภาพที่ 3.11 Sequence Diagram การค้นหาบุคคลจากเงื่อนไขเสื้อผ้าและสี

```mermaid
sequenceDiagram
    autonumber
    actor User as ผู้ใช้
    participant UI as Next.js Investigation UI
    participant API as FastAPI Search API
    participant Controller as DetectionController
    participant DB as PostgreSQL
    participant Storage as MinIO

    User->>UI: เลือกเงื่อนไขค้นหา<br/>เสื้อผ้า สี กล้อง วิดีโอ เวลา
    UI->>API: GET /api/search/persons<br/>หรือ POST /api/search/advanced
    API->>Controller: ส่ง logic, threshold, filters
    Controller->>Controller: แปลง threshold 0-1 เป็นเปอร์เซ็นต์ 0-100
    Controller->>Controller: สร้าง WHERE clause ตาม OR/AND
    Controller->>DB: COUNT DISTINCT detections
    DB-->>Controller: total results
    Controller->>DB: SELECT detections + aggregate items/colors
    DB-->>Controller: rows พร้อม items และ color metadata
    Controller->>Controller: format ผลลัพธ์และคำนวณ has_more
    Controller-->>API: results, total, page, has_more
    API-->>UI: JSON response
    UI->>Storage: โหลดภาพจาก image_path ผ่าน API/proxy
    Storage-->>UI: ภาพ crop ของบุคคล
    UI-->>User: แสดงผลลัพธ์พร้อมรูป สี เสื้อผ้า เวลา และกล้อง
```

## คำอธิบายสำหรับใส่ในรายงาน

แผนภาพนี้แสดงการทำงานของฟังก์ชันค้นหาย้อนหลัง ผู้ใช้กำหนดเงื่อนไขในหน้า Investigation จากนั้น frontend ส่งเงื่อนไขไปยัง FastAPI ระบบจะสร้าง SQL query โดย join ตาราง `detections`, `detection_items` และ `detection_colors` เพื่อค้นหาผลลัพธ์ที่ตรงกับเสื้อผ้า สี กล้อง วิดีโอ และช่วงเวลา สำหรับ advanced search ระบบสามารถกำหนดสีเฉพาะให้เสื้อผ้าแต่ละประเภทได้ และจัดอันดับผลลัพธ์ด้วย relevance score

