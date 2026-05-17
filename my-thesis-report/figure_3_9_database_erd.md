# ภาพที่ 3.9 แผนภาพความสัมพันธ์ของฐานข้อมูลหลัก (Database ERD)

```mermaid
erDiagram
    CAMERAS ||--o{ PROCESSED_VIDEOS : "camera_id"
    CAMERAS ||--o{ DETECTIONS : "camera_id"
    PROCESSED_VIDEOS ||--o{ DETECTIONS : "video_id"
    DETECTIONS ||--o{ DETECTION_ITEMS : "detection_id"
    DETECTION_ITEMS ||--o{ DETECTION_COLORS : "detection_item_id"
    DETECTIONS ||--o{ DETECTION_COLORS : "detection_id"

    CAMERAS {
        int id PK
        varchar name
        text source_url
        boolean is_active
    }

    PROCESSED_VIDEOS {
        uuid id PK
        varchar camera_id
        text label
        text filename
        text file_path
        varchar status
        int progress
        int width
        int height
        timestamp created_at
        timestamp updated_at
    }

    DETECTIONS {
        uuid id PK
        int track_id
        timestamp timestamp
        text image_path
        varchar camera_id
        text video_id
        float video_time_offset
        jsonb bbox
        jsonb embedding
        jsonb clothes
    }

    DETECTION_ITEMS {
        uuid id PK
        uuid detection_id FK
        int item_index
        varchar class_name
        varchar category
        float confidence
        jsonb bbox
        timestamp created_at
    }

    DETECTION_COLORS {
        uuid id PK
        uuid detection_id FK
        uuid detection_item_id FK
        jsonb top_colors
        varchar primary_color
        varchar primary_tone_group
        jsonb color_groups
        jsonb brightness_groups
        jsonb vibrancy_groups
        jsonb temperature_groups
        jsonb clothing_groups
        timestamp created_at
    }
```

## คำอธิบายสำหรับใส่ในรายงาน

แผนภาพนี้แสดงโครงสร้างข้อมูลหลักของระบบ โดย `detections` เป็นตารางกลางที่เก็บผลการตรวจจับบุคคลในระดับเฟรมหรือช่วงเวลา ส่วน `detection_items` ใช้แยกรายการเสื้อผ้าที่ตรวจพบในแต่ละบุคคล และ `detection_colors` ใช้เก็บข้อมูลสีของเสื้อผ้าแต่ละรายการ การแยกข้อมูลเสื้อผ้าและสีออกจากตาราง `detections` ทำให้ระบบรองรับการค้นหาแบบละเอียด เช่น เสื้อแขนยาวสีแดง หรือกางเกงขายาวสีน้ำเงิน ได้ดีกว่าการเก็บทุกอย่างรวมกันใน field เดียว

