import cv2
import torch
from torch.version import cuda
from ultralytics import YOLO

print("CUDA Available:", torch.cuda.is_available())
if torch.cuda.is_available():
    print("Device Name:", torch.cuda.get_device_name(0))
    device = "cuda"
else:
    print("คำเตือน: ไม่พบ CUDA ระบบจะรันบน CPU แทน ซึ่งจะทำให้วิดีโอประมวลผลช้ามาก")
    device = "cpu"
# 1. Load both models
# yolov11n.pt will automatically download if you don't have it
person_model = YOLO('yolo11n.pt')  
custom_model = YOLO(r'E:\ALL_CODE\my-project\models\prepare_dataset.pt') # Replace with the path to your custom .pt file

# 2. โหลดไฟล์วิดีโอ (เปลี่ยน path เป็นไฟล์วิดีโอของคุณ)
# หากต้องการใช้กล้องเว็บแคม ให้เปลี่ยน 'test_video.mp4' เป็น 0
video_path = r'E:\ALL_CODE\my-project\temp_videos\CAM-01_4p-c0-new.mp4' 
cap = cv2.VideoCapture(video_path)

if not cap.isOpened():
    print(f"Error: ไม่สามารถเปิดไฟล์วิดีโอได้ {video_path}")
    exit()

# อ่านขนาดวิดีโอเพื่อใช้ป้องกันกรอบภาพล้นกรอบ
frame_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
frame_height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

print("กำลังประมวลผลวิดีโอ... กด 'q' เพื่อออก")
# ---------------------------------------------------------
# 🌟 สร้าง Dictionary เพื่อเก็บ "ความจำ" ของแต่ละ ID
# รูปแบบ: { track_id : "สิ่งที่โมเดล 2 ตรวจเจอ" }
track_history = {} 
# ---------------------------------------------------------

while cap.isOpened():
    success, frame = cap.read()
    if not success:
        break

    # 1. Track คน (โมเดล 1)
    person_results = person_model.track(
        frame, persist=True, classes=[0], device=device, 
        verbose=False, tracker="bytetrack.yaml", conf=0.3
    )

    # เก็บ ID ที่อยู่ในเฟรมปัจจุบัน เพื่อเอาไว้ล้างข้อมูล ID ที่หายไปแล้ว
    current_ids = []

    if person_results[0].boxes.id is not None:
        boxes = person_results[0].boxes.xyxy.cpu().numpy().astype(int)
        ids = person_results[0].boxes.id.cpu().numpy().astype(int)

        for box, track_id in zip(boxes, ids):
            current_ids.append(track_id)
            x1, y1, x2, y2 = box
            
            x1, y1 = max(0, x1), max(0, y1)
            x2, y2 = min(frame_width, x2), min(frame_height, y2)
            
            # --- ตรวจสอบว่ามีข้อมูลของ ID นี้ใน History หรือยัง ---
            if track_id not in track_history:
                track_history[track_id] = "Unknown" # ค่าเริ่มต้นถ้ายังไม่เคยเจอ

            # ครอปคน
            person_crop = frame[y1:y2, x1:x2]
            if person_crop.size > 0:
                # 2. ให้โมเดล 2 ทำนายภาพครอปเสื้อผ้า
                custom_results = custom_model(person_crop, device=device, verbose=False)
                
                # 🌟 สร้างลิสต์ว่างๆ มารองรับเสื้อผ้าหลายชิ้น
                detected_clothes = [] 
                
                for c_res in custom_results:
                    for c_box in c_res.boxes:
                        # 💡 แนะนำ: กรองด้วยความมั่นใจ (Confidence) สัก 40% เพื่อลดกรอบขยะ
                        if float(c_box.conf[0]) > 0.40: 
                            cls_name = custom_model.names[int(c_box.cls[0])]
                            
                            # ป้องกันการเก็บชื่อคลาสซ้ำ (เช่น โมเดลตรวจเจอ "Shirt" 2 กรอบในคนเดียว)
                            if cls_name not in detected_clothes:
                                detected_clothes.append(cls_name)
                            
                            # วาดกรอบเสื้อผ้าแต่ละชิ้น (สีเขียว)
                            cx1, cy1, cx2, cy2 = map(int, c_box.xyxy[0])
                            orig_x1, orig_y1 = x1 + cx1, y1 + cy1
                            orig_x2, orig_y2 = x1 + cx2, y1 + cy2
                            cv2.rectangle(frame, (orig_x1, orig_y1), (orig_x2, orig_y2), (0, 255, 0), 1)

                # 🌟 อัปเดตความจำลง Dictionary
                if len(detected_clothes) > 0:
                    # ถ้านำลิสต์มารวมกันด้วยลูกน้ำ เช่น ["Shirt", "Pants"] -> "Shirt, Pants"
                    track_history[track_id] = ", ".join(detected_clothes)
                    
            # 3. นำข้อมูลจาก History มาแสดงผลประกอบกับตัวคน
            # ถ้าไม่เคยเจออะไรเลยจะขึ้น Unknown แต่ถ้าเจอจะขึ้นสิ่งของทั้งหมดที่จำได้
            status_text = f'ID: {track_id} | {track_history[track_id]}'
            
            cv2.rectangle(frame, (x1, y1), (x2, y2), (255, 0, 0), 2)
            cv2.putText(frame, status_text, (x1, y1 - 10), 
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)

    # 4. (Optional) ล้างหน่วยความจำสำหรับคนที่เดินออกนอกกล้องไปแล้ว
    # เพื่อไม่ให้กิน RAM สะสม
    keys_to_delete = [k for k in track_history.keys() if k not in current_ids]
    for k in keys_to_delete:
        # อาจจะหน่วงเวลาไว้สัก 30 เฟรมค่อยลบ เผื่อคนแค่เดินหลบหลังเสา
        del track_history[k]

    cv2.imshow('Tracking with Attribute Memory', frame)
    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

cap.release()
cv2.destroyAllWindows()