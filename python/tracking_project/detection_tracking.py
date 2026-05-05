import cv2
import torch
from torch.version import cuda
from ultralytics import YOLO
import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..', 'src', 'ai'))
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..', 'src', 'services'))
from color_system import (
    analyze_detailed_colors, get_color_groups, 
    get_primary_detailed_color, get_primary_color_group
)
from database import DatabaseService
from reid_utils import (
    calculate_similarity, match_lost_track, update_lost_tracks
)
from feature_extractor import ClothingEmbedder

def setup_device():
    """ตั้งค่า device สำหรับการประมวลผล"""
    print("CUDA Available:", torch.cuda.is_available())
    if torch.cuda.is_available():
        print("Device Name:", torch.cuda.get_device_name(0))
        return "cuda"
    else:
        print("คำเตือน: ไม่พบ CUDA ระบบจะรันบน CPU แทน ซึ่งจะทำให้วิดีโอประมวลผลช้ามาก")
        return "cpu"

def load_models(device):
    """โหลดโมเดล YOLO ทั้งหมด"""
    person_model = YOLO('yolo11n.pt')
    custom_model = YOLO(r'E:\ALL_CODE\my-project\models\prepare_dataset.pt')
    embedder = ClothingEmbedder(model_path=r'E:\ALL_CODE\my-project\models\prepare_dataset.pt', device=device)
    return person_model, custom_model, embedder

def init_video_capture(video_path):
    """เปิดไฟล์วิดีโอและคืนค่าข้อมูลเบื้องต้น"""
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        print(f"Error: ไม่สามารถเปิดไฟล์วิดีโอได้ {video_path}")
        exit()
    
    frame_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    frame_height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    return cap, frame_width, frame_height

def detect_persons(person_model, frame, device):
    """ตรวจจับคนและ tracking"""
    return person_model.track(
        frame, persist=True, classes=[0], device=device, 
        verbose=False, tracker="bytetrack.yaml", conf=0.3
    )

def detect_clothes(custom_model, person_crop, device, conf_threshold=0.40):
    """ตรวจจับเสื้อผ้าจากภาพครอปคน"""
    results = custom_model(person_crop, device=device, verbose=False)
    detected_clothes = []
    
    for c_res in results:
        for c_box in c_res.boxes:
            if float(c_box.conf[0]) > conf_threshold:
                cls_name = custom_model.names[int(c_box.cls[0])]
                if cls_name not in detected_clothes:
                    detected_clothes.append(cls_name)
    
    return detected_clothes

def analyze_person_features(person_crop, custom_model, embedder, device):
    """วิเคราะห์คุณสมบัติของคน (เสื้อผ้า + สีละเอียด + กลุ่มสี + 768-dim embedding)"""
    clothes = detect_clothes(custom_model, person_crop, device)
    detailed_colors = analyze_detailed_colors(person_crop)
    color_groups = get_color_groups(detailed_colors)
    embedding, cloth_names = embedder.get_embedding(person_crop)
    
    return {
        "clothes": clothes,
        "detailed_colors": detailed_colors,
        "color_groups": color_groups,
        "primary_detailed_color": get_primary_detailed_color(detailed_colors),
        "primary_color_group": get_primary_color_group(color_groups),
        "embedding": embedding
    }

def update_track_history(track_history, track_id, features, frame_count):
    """อัปเดตข้อมูลใน track_history"""
    if track_id not in track_history:
        track_history[track_id] = {
            "clothes": [],
            "detailed_colors": {},
            "color_groups": {},
            "primary_detailed_color": "unknown",
            "primary_color_group": "unknown",
            "embedding": None,
            "last_seen": frame_count,
            "confidence": 0.0
        }
    
    # อัปเดตเฉพาะถ้ามีข้อมูลใหม่
    if features["clothes"] or features["detailed_colors"] or features.get("embedding") is not None:
        track_history[track_id].update(features)
        track_history[track_id]["last_seen"] = frame_count
        track_history[track_id]["confidence"] = min(1.0, track_history[track_id]["confidence"] + 0.1)

def cleanup_old_tracks(track_history, current_ids, frame_count, timeout=60):
    """ลบข้อมูล track ที่หมดอายุ"""
    keys_to_delete = []
    for track_id in track_history.keys():
        if (track_id not in current_ids and 
            frame_count - track_history[track_id]["last_seen"] > timeout):
            keys_to_delete.append(track_id)
    
    for k in keys_to_delete:
        del track_history[k]

