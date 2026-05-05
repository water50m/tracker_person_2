import cv2
import os
import time
from ultralytics import YOLO
from PIL import Image
from google import genai
from dotenv import load_dotenv
from vidgear.gears import CamGear

# ==========================================
# 1. ตั้งค่า API และตัวแปรพื้นฐาน
# ==========================================
load_dotenv()
my_api_key = os.getenv('GEMINI_API') 

if not my_api_key:
    print("🚨 หา API Key ไม่เจอ! ตรวจสอบไฟล์ .env ครับ")
    exit()

client = genai.Client(api_key=my_api_key)

# โหลดโมเดล YOLO
yolo_model = YOLO("yolov8n.pt") 

CLASSES = [
    'short_sleeve_top', 'long_sleeve_top', 'short_sleeve_outwear', 
    'long_sleeve_outwear', 'short_sleeve_dress', 'long_sleeve_dress',
    'trousers', 'shorts', 'skirt', 'vest_dress', 'sling_dress', 'vest', 'sling'
]

main_output_folder = "youtube_auto_capture" 
for c in CLASSES + ["unknown"]:
    os.makedirs(os.path.join(main_output_folder, c), exist_ok=True)

# ------------------------------------------
# 🌟 ความลับอยู่ตรงนี้: ฐานข้อมูลจำ ID คนที่ตรวจแล้ว
# ------------------------------------------
analyzed_track_ids = set()

# ==========================================
# 2. เริ่มเปิด YouTube และประมวลผล
# ==========================================
YOUTUBE_URL = "https://www.youtube.com/watch?v=bbBGNNPu0rg"
print("กำลังเชื่อมต่อ YouTube...")

options = {"STREAM_RESOLUTION": "720p"} 
stream = CamGear(source=YOUTUBE_URL, stream_mode=True, logging=True, **options).start()

print("เริ่มการตรวจจับแบบมี Tracking (กด Ctrl+C เพื่อหยุด)...")

while True:
    frame = stream.read()
    if frame is None:
        print("⚠️ วิดีโอจบ หรือสัญญาณภาพขาดหาย")
        break

    # ใช้คำสั่ง .track() แทนตอนหาคน (YOLO จะใช้ ByteTrack เบื้องหลังให้เลย)
    # persist=True คือให้มันจำ ID ข้ามเฟรมได้
    results = yolo_model.track(frame, classes=[0], persist=True, verbose=False)
    
    for r in results:
        boxes = r.boxes
        
        # เช็กก่อนว่ามีคนในเฟรมและมี ID หรือยัง
        if boxes.id is not None:
            track_ids = boxes.id.int().cpu().tolist()
            
            for box, track_id in zip(boxes, track_ids):
                # ถ้า ID นี้เคยส่งให้ Gemini ตรวจแล้ว -> ข้ามไปเลย ประหยัด API!
                if track_id in analyzed_track_ids:
                    continue
                
                # ถ้าเป็นคนใหม่ (ID ใหม่) ดึงพิกัดมากรอบรูป
                x1, y1, x2, y2 = map(int, box.xyxy[0])
                
                # กรองคนไกลๆ ทิ้ง (ขนาดกรอบเล็กไปภาพจะแตก Gemini จะงง)
                if (x2 - x1) < 100 or (y2 - y1) < 150:
                    continue
                
                # ----------------------------------
                # เจอคนใหม่ที่ขนาดภาพชัดเจน! เริ่มกระบวนการส่ง API
                # ----------------------------------
                person_crop = frame[y1:y2, x1:x2]
                person_crop_rgb = cv2.cvtColor(person_crop, cv2.COLOR_BGR2RGB)
                pil_img = Image.fromarray(person_crop_rgb)
                
                prompt = f"""
                You are an expert fashion classifier. Look at the clothing worn by the person in this image.
                Classify the MAIN visible clothing into EXACTLY ONE of the following categories:
                {', '.join(CLASSES)}
                
                Rules:
                - Respond with ONLY the exact category name.
                - If you cannot decide or it doesn't fit, respond with 'unknown'.
                - Do not add any other text.
                """
                
                print(f"🔍 เจอคนใหม่ (ID: {track_id}) กำลังส่งภาพให้ Gemini วิเคราะห์...")
                
                # ระบบ Auto-Retry ป้องกัน API Limit
                max_retries = 3
                for attempt in range(max_retries):
                    try:
                        response = client.models.generate_content(
                            model='gemini-2.0-flash',
                            contents=[prompt, pil_img]
                        )
                        predicted_class = response.text.strip().lower()
                        if predicted_class not in CLASSES:
                            predicted_class = "unknown"
                        break 
                    except Exception as e:
                        error_msg = str(e)
                        if "429" in error_msg or "RESOURCE_EXHAUSTED" in error_msg:
                            print(f"⚠️ โควตา API เต็ม! พักเบรก 60 วินาที... (ครั้งที่ {attempt+1}/{max_retries})")
                            time.sleep(60)
                            predicted_class = "unknown"
                        else:
                            print(f"❌ Gemini API Error: {e}")
                            predicted_class = "unknown"
                            break
                
                # เซฟรูปลงโฟลเดอร์
                timestamp = int(time.time() * 1000)
                filename = f"id{track_id}_{predicted_class}_{timestamp}.jpg"
                filepath = os.path.join(main_output_folder, predicted_class, filename)
                
                cv2.imwrite(filepath, person_crop)
                print(f"✅ บันทึก ID: {track_id} -> โฟลเดอร์ {predicted_class}/ สำเร็จ!\n")
                
                # *** สำคัญมาก: เมมโมรี่ไว้ว่า ID นี้ตรวจแล้ว จะได้ไม่ส่งซ้ำ ***
                analyzed_track_ids.add(track_id)
                
                # ดีเลย์นิดนึงไม่ให้ยิง API รัวเกินไปสำหรับสายฟรี
                time.sleep(4)

stream.stop()
print("ทำงานเสร็จสิ้น!")