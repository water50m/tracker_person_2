import cv2
import numpy as np
import torch
import torch.nn as nn
from torchvision import transforms, models
from PIL import Image
from ultralytics import YOLO
import yt_dlp
import time
import os # 🌟 เพิ่ม os สำหรับสร้างโฟลเดอร์

# ==========================================
# 1. ตั้งค่าระบบและ Constants
# ==========================================
device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
print(f"🚀 Performance Setup: Running on {device}")

if device.type == 'cuda':
    torch.backends.cudnn.benchmark = True

# 🌟 สร้างโฟลเดอร์สำหรับเก็บภาพเฟรมที่มีปัญหา
DEBUG_FOLDER = "debug_frames"
if not os.path.exists(DEBUG_FOLDER):
    os.makedirs(DEBUG_FOLDER)
    print(f"📁 สร้างโฟลเดอร์สำหรับเก็บภาพ Debug: {DEBUG_FOLDER}")

ATTRIBUTES_26 = [
    'Female', 'AgeOver60', 'Age18-60', 'AgeLess18', 'Front', 'Side', 'Back', 
    'Hat', 'Glasses', 'HandBag', 'ShoulderBag', 'Backpack', 'HoldObjectsInFront', 
    'ShortSleeve', 'LongSleeve', 'UpperStripe', 'UpperLogo', 'UpperPlaid', 
    'UpperSplice', 'LowerStripe', 'LowerPattern', 'LongCoat', 'Trousers', 
    'Shorts', 'Skirt&Dress', 'boots'
]
ATTRIBUTES_20 = [
    'Age18-60', 'AgeLess18', 'AgeOver60', 'Female', 'LongCoat', 'LongSleeve', 
    'LowerPattern', 'LowerStripe', 'ShortSleeve', 'Shorts', 'Skirt&Dress', 
    'Trousers', 'UpperLogo', 'UpperPlaid', 'UpperSplice', 'UpperStride', 
    'boots', 'bottom_capri', 'dress', 'skirt'
]
ATTRIBUTES_5 = ['ShortSleeve', 'LongSleeve', 'Trousers', 'Shorts', 'Skirt&Dress']

# ==========================================
# 2. โหลด Checkpoint และสร้างโมเดล
# ==========================================
weights_path = r'E:\ALL_CODE\my-project\models\resnet50_focused_epoch_30.pth' 
checkpoint = torch.load(weights_path, map_location=device)
state_dict = checkpoint['model_state_dict'] if 'model_state_dict' in checkpoint else checkpoint

num_classes = state_dict['fc.weight'].shape[0]
print(f"🔍 ตรวจพบไฟล์โมเดลขนาด: {num_classes} คลาส")

if num_classes == 26:
    CURRENT_ATTRIBUTES = ATTRIBUTES_26
    SLEEVE_IDX = [13, 14]
    BOTTOM_IDX = [22, 23, 24]
elif num_classes == 20:
    CURRENT_ATTRIBUTES = ATTRIBUTES_20
    SLEEVE_IDX = [5, 8]
    BOTTOM_IDX = [9, 11, 16, 17, 18, 19]
elif num_classes == 5:
    CURRENT_ATTRIBUTES = ATTRIBUTES_5
    SLEEVE_IDX = [0, 1]
    BOTTOM_IDX = [2, 3, 4]
else:
    raise ValueError(f"❌ ไม่รองรับโมเดลขนาด {num_classes} คลาส")

is_resnet50 = 'layer1.0.conv3.weight' in state_dict
is_resnet34 = 'layer4.2.conv1.weight' in state_dict and not is_resnet50

if is_resnet50:
    model = models.resnet50(weights=None)
elif is_resnet34:
    model = models.resnet34(weights=None)
else:
    model = models.resnet18(weights=None)

model.fc = nn.Linear(model.fc.in_features, num_classes) 
model.load_state_dict(state_dict) 
model.to(device)
model.eval()

# 🌟 ลดขนาดภาพก่อนเข้า YOLO เพื่อความเร็ว (imgsz=640) หรือลองใช้รุ่น yolo11n.pt
yolo_model = YOLO('yolo11s.pt') 

classify_transform = transforms.Compose([
    transforms.Resize((256, 128)),
    transforms.ToTensor(),
    transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225])
])

