import cv2
import os
from ultralytics import YOLO

# 1. Load Model
model = YOLO("yolo11n.pt") 

# 2. Configs
video_path = r"E:\ALL_CODE\my-project\temp_videos\YTDown.com_YouTube_LIVE-footage-Bangkok-Earthquake-28-03-25_Media_I5jaBKWPy6g_001_1080p.mp4"
output_folder = "tracked_results"
max_frames = 300  # ทำงานแค่ 300 frame
width_crop, height_crop = 256, 512

if not os.path.exists(output_folder):
    os.makedirs(output_folder)

cap = cv2.VideoCapture(video_path)
fps = int(cap.get(cv2.CAP_PROP_FPS))
fourcc = cv2.VideoWriter_fourcc(*'mp4v')

# เก็บ VideoWriter ของแต่ละ ID ไว้ใน Dictionary
# โครงสร้าง { track_id: cv2.VideoWriter_object }
video_writers = {}

frame_count = 0

while cap.isOpened() and frame_count < max_frames:
    success, frame = cap.read()
    if not success:
        break

    # 3. Tracking (classes=[0] คือคน)
    results = model.track(frame, persist=True, classes=[0], verbose=False)

    if results[0].boxes.id is not None:
        boxes = results[0].boxes.xyxy.cpu().numpy()
        track_ids = results[0].boxes.id.int().cpu().numpy()

        for box, track_id in zip(boxes, track_ids):
            x1, y1, x2, y2 = map(int, box)
            
            # ป้องกันพิกัดออกนอกขอบภาพ
            y1, y2 = max(0, y1), min(frame.shape[0], y2)
            x1, x2 = max(0, x1), min(frame.shape[1], x2)
            
            # 4. Crop และ Resize
            crop_img = frame[y1:y2, x1:x2]
            if crop_img.size == 0: continue # ข้ามถ้า crop พลาด
            
            crop_resized = cv2.resize(crop_img, (width_crop, height_crop))

            # 5. ตรวจสอบว่ามี VideoWriter สำหรับ ID นี้หรือยัง
            if track_id not in video_writers:
                save_path = os.path.join(output_folder, f"person_id_{track_id}.mp4")
                video_writers[track_id] = cv2.VideoWriter(save_path, fourcc, fps, (width_crop, height_crop))
                print(f"Created new video for ID: {track_id}")

            # บันทึกลงไฟล์ของ ID นั้นๆ
            video_writers[track_id].write(crop_resized)

    frame_count += 1
    if frame_count % 50 == 0:
        print(f"Processing frame: {frame_count}/{max_frames}")

# 6. คืน Memory และปิดไฟล์ทั้งหมด
cap.release()
for writer in video_writers.values():
    writer.release()
cv2.destroyAllWindows()

print(f"--- Finished ---")
print(f"Processed {frame_count} frames. Results saved in '{output_folder}'")