def draw_person_box(frame, box, track_id, track_history):
    """วาดกรอบคนและข้อมูล"""
    x1, y1, x2, y2 = box
    
    # สร้างข้อความแสดงผล
    if track_id in track_history:
        data = track_history[track_id]
        clothes_text = ", ".join(data["clothes"]) if data["clothes"] else "Unknown"
        primary_color = data.get("primary_detailed_color", "unknown")
        status_text = f'ID: {track_id} | {clothes_text} | {primary_color}'
    else:
        status_text = f'ID: {track_id} | Unknown'
    
    cv2.rectangle(frame, (x1, y1), (x2, y2), (255, 0, 0), 2)
    cv2.putText(frame, status_text, (x1, y1 + 10), 
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)

def draw_clothes_boxes(frame, person_box, clothes_results, custom_model):
    """วาดกรอบเสื้อผ้า"""
    x1, y1 = person_box[:2]
    
    for c_res in clothes_results:
        for c_box in c_res.boxes:
            if float(c_box.conf[0]) > 0.40:
                cx1, cy1, cx2, cy2 = map(int, c_box.xyxy[0])
                orig_x1, orig_y1 = x1 + cx1, y1 + cy1
                orig_x2, orig_y2 = x1 + cx2, y1 + cy2
                cv2.rectangle(frame, (orig_x1, orig_y1), (orig_x2, orig_y2), (0, 255, 0), 1)

def process_single_person(person_model, custom_model, embedder, frame, box, track_id,
                         track_history, frame_count, device, frame_width, frame_height, db=None):
    """ประมวลผลคนแต่ละคน"""
    x1, y1, x2, y2 = box

    # จำกัดกรอบไม่ให้เกินขอบภาพ
    x1, y1 = max(0, x1), max(0, y1)
    x2, y2 = min(frame_width, x2), min(frame_height, y2)

    # ครอปภาพคน
    person_crop = frame[y1:y2, x1:x2]
    if person_crop.size > 0:
        # ตรวจจับเสื้อผ้าและวิเคราะห์สี
        features = analyze_person_features(person_crop, custom_model, embedder, device)
        
        # อัปเดตประวัติ
        update_track_history(track_history, track_id, features, frame_count)
        
        # บันทึกลงฐานข้อมูล (ถ้ามี database service)
        if db is not None:
            try:
                db.insert_detection(
                    camera_id="CAM-01",
                    track_id=int(track_id),
                    class_name="person",
                    image_path="",
                    category="person",
                    detailed_colors=features["detailed_colors"],
                    color_groups=features["color_groups"],
                    primary_detailed_color=features["primary_detailed_color"],
                    primary_color_group=features["primary_color_group"],
                    clothes=features["clothes"],
                    bbox=[int(x1), int(y1), int(x2), int(y2)]
                )
            except Exception as e:
                print(f"❌ Database save error for track {track_id}: {e}")
        
        # วาดผลลัพธ์
        draw_person_box(frame, (x1, y1, x2, y2), track_id, track_history)
        
        # วาดกรอบเสื้อผ้า (ต้องได้รับ clothes_results จาก detect_clothes)
        clothes_results = custom_model(person_crop, device=device, verbose=False)
        draw_clothes_boxes(frame, (x1, y1, x2, y2), clothes_results, custom_model)