def get_hsv_color(img_bgr):
    if img_bgr is None or img_bgr.size == 0: return "Unknown"
    hsv_crop = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2HSV)
    avg_hsv = cv2.mean(hsv_crop)[:3]
    h, s, v = avg_hsv
    if v < 40: return "Black"
    if s < 40 and v > 200: return "White"
    if s < 40 and v <= 200: return "Gray"
    if (h < 10 or h > 160) and s > 80: return "Red"
    if 10 <= h <= 30 and s > 80: return "Yellow/Orange"
    if 35 <= h <= 85 and s > 80: return "Green"
    if 90 <= h <= 140 and s > 80: return "Blue"
    if 10 < h < 20 and 20 < v < 200: return "Brown"
    return "Mixed"

def get_youtube_url(url):
    ydl_opts = {'format': 'best', 'quiet': True}
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=False)
        return info['url']

# ==========================================
# 4. ลูปการทำงานหลัก
# ==========================================
source = r"E:\ALL_CODE\my-project\temp_videos\YTDown.com_YouTube_LIVE-footage-Bangkok-Earthquake-28-03-25_Media_I5jaBKWPy6g_001_1080p.mp4"
try:
    video_url = get_youtube_url(source) if "youtube.com" in source or "youtu.be" in source else source
except:
    video_url = source 

cap = cv2.VideoCapture(video_url)

video_fps = cap.get(cv2.CAP_PROP_FPS)
if video_fps <= 0 or np.isnan(video_fps): video_fps = 30.0
target_frame_time = 1.0 / video_fps
fps_history = [] 

frame_count = 0 
track_history = {}
skip_frames = 2 
last_drawn_data = [] 

print(f"🎥 เริ่มวิเคราะห์วิดีโอ (Target FPS: {video_fps}) | กด 'q' เพื่อหยุด")

