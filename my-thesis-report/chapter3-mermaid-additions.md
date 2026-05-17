# Mermaid Diagram ที่ควรเพิ่มในบทที่ 3

ไฟล์นี้สรุปแผนภาพ Mermaid ที่ควรเพิ่มเข้าไปในบทที่ 3 หลังจากอ่านโครงสร้างโปรเจกต์จริง โดยไม่ทับเลขภาพ 3.4-3.8 ที่บทปัจจุบันกันไว้สำหรับ screenshot ของหน้าจอระบบ

## รายการภาพที่มีอยู่แล้ว

| ภาพ | สถานะ | หมายเหตุ |
|---|---|---|
| ภาพที่ 3.1 สถาปัตยกรรมระบบ | มีแล้ว | ควรใช้เป็นภาพรวมทั้งระบบ |
| ภาพที่ 3.2 Two-pass processing | มีแล้ว | ควรหลีกเลี่ยงการใส่ตัวเลข FPS/ms ถ้าไม่ได้วัดจริง |
| ภาพที่ 3.3 Track ID recovery | มีแล้ว | เหมาะกับอธิบาย HybridTracker |
| ภาพที่ 3.4-3.8 | ยังควรเป็น screenshot | Dashboard, Input Manager, Realtime, Search/Investigation, Camera Management |

## รายการ Mermaid ที่เพิ่มให้

| ภาพที่แนะนำ | ไฟล์ | ควรใส่หลังหัวข้อ |
|---|---|---|
| ภาพที่ 3.9 Database ERD | `figure_3_9_database_erd.md` | 3.3.7 การออกแบบฐานข้อมูล |
| ภาพที่ 3.10 Video Queue Processing Flow | `figure_3_10_video_queue_processing_flow.md` | 3.4.5 การประมวลผลวิดีโอและสตรีม |
| ภาพที่ 3.11 Search Sequence Diagram | `figure_3_11_search_sequence.md` | 3.4.6 การพัฒนาฟังก์ชันค้นหา หรือ 3.5.2 API |
| ภาพที่ 3.12 Frontend-Backend API Map | `figure_3_12_frontend_backend_api_map.md` | 3.5.2 การเชื่อมต่อ API ระหว่าง Frontend และ Backend |
| ภาพที่ 3.13 Image Attribute Search Flow | `figure_3_13_image_attribute_search_flow.md` | 3.5.3 การค้นหาด้วยรูปภาพตัวอย่าง |

## ข้อเสนอแนะก่อนนำไปใส่เล่ม

1. ถ้าแปลง Mermaid เป็นรูปภาพสำหรับ Word ให้ใช้เลขภาพตามลำดับจริงในเล่มอีกครั้ง เพราะถ้าเพิ่ม screenshot ก่อนหน้า เลขภาพอาจเลื่อน
2. ภาพที่ 3.2 เดิมมีตัวเลขเวลาโดยประมาณ เช่น ms/frame และ 30fps หากยังไม่ได้ทดสอบจริง ควรเปลี่ยนเป็นคำว่า “ทำงานแบบ realtime/ประมวลผลเบื้องต้น” แทนการระบุตัวเลข
3. ภาพ ERD ควรใส่ในบทที่ 3 เพราะช่วยอธิบายว่าทำไม search ต้อง join `detections`, `detection_items` และ `detection_colors`
4. ภาพ Search Sequence ควรใส่คู่กับคำอธิบาย advanced search เพราะเป็นส่วนที่ซับซ้อนที่สุดของระบบฝั่งผู้ใช้
5. ภาพ Image Attribute Search ควรใส่เพราะเป็น feature สำคัญที่ทำให้ผู้ใช้ไม่ต้องเลือกสีและประเภทเสื้อผ้าด้วยตนเองทั้งหมด