def main(enable_db=False):
    """ฟังก์ชันหลัก
    
    Args:
        enable_db: เปิด/ปิดการบันทึกลงฐานข้อมูล (default: False)
    """
    # Setup
    device = setup_device()
    person_model, custom_model, embedder = load_models(device)
    video_path = r'E:\ALL_CODE\my-project\temp_videos\CAM-01_4p-c0-new.mp4'
    cap, frame_width, frame_height = init_video_capture(video_path)
    
    # Database service
    if enable_db:
        try:
            db = DatabaseService()
            print("✅ Database service initialized")
        except Exception as e:
            print(f"⚠️  Database service failed to initialize: {e}")
            print("   ระบบจะทำงานโดยไม่บันทึกลงฐานข้อมูล")
            db = None
    else:
        db = None
        print("ℹ️  Database save disabled (enable_db=False)")
    
    # Hybrid Tracking System
    id_mapping = {}  # {byte_id: our_id}
    lost_tracks = {}  # {our_id: {features, last_seen}}
    next_our_id = 1
    
    # Memory system
    track_history = {}
    frame_count = 0
    
    print("✅ Hybrid Tracking System enabled (ByteTrack + Re-ID)")
    print("กำลังประมวลผลวิดีโอ... กด 'q' เพื่อออก")
    
    while cap.isOpened():
        success, frame = cap.read()
        if not success:
            break
        
        frame_count += 1
        current_byte_ids = []
        current_our_ids = []
        
        # ตรวจจับคนด้วย ByteTrack
        person_results = detect_persons(person_model, frame, device)
        
        if person_results[0].boxes.id is not None:
            boxes = person_results[0].boxes.xyxy.cpu().numpy().astype(int)
            byte_ids = person_results[0].boxes.id.cpu().numpy().astype(int)
            
            for box, byte_id in zip(boxes, byte_ids):
                current_byte_ids.append(byte_id)
                
                # จำกัดกรอบไม่ให้เกินขอบภาพ
                x1, y1, x2, y2 = box
                x1, y1 = max(0, x1), max(0, y1)
                x2, y2 = min(frame_width, x2), min(frame_height, y2)
                
                # ครอปภาพคน
                person_crop = frame[y1:y2, x1:x2]
                
                # ถ้าเป็น byte_id ใหม่ → พยายาม match กับ lost_tracks
                if byte_id not in id_mapping:
                    if person_crop.size > 0:
                        # วิเคราะห์ features
                        features = analyze_person_features(person_crop, custom_model, embedder, device)
                        
                        # พยายาม match กับ lost_tracks
                        recovered_id = match_lost_track(features, lost_tracks, threshold=0.7)
                        
                        if recovered_id is not None:
                            # Recover track
                            id_mapping[byte_id] = recovered_id
                            print(f"🔄 Track recovered: {recovered_id} (byte_id: {byte_id})")
                            del lost_tracks[recovered_id]
                        else:
                            # สร้าง track ใหม่
                            id_mapping[byte_id] = next_our_id
                            next_our_id += 1
                            print(f"🆕 New track: {id_mapping[byte_id]} (byte_id: {byte_id})")
                else:
                    # byte_id เดิม → วิเคราะห์ features ตามปกติ
                    if person_crop.size > 0:
                        features = analyze_person_features(person_crop, custom_model, embedder, device)
                
                # ใช้ our_id แทน byte_id
                our_id = id_mapping[byte_id]
                current_our_ids.append(our_id)
                
                # ประมวลผลตามปกติ
                if person_crop.size > 0:
                    # อัปเดตประวัติ
                    update_track_history(track_history, our_id, features, frame_count)
                    
                    # บันทึกลงฐานข้อมูล
                    if db is not None:
                        try:
                            db.insert_detection(
                                camera_id="CAM-01",
                                track_id=int(our_id),
                                class_name="person",
                                image_path="",
                                category="person",
                                detailed_colors=features["detailed_colors"],
                                color_groups=features["color_groups"],
                                primary_detailed_color=features["primary_detailed_color"],
                                primary_color_group=features["primary_color_group"],
                                clothes=features["clothes"],
                                bbox=[int(x1), int(y1), int(x2), int(y2)]
                            )
                        except Exception as e:
                            print(f"❌ Database save error for track {our_id}: {e}")
                    
                    # วาดผลลัพธ์
                    draw_person_box(frame, (x1, y1, x2, y2), our_id, track_history)
                    
                    # วาดกรอบเสื้อผ้า
                    clothes_results = custom_model(person_crop, device=device, verbose=False)
                    draw_clothes_boxes(frame, (x1, y1, x2, y2), clothes_results, custom_model)
        
        # อัปเดต lost_tracks
        update_lost_tracks(lost_tracks, track_history, current_our_ids, frame_count, timeout=60)
        
        # ลบข้อมูลเก่าจาก track_history
        cleanup_old_tracks(track_history, current_our_ids, frame_count)
        
        # แสดงผล
        cv2.imshow('Hybrid Tracking (ByteTrack + Re-ID)', frame)
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break
    
    cap.release()
    cv2.destroyAllWindows()
    
    # ปิด database connection
    if db is not None:
        db.close()
    
    print(f"\n📊 Tracking Summary:")
    print(f"   Total tracks created: {next_our_id - 1}")
    print(f"   Active tracks: {len(track_history)}")
    print(f"   Lost tracks: {len(lost_tracks)}")

if __name__ == "__main__":
    main()