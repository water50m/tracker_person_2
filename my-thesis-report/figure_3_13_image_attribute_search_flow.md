# ภาพที่ 3.13 Flow การค้นหาด้วยรูปภาพตัวอย่าง

```mermaid
flowchart TD
    A["ผู้ใช้อัปโหลดรูปภาพตัวอย่าง"] --> B["Next.js SearchFilterBar / InvestigationContext"]
    B --> C["POST /api/search/detect-attributes"]
    C --> D["FastAPI อ่าน UploadFile เป็น bytes"]
    D --> E["DetectionController.analyze_image_for_search"]
    E --> F["ImageAnalyzer"]
    F --> G["แปลง image bytes เป็น OpenCV image"]
    G --> H["FrameProcessor.process_frame"]
    H --> I["YOLO ตรวจจับบุคคล"]
    I --> J{"พบคนหรือไม่?"}
    J -->|ไม่พบ| K["ส่ง status: no_detections"]
    J -->|พบ| L["เลือกบุคคลหลักจากผลตรวจจับ"]
    L --> M["วิเคราะห์เสื้อผ้าและสี"]
    M --> N["คืน detected_attributes<br/>class_name, color_name, color_groups"]
    N --> O["Frontend auto-fill filter"]
    O --> P["เรียก search persons / advanced search"]
    P --> Q["แสดงผลลัพธ์จากฐานข้อมูล"]
```

## คำอธิบายสำหรับใส่ในรายงาน

แผนภาพนี้แสดง flow การค้นหาด้วยรูปภาพตัวอย่าง ระบบไม่ได้ใช้รูปภาพเพื่อยืนยันตัวตนแบบสมบูรณ์ แต่ใช้ `ImageAnalyzer` และ `FrameProcessor` เพื่อดึง attribute ที่มองเห็นได้ เช่น ประเภทเสื้อผ้า สีหลัก และกลุ่มสี จากนั้น frontend นำ attribute ที่ได้ไปเติมเป็นเงื่อนไขค้นหาอัตโนมัติ ช่วยให้ผู้ใช้เริ่มค้นหาได้เร็วขึ้นโดยไม่ต้องเลือกเงื่อนไขเองทั้งหมด