while cap.isOpened():
    loop_start_time = time.time() 
    
    t_read_start = time.perf_counter()
    success, frame = cap.read()
    if not success: break
    t_read = (time.perf_counter() - t_read_start) * 1000
        
    frame_count += 1 
    annotated_frame = frame.copy()

    t_yolo, t_prep, t_resnet, t_post = 0, 0, 0, 0

    if frame_count % (skip_frames + 1) == 1:
        last_drawn_data = [] 
        
        t_yolo_start = time.perf_counter()
        # 🌟 ใส่ imgsz=640 เพื่อเร่งความเร็ว YOLO
        results = yolo_model.track(frame, classes=[0], persist=True, verbose=False, conf=0.45, imgsz=640)
        t_yolo = (time.perf_counter() - t_yolo_start) * 1000
        
        if results[0].boxes:
            boxes = results[0].boxes.xyxy.cpu().numpy()
            crops_for_resnet = []
            valid_indices = []
            color_results = []

            t_prep_start = time.perf_counter()
            for i, box in enumerate(boxes):
                x1, y1, x2, y2 = map(int, box)
                x1, y1 = max(0, x1), max(0, y1)
                
                person_crop = frame[y1:y2, x1:x2]
                if person_crop.size == 0 or person_crop.shape[0] < 32 or person_crop.shape[1] < 32: 
                    continue
                
                img_pil = Image.fromarray(cv2.cvtColor(person_crop, cv2.COLOR_BGR2RGB))
                tensor = classify_transform(img_pil)
                crops_for_resnet.append(tensor)
                valid_indices.append(i)

                h, w = y2 - y1, x2 - x1
                shirt_crop = frame[max(0,int(y1+(h*0.15))):int(y1+(h*0.45)), max(0,int(x1+(w*0.2))):int(x2-(w*0.2))]
                bottom_crop = frame[max(0,int(y1+(h*0.50))):int(y1+(h*0.90)), max(0,int(x1+(w*0.2))):int(x2-(w*0.2))]
                color_results.append((get_hsv_color(shirt_crop), get_hsv_color(bottom_crop)))
            t_prep = (time.perf_counter() - t_prep_start) * 1000

            if crops_for_resnet:
                batch_tensor = torch.stack(crops_for_resnet).to(device)
                use_amp = True if device.type == 'cuda' else False
                
                t_resnet_start = time.perf_counter()
                with torch.no_grad():
                    with torch.autocast(device_type=device.type, enabled=use_amp):
                        outputs = model(batch_tensor)
                    all_probs = torch.sigmoid(outputs.to(torch.float32)).cpu().numpy()
                all_probs = np.nan_to_num(all_probs, nan=0.0)
                t_resnet = (time.perf_counter() - t_resnet_start) * 1000

                # 🌟 ระบบตรวจสอบ Frame ผิดปกติ (Anomaly Catcher)
                if t_resnet > 200: # ถ้าเกิน 200 ms ถือว่าเริ่มช้าผิดปกติ
                    num_people = len(crops_for_resnet)
                    file_name = f"{DEBUG_FOLDER}/frame_{frame_count}_resnet_{t_resnet:.0f}ms_people_{num_people}.jpg"
                    
                    # วาดกล่องของคนที่มีปัญหาในเฟรมนั้นเลยเพื่อวิเคราะห์
                    debug_frame = frame.copy()
                    for idx in valid_indices:
                        dx1, dy1, dx2, dy2 = map(int, boxes[idx])
                        cv2.rectangle(debug_frame, (dx1, dy1), (dx2, dy2), (0, 0, 255), 2)
                        cv2.putText(debug_frame, "Sent to ResNet", (dx1, dy1-10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0,0,255), 2)
                    
                    cv2.imwrite(file_name, debug_frame)
                    print(f"🚨 [WARNING] ตรวจพบการประมวลผลช้าผิดปกติ! บันทึกภาพไว้ที่: {file_name}")

                t_post_start = time.perf_counter()
                track_ids = results[0].boxes.id.int().cpu().numpy() if results[0].boxes.id is not None else [-1] * len(boxes)

                for idx, probs, colors, track_id in zip(valid_indices, all_probs, color_results, track_ids):
                    x1, y1, x2, y2 = map(int, boxes[idx])
                    
                    bonus_probs = probs.copy() 
                    bonus_probs[bonus_probs >= 0.98] *= 1.5 
                    
                    if track_id != -1:
                        if track_id not in track_history: track_history[track_id] = []
                        if not np.isnan(bonus_probs).any(): track_history[track_id].append(bonus_probs)
                        if len(track_history[track_id]) > 15: track_history[track_id].pop(0)
                        final_scores = np.mean(track_history[track_id], axis=0) if track_history[track_id] else bonus_probs
                    else:
                        final_scores = bonus_probs

                    shirt_c, bottom_c = colors
                    detected_info = [f"ID:{track_id} Shirt: {shirt_c}", f"Pants: {bottom_c}"]

                    for group_idx in [SLEEVE_IDX, BOTTOM_IDX]:
                        g_probs = [final_scores[i] for i in group_idx]
                        max_i = group_idx[np.argmax(g_probs)]
                        for i in group_idx:
                            if final_scores[i] > 0.5 or i == max_i:
                                detected_info.append(f"{CURRENT_ATTRIBUTES[i]} ({min(final_scores[i]*100, 100):.0f}%)")

                    last_drawn_data.append({"box": (x1, y1, x2, y2), "info": detected_info})
                t_post = (time.perf_counter() - t_post_start) * 1000

        print(f"⏱️ [Frame {frame_count}] Read: {t_read:.1f}ms | YOLO: {t_yolo:.1f}ms | PrepCrop: {t_prep:.1f}ms | ResNet: {t_resnet:.1f}ms | Logic: {t_post:.1f}ms")

    t_draw_start = time.perf_counter()
    for data in last_drawn_data:
        bx = data["box"]
        cv2.rectangle(annotated_frame, (bx[0], bx[1]), (bx[2], bx[3]), (0, 255, 255), 2)
        for j, text in enumerate(data["info"]):
            y_p = bx[1] + 20 + (j * 18)
            cv2.putText(annotated_frame, text, (bx[0]+5, y_p), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0,0,0), 3)
            cv2.putText(annotated_frame, text, (bx[0]+5, y_p), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0,255,255) if j>1 else (0,255,0), 1)
    t_draw = (time.perf_counter() - t_draw_start) * 1000

    processing_time = time.time() - loop_start_time
    sleep_time = target_frame_time - processing_time
    if sleep_time > 0:
        time.sleep(sleep_time)

    total_frame_time = time.time() - loop_start_time
    fps_history.append(1.0 / total_frame_time if total_frame_time > 0 else video_fps)
    if len(fps_history) > 30: fps_history.pop(0)
    avg_fps = sum(fps_history) / len(fps_history)

    cv2.putText(annotated_frame, f"Frame: {frame_count} | Avg FPS: {avg_fps:.1f}", (20, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 0), 4)
    cv2.putText(annotated_frame, f"Frame: {frame_count} | Avg FPS: {avg_fps:.1f}", (20, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 255), 2)

    cv2.imshow("CCTV Analytics (Smoothed)", annotated_frame)
    if cv2.waitKey(1) & 0xFF == ord('q'): break

cap.release()
cv2.destroyAllWindows()