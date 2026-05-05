"""
pipeline_test.py — ระบบทดสอบ Detection + DeepSORT Tracking + Clothing Classification

โหมดการใช้งาน (เลือกผ่าน MODE หรือ argument):
  python pipeline_test.py            → โหมด visual (default, เห็น OpenCV window)
  python pipeline_test.py --bg       → โหมด background (ไม่มีหน้าต่าง, save DB)
  python pipeline_test.py --results  → ดูสรุปผลลัพธ์ใน DB
  python pipeline_test.py --phase 1  → เลือก phase (ใช้ร่วมกับ --bg หรือ visual)

Phase:
  1 = detect คนเท่านั้น
  2 = detect + DeepSORT tracking
  3 = detect + DeepSORT + classify clothing + บันทึก DB/รูปภาพ (full)
"""

import sys
import os
import argparse
import time
import cv2
import torch

# ==========================================
# ⚙️ CONFIG — แก้ตรงนี้ได้เลย
# ==========================================
PHASE        = 3
SOURCE       = r"E:\ALL_CODE\my-project\temp_videos\YTDown.com_YouTube_LIVE-footage-Bangkok-Earthquake-28-03-25_Media_I5jaBKWPy6g_001_1080p.mp4"
# SOURCE       = r"E:\ALL_CODE\my-project\temp_videos\CAM-01_4p-c0-new.mp4"            # 0 = webcam | path ไฟล์วิดีโอ เช่น "test.mp4"
# SOURCE       = "https://www.youtube.com/watch?v=UemFRPrl1hk"  # YouTube live
CAMERA_ID    = "test-cam"   # ID ของกล้อง (ใช้ใน DB)
MODEL_DETECT = "yolo11s.pt"
MODEL_CLOTH  = os.path.join(
    os.path.dirname(__file__), "../../models/clothing_classifier.pt"
)
MIN_BOX_W    = 0    # ปิด filter แล้ว (0 = ไม่กรอง)
MIN_BOX_H    = 0
OUTPUT_DIR   = "pipeline_results"   # โฟลเดอร์เก็บรูป (Phase 3)
CONF_THRESH  = 0.20
FRAME_SKIP   = 2    # process ทุกกี่ frame (1 = ทุก frame, 2 = ข้าม 1, 3 = ข้าม 2 ...)
EMBED_EVERY_N = 3   # สกัด embedding ทุก N รอบที่ process (ลดการเรียกโมเดล)

# ==========================================
# 👕 CLOTHING GROUP CLASSIFICATION
# ==========================================
def get_clothing_group(class_name: str) -> str:
    """
    แบ่ง class เป็น 3 กลุ่มหลัก: DRESS, TOP, BOTTOM
    ตาม class ที่มีจริงในระบบ
    """
    if not class_name or class_name == "Unknown":
        return "UNKNOWN"
    
    class_name = class_name.lower().strip()
    
    # Dress group - เดรสทั้งหมด
    DRESS_CLASSES = [
        "short sleeve dress", "long sleeve dress", "vest dress", "sling dress"
    ]
    
    # Top group - เสื้อช่วงบน
    TOP_CLASSES = [
        "short sleeve top", "long sleeve top", "short sleeve outwear", 
        "long sleeve outwear", "vest", "sling"
    ]
    
    # Bottom group - กางเกงและกระโปรง
    BOTTOM_CLASSES = [
        "shorts", "trousers", "skirt"
    ]
    
    # Check exact match first
    if class_name in DRESS_CLASSES:
        return "DRESS"
    elif class_name in TOP_CLASSES:
        return "TOP"
    elif class_name in BOTTOM_CLASSES:
        return "BOTTOM"
    
    # Fallback: check partial matches
    if "dress" in class_name:
        return "DRESS"
    elif any(top in class_name for top in ["top", "outwear", "vest", "sling"]):
        return "TOP"
    elif any(bottom in class_name for bottom in ["shorts", "trousers", "skirt", "pants"]):
        return "BOTTOM"
    
    return "UNKNOWN"

def get_best_2_from_different_groups(votes: dict) -> list:
    """
    เลือก best 2 classes จากคนละกลุ่ม (Dress/Top/Bottom)
    คืนค่า: [(class_name, group, votes), ...]
    """
    if not votes:
        return [("Unknown", "UNKNOWN", 0)]
    
    # Group votes by category
    grouped_votes = {
        "DRESS": [],
        "TOP": [],
        "BOTTOM": [],
        "UNKNOWN": []
    }
    
    for class_name, count in votes.items():
        group = get_clothing_group(class_name)
        grouped_votes[group].append((class_name, count))
    
    # Sort each group by votes (highest first)
    for group in grouped_votes:
        grouped_votes[group].sort(key=lambda x: x[1], reverse=True)
    
    # Get best from each group
    best_dress = grouped_votes["DRESS"][0] if grouped_votes["DRESS"] else None
    best_top = grouped_votes["TOP"][0] if grouped_votes["TOP"] else None
    best_bottom = grouped_votes["BOTTOM"][0] if grouped_votes["BOTTOM"] else None
    
    # Select best 2 from DIFFERENT groups
    best_2 = []
    
    # Priority 1: DRESS + TOP (if both exist)
    if best_dress and best_top:
        best_2 = [best_dress, best_top]
    
    # Priority 2: DRESS + BOTTOM (if DRESS exists but no TOP)
    elif best_dress and best_bottom:
        best_2 = [best_dress, best_bottom]
    
    # Priority 3: TOP + BOTTOM (if no DRESS)
    elif best_top and best_bottom:
        best_2 = [best_top, best_bottom]
    
    # Priority 4: If only one group has votes, take top 2 from that group
    elif best_dress and len(grouped_votes["DRESS"]) >= 2:
        best_2 = grouped_votes["DRESS"][:2]
    elif best_top and len(grouped_votes["TOP"]) >= 2:
        best_2 = grouped_votes["TOP"][:2]
    elif best_bottom and len(grouped_votes["BOTTOM"]) >= 2:
        best_2 = grouped_votes["BOTTOM"][:2]
    
    # Convert to (class_name, group, votes) format
    result = []
    for class_name, votes in best_2:
        group = get_clothing_group(class_name)
        result.append((class_name, group, votes))
    
    return result
# ==========================================

# ── Parse arguments
parser = argparse.ArgumentParser(description="Pipeline Test")
parser.add_argument("--bg",      action="store_true", help="รันแบบ background (ไม่มีหน้าต่าง)")
parser.add_argument("--results", action="store_true", help="ดูสรุปผลใน DB แล้วออก")
parser.add_argument("--phase",   type=int, default=PHASE, help="Phase 1/2/3")
parser.add_argument("--tracker", type=str, default="bytetrack",
                    choices=["deepsort", "bytetrack", "botsort", "boxmot"],
                    help="Tracking algorithm: deepsort | bytetrack | botsort | boxmot")
parser.add_argument("--debug",   action="store_true",
                    help="แสดง raw detection ทั้งหมดก่อน filter (ช่วย diagnose)")
parser.add_argument("--conf",    type=float, default=CONF_THRESH, help="Confidence threshold (default: 0.20)")
parser.add_argument("--min-w",   type=int,   default=MIN_BOX_W,   help="Min box width px (default: 0)")
parser.add_argument("--min-h",   type=int,   default=MIN_BOX_H,   help="Min box height px (default: 0)")
parser.add_argument("--skip",    type=int,   default=FRAME_SKIP,  help="Process every N frames (default: 2)")
args = parser.parse_args()

PHASE        = args.phase
TRACKER_NAME = args.tracker
SHOW_WINDOW  = not args.bg
CONF_THRESH  = args.conf
MIN_BOX_W    = args.min_w
MIN_BOX_H    = args.min_h
DEBUG        = args.debug
FRAME_SKIP   = max(1, args.skip)

# ── เพิ่ม src root ลง path
_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../"))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)


# ==========================================
# MODE: --results  →  แสดงผลจาก DB แล้วออก
# ==========================================
if args.results:
    print("\n" + "="*55)
    print("  📊 PIPELINE RESULTS — สรุปผลจากฐานข้อมูล")
    print("="*55)
    try:
        from src.services.database import DatabaseService
        db = DatabaseService()
        with db.conn.cursor() as cur:
            # สรุปจำนวนตามประเภทเสื้อผ้า
            cur.execute("""
                SELECT class_name, COUNT(*) as cnt
                FROM detections
                WHERE camera_id = %s
                GROUP BY class_name
                ORDER BY cnt DESC
            """, (CAMERA_ID,))
            rows = cur.fetchall()
            if not rows:
                print(f"\n  ⚠️ ยังไม่มีข้อมูลสำหรับ CAMERA_ID='{CAMERA_ID}'")
            else:
                print(f"\n  Camera: {CAMERA_ID}")
                print(f"  {'Class':<25} {'Count':>6}")
                print(f"  {'-'*33}")
                for cls, cnt in rows:
                    print(f"  {str(cls):<25} {cnt:>6}")

            # 10 รายการล่าสุด
            cur.execute("""
                SELECT track_id, class_name, timestamp, image_path
                FROM detections
                WHERE camera_id = %s
                ORDER BY timestamp DESC
                LIMIT 10
            """, (CAMERA_ID,))
            recent = cur.fetchall()
            if recent:
                print(f"\n  {'ล่าสุด 10 รายการ'}")
                print(f"  {'ID':>6}  {'Class':<22}  {'Time'}")
                print(f"  {'-'*50}")
                for tid, cls, ts, img in recent:
                    print(f"  {str(tid):>6}  {str(cls):<22}  {ts}")
        db.close()
    except Exception as e:
        print(f"\n  ❌ ไม่สามารถเชื่อมต่อ DB: {e}")
        print("     ตรวจสอบไฟล์ .env (DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASS)")
    print("="*55 + "\n")
    sys.exit(0)


# ==========================================
# DRAWING HELPERS
# ==========================================
COLORS = {
    "bbox":  (0, 220, 60),
    "track": (50, 180, 255),
    "cloth": (255, 160, 40),
}

def draw_bbox(frame, x1, y1, x2, y2, label: str, color):
    cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
    (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 2)
    ty = max(y1 - 8, th + 4)
    cv2.rectangle(frame, (x1, ty - th - 4), (x1 + tw + 4, ty + 2), color, -1)
    cv2.putText(frame, label, (x1 + 2, ty - 2),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)

def draw_hud(frame, mode_label: str, phase: int, fps: float, count: int):
    """Draw HUD overlay with FPS control indicator and GPU memory usage"""
    h, w = frame.shape[:2]
    
    # Position HUD in top-right corner to avoid conflicts with detections
    hud_width = 460
    hud_height = 140
    start_x = w - hud_width - 10
    start_y = 10
    
    # Create a semi-transparent overlay
    overlay = frame.copy()
    
    # Draw background with border for better visibility
    cv2.rectangle(overlay, (start_x-2, start_y-2), (start_x + hud_width+2, start_y + hud_height+2), (255, 255, 255), 2)
    cv2.rectangle(overlay, (start_x, start_y), (start_x + hud_width, start_y + hud_height), (0, 0, 0), -1)
    
    # Text settings
    font = cv2.FONT_HERSHEY_SIMPLEX
    font_scale = 0.6
    thickness = 2
    
    # FPS color indicator (red if too high)
    fps_color = (0, 0, 255) if fps > 35 else (0, 255, 0)  # Red if > 35 FPS
    
    # Get GPU memory info if available
    gpu_mem_text = "GPU: N/A"
    gpu_mem_color = (255, 255, 255)
    if torch.cuda.is_available():
        try:
            allocated = torch.cuda.memory_allocated(0) / 1024**3  # GB
            total = torch.cuda.get_device_properties(0).total_memory / 1024**3  # GB
            usage_percent = (allocated / total) * 100
            gpu_mem_text = f"GPU: {allocated:.2f}GB/{total:.1f}GB ({usage_percent:.0f}%)"
            
            # Color coding for GPU memory usage
            if usage_percent > 80:
                gpu_mem_color = (0, 0, 255)  # Red for high usage
            elif usage_percent > 60:
                gpu_mem_color = (0, 165, 255)  # Orange for medium usage
            else:
                gpu_mem_color = (0, 255, 0)  # Green for low usage
        except Exception:
            gpu_mem_text = "GPU: Error"
            gpu_mem_color = (0, 0, 255)
    
    # Display info with better formatting
    texts = [
        (f"Mode: {mode_label}", (0, 255, 0)),
        (f"Phase: {phase}", (0, 255, 0)),
        (f"FPS: {fps:.1f}", fps_color),
        (f"Target: 30 FPS", (255, 255, 0)),
        (f"People: {count}", (0, 255, 0)),
        (gpu_mem_text, gpu_mem_color)
    ]
    
    for i, (text, color) in enumerate(texts):
        y_pos = start_y + 20 + i * 18
        cv2.putText(overlay, text, (start_x + 8, y_pos), font, font_scale, color, thickness, cv2.LINE_AA)
    
    # Blend overlay with higher transparency for better visibility
    alpha = 0.85
    result = cv2.addWeighted(overlay, alpha, frame, 1 - alpha, 0)
    
    # Debug: Print HUD info to console every 30 frames
    if hasattr(draw_hud, 'frame_counter'):
        draw_hud.frame_counter += 1
    else:
        draw_hud.frame_counter = 1
    
    if draw_hud.frame_counter % 30 == 0:
        print(f"🔍 HUD Debug: FPS={fps:.1f}, People={count}, GPU={gpu_mem_text}")
    
    return result


# ==========================================
# LOAD COMPONENTS
# ==========================================
mode_label = "BG" if args.bg else "VISUAL"
print(f"\n{'='*55}")
print(f"  🚀 Pipeline Test | Phase {PHASE} | Tracker: {TRACKER_NAME.upper()} | Mode: {mode_label.upper()}")
print(f"{'='*55}\n")

device = "cuda" if torch.cuda.is_available() else "cpu"
print(f"📦 Device: {device.upper()}")

# ตรวจสอบ GPU ที่มีจริง
if torch.cuda.is_available():
    print(f"🎮 GPU Available: {torch.cuda.get_device_name(0) if torch.cuda.device_count() > 0 else 'Unknown'}")
    print(f"📊 GPU Memory: {torch.cuda.get_device_properties(0).total_memory / 1024**3:.1f} GB")
    print(f"🔢 CUDA Version: {torch.version.cuda}")
    
    # ตรวจสอบ GPU Memory ที่ใช้งานจริง
    try:
        torch.cuda.empty_cache()  # Clear cache first
        allocated = torch.cuda.memory_allocated(0) / 1024**3  # GB
        cached = torch.cuda.memory_reserved(0) / 1024**3    # GB
        total = torch.cuda.get_device_properties(0).total_memory / 1024**3  # GB
        
        print(f"💾 GPU Memory Usage:")
        print(f"   Allocated: {allocated:.2f} GB ({allocated/total*100:.1f}%)")
        print(f"   Cached: {cached:.2f} GB ({cached/total*100:.1f}%)")
        print(f"   Free: {total-allocated:.2f} GB ({(total-allocated)/total*100:.1f}%)")
        
        # Test GPU computation
        if allocated < 0.1:  # If very low usage, test with small tensor
            test_tensor = torch.randn(1000, 1000).cuda()
            result = torch.mm(test_tensor, test_tensor.t())
            print(f"✅ GPU Test: Computation successful ({result.shape})")
            del test_tensor, result
            torch.cuda.empty_cache()
        
    except Exception as e:
        print(f"⚠️  GPU Memory Check Error: {e}")
else:
    print("⚠️  CUDA not available - Using CPU (slower)")

from ultralytics import YOLO
yolo = YOLO(MODEL_DETECT)
yolo.to(device)
print(f"✅ [Phase 1] YOLO loaded: {MODEL_DETECT}")

# ตรวจสอบว่า YOLO อยู่บน GPU จริง
if device == "cuda":
    yolo_device = next(yolo.model.parameters()).device
    print(f"🔍 YOLO Device Check: {yolo_device}")
    if str(yolo_device) != "cuda:0":
        print("⚠️  YOLO not on GPU! Forcing to CUDA...")
        yolo.to("cuda:0")

tracker   = None
classifier = None
embedder   = None
db         = None

if PHASE >= 2:
    from src.ai.tracker import create_tracker
    tracker = create_tracker(TRACKER_NAME, max_age=30, n_init=3)
    print(f"✅ [Phase 2] Tracker ready: {TRACKER_NAME.upper()}")
    
    from src.ai.feature_extractor import ClothingEmbedder
    embedder = ClothingEmbedder(model_path=MODEL_CLOTH, device=device)
    print(f"✅ [Phase 2] ClothingEmbedder ready")
    
    # ตรวจสอบว่า Embedder อยู่บน GPU จริง
    if device == "cuda" and hasattr(embedder, 'model'):
        try:
            embedder_device = next(embedder.model.parameters()).device
            print(f"🔍 Embedder Device Check: {embedder_device}")
            if str(embedder_device) != "cuda:0":
                print("⚠️  Embedder not on GPU! Forcing to CUDA...")
                embedder.model.to("cuda:0")
                embedder.reid_model.to("cuda:0")
        except Exception as e:
            print(f"⚠️  Cannot check embedder device: {e}")

if PHASE >= 3:
    from src.ai.classifier import ClothingClassifier
    from src.ai.color_analysis import analyze_color_groups_hsl
    classifier = ClothingClassifier(model_path=MODEL_CLOTH)
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    print(f"✅ [Phase 3] ClothingClassifier & ColorAnalysis ready")

    # DB — ลอง connect แต่ไม่ crash ถ้าไม่มี
    try:
        from src.services.database import DatabaseService
        db = DatabaseService()
        print(f"✅ [Phase 3] Database connected")
    except Exception as e:
        print(f"⚠️ [Phase 3] DB unavailable → บันทึกแค่รูปภาพ: {e}")
        db = None


# ==========================================
# OPEN VIDEO SOURCE  (รองรับ YouTube URL)
# ==========================================
import re
_YT_PATTERN = re.compile(r'(https?://)?(www\.)?(youtube|youtu|youtube-nocookie)\.(com|be)/')

_resolved_source = SOURCE
if isinstance(SOURCE, str) and _YT_PATTERN.search(SOURCE):
    print(f"🔗 YouTube URL detected — resolving stream via yt-dlp...")
    try:
        import yt_dlp
        _ydl_opts = {
            "format": "best[ext=mp4]/best",
            "quiet": True,
            "no_warnings": True,
        }
        with yt_dlp.YoutubeDL(_ydl_opts) as ydl:
            _info = ydl.extract_info(SOURCE, download=False)
            _resolved_source = _info.get("url", SOURCE)
        print(f"✅ Stream resolved successfully")
        # Set FFmpeg options for streaming
        os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = (
            "http_persistent;0|reconnect;1|reconnect_at_eof;1"
            "|reconnect_streamed;1|reconnect_delay_max;5|timeout;10000000"
        )
    except Exception as e:
        print(f"❌ yt-dlp failed: {e}")
        sys.exit(1)

cap = cv2.VideoCapture(_resolved_source)
if not cap.isOpened():
    print(f"❌ ไม่สามารถเปิด source: {SOURCE}")
    sys.exit(1)

print(f"\n▶️  เริ่ม (source={SOURCE})  |  {'กด Q เพื่อออก' if SHOW_WINDOW else 'กด Ctrl+C เพื่อหยุด'}\n")

# ── แสดงข้อมูล Video Source
try:
    import cv2
    cap_check = cv2.VideoCapture(SOURCE)
    if cap_check.isOpened():
        fps = cap_check.get(cv2.CAP_PROP_FPS)
        width = int(cap_check.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap_check.get(cv2.CAP_PROP_FRAME_HEIGHT))
        total_frames = int(cap_check.get(cv2.CAP_PROP_FRAME_COUNT))
        duration = total_frames / fps if fps > 0 else 0
        
        print(f"📹 Video Information:")
        print(f"   FPS: {fps:.2f}")
        print(f"   Resolution: {width}x{height}")
        print(f"   Total Frames: {total_frames:,}")
        print(f"   Duration: {duration:.2f}s ({duration/60:.2f} min)")
        print(f"   File Size: {os.path.getsize(SOURCE) / (1024*1024):.2f} MB")
        print()
        cap_check.release()
    else:
        print(f"⚠️  Cannot open video source for info: {SOURCE}")
except Exception as e:
    print(f"⚠️  Error getting video info: {e}")
print()

# State Tracking
analyzed_ids: dict = {}  # track_id → list of [(class_name, group, votes), ...]
cloth_votes: dict = {}   # track_id → {"class_name": count} สำหรับโหวตหาชุดที่เจอเยอะสุด
db_batch    : list = []
BATCH_SIZE  = 5

prev_time  = time.time()
frame_num  = 0
last_draw_data = []  # เก็บข้อมูลวาดกล่องของเฟรมล่าสุด (สำหรับเฟรมที่โดน skip)
last_embeds = {}     # เก็บ embedding ล่าสุดของแต่ละ track_id (reuse ถ้าไม่ต้องสกัดใหม่)
save_queue = []      # Queue สำหรับบันทึกรูปแบบ async



# ==========================================
# def flush_db_batch — บันทึก batch ลง DB
# ==========================================
def flush_db_batch():
    global db_batch
    if db and db_batch:
        db.insert_detections_batch(db_batch)
        db_batch = []


# ==========================================
# MAIN LOOP
# ==========================================
try:
    while True:
        ret, frame = cap.read()
        if not ret:
            print("⚠️ วิดีโอจบ หรืออ่านเฟรมไม่ได้")
            break

        now = time.time()
        fps = 1.0 / (now - prev_time + 1e-9)
        prev_time = now
        frame_num += 1

        people_count = 0
        display = frame.copy() if SHOW_WINDOW else None

        # ── ข้าม frame ที่ไม่ใช่รอบ process (แสดงผลแต่ไม่ detect)
        if frame_num % FRAME_SKIP != 0:
            if SHOW_WINDOW and display is not None:
                # วาดกล่องของเฟรมก่อนหน้าค้างไว้ (ลดการกะพริบ)
                for draw_fn, args_tuple in last_draw_data:
                    draw_fn(display, *args_tuple)
                draw_hud(display, mode_label, PHASE, fps, people_count)
                cv2.imshow(f"Pipeline | Phase {PHASE}", display)
                if cv2.waitKey(1) & 0xFF == ord("q"):
                    print("⏹️  ผู้ใช้กด Q หยุดการทำงาน")
                    break
            continue

        # เคลียร์ข้อมูลวาดกล่องสำหรับเฟรมใหม่
        last_draw_data.clear()

        # ──────────────────────────────────────────────
        # PHASE 1 — Detection Only
        # ──────────────────────────────────────────────
        if PHASE == 1:
            results = yolo(frame, classes=[0], conf=CONF_THRESH, verbose=False, device=device)
            for box in (results[0].boxes or []):
                x1, y1, x2, y2 = map(int, box.xyxy[0])
                w, h = x2-x1, y2-y1
                conf_val = float(box.conf[0])

                # Debug: แสดงขนาด box (สีแดง)
                if DEBUG and SHOW_WINDOW:
                    cv2.rectangle(display, (x1,y1), (x2,y2), (0,0,200), 1)
                    cv2.putText(display, f"{conf_val:.2f} {w}x{h}",
                                (x1, max(y1-4,10)), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0,0,255), 1)

                people_count += 1
                if SHOW_WINDOW:
                    args_tuple = (x1, y1, x2, y2, f"Person {conf_val:.2f}", COLORS["bbox"])
                    draw_bbox(display, *args_tuple)
                    last_draw_data.append((draw_bbox, args_tuple))

        # ──────────────────────────────────────────────
        # PHASE 2 & 3 — Tracking with Custom Feature Extractor
        # ──────────────────────────────────────────────
        elif PHASE in [2, 3]:
            # 1. Detection
            results = yolo(frame, classes=[0], conf=CONF_THRESH, verbose=False, device=device)
            boxes_list = []
            embeds_list = []
            cloth_labels_list = []
            
            should_extract_embeds = (frame_num // FRAME_SKIP) % EMBED_EVERY_N == 0
            
            if results and results[0].boxes:
                # เก็บ crops ไว้ batch process
                crops_to_process = []
                box_indices = []
                
                for idx, box in enumerate(results[0].boxes):
                    x1, y1, x2, y2 = map(int, box.xyxy[0])
                    c = float(box.conf[0])
                    cls_id = int(box.cls[0])
                    
                    emb = None
                    cloth_label = "Unknown"
                    
                    if embedder is not None and should_extract_embeds:
                        crop = frame[max(y1,0):y2, max(x1,0):x2]
                        if crop.size > 0:
                            crops_to_process.append(crop)
                            box_indices.append(idx)
                    
                    boxes_list.append([x1, y1, x2, y2, c, cls_id])
                    embeds_list.append(emb)  # จะอัปเดตทีหลังถ้ามีการสกัด
                    cloth_labels_list.append(cloth_label)
                
                # Batch process embeddings ถ้ามี crops
                if crops_to_process and should_extract_embeds:
                    batch_results = embedder.get_embeddings_batch(crops_to_process)
                    for i, (emb, labels) in enumerate(batch_results):
                        box_idx = box_indices[i]
                        embeds_list[box_idx] = emb
                        if labels and labels != ["Unknown"]:
                            # Limit to top 2 classes from feature extractor
                            top_2_labels = labels[:2] if len(labels) > 2 else labels
                            cloth_labels_list[box_idx] = " + ".join(top_2_labels)
                
                # Pad None embeddings with zeros (768-dim) to maintain consistency for tracker
                import numpy as np
                for i in range(len(embeds_list)):
                    if embeds_list[i] is None:
                        embeds_list[i] = np.zeros(768, dtype=np.float32)


            # 2. Tracking with Custom Embeddings
            tracks = tracker.update(frame, yolo, device, CONF_THRESH, [0], embeds=embeds_list, boxes_list=boxes_list)
            
            for t in tracks:
                x1, y1, x2, y2 = t["bbox"]
                tid = t["track_id"]
                people_count += 1
                
                # แมตช์ข้ามกล่อง Tracking ให้เชื่อมกับกล่อง Detection (ด้วย Center Distance) เพื่อดึงชื่อเสื้อผ้า
                best_label = "Unknown"
                if cloth_labels_list:
                    tx, ty = (x1+x2)/2, (y1+y2)/2
                    best_dist = 999999
                    for i, b in enumerate(boxes_list):
                        bx, by = (b[0]+b[2])/2, (b[1]+b[3])/2
                        dist = (tx-bx)**2 + (ty-by)**2
                        if dist < best_dist and dist < 10000:
                            best_dist = dist
                            best_label = cloth_labels_list[i]
                            
                cls_label = best_label
                
                # ── ระบบโหวต (Voting System) ใช้กับทุก Phase เพื่อความเสถียร ──
                # 1. ถ้ายังได้ Unknown ให้ลองใช้ Classifier ตัวเก่าช่วยทาย (ถ้ามี)
                if cls_label == "Unknown" and classifier is not None:
                    crop = frame[max(y1,0):y2, max(x1,0):x2]
                    if crop.size > 0:
                        cls_label, conf_cls, _ = classifier.predict(crop)

                # 2. บันทึกผลโหวต
                if tid not in cloth_votes:
                    cloth_votes[tid] = {}
                    
                if cls_label != "Unknown":
                    cloth_votes[tid][cls_label] = cloth_votes[tid].get(cls_label, 0) + 1
                    
                # 3. หา best 2 จากคนละกลุ่ม (Dress/Top/Bottom)
                best_2_results = get_best_2_from_different_groups(cloth_votes[tid])
                
                # Update analyzed_ids with best 2 from different groups
                analyzed_ids[tid] = best_2_results
                
                # Use the top class for display and processing
                class_name = best_2_results[0][0] if best_2_results else "Unknown"
                primary_group = best_2_results[0][1] if best_2_results else "UNKNOWN"
                # ───────────────────────────────────────────────────────
                
                if PHASE == 2:
                    if SHOW_WINDOW:
                        color = COLORS["track"] if class_name == "Unknown" else COLORS["cloth"]
                        # Display best 2 from different groups
                        display_text = f"ID:{tid} [{class_name}({primary_group})]"
                        if len(best_2_results) > 1:
                            second_class, second_group, _ = best_2_results[1]
                            display_text += f" | {second_class}({second_group})"
                        args_tuple = (x1, y1, x2, y2, display_text, color)
                        draw_bbox(display, *args_tuple)
                        last_draw_data.append((draw_bbox, args_tuple))
                        
                elif PHASE == 3:
                    # ── Queue บันทึกรูปภาพ (async)
                    # Use top class for folder name
                    out_folder = os.path.join(OUTPUT_DIR, class_name)
                    os.makedirs(out_folder, exist_ok=True)
                    ts = int(time.time() * 1000)
                    img_path = os.path.join(out_folder, f"id{tid}_{ts}.jpg")
                    crop_save = frame[max(y1,0):y2, max(x1,0):x2]
                    
                    # ส่งไป queue แทนการบันทึกตรงนี้
                    if crop_save.size > 0:
                        save_queue.append((crop_save.copy(), img_path, tid, best_2_results, CAMERA_ID, 
                                         analyzed_ids.get(tid, [("Unknown", "UNKNOWN", 0)])))
                    
                    color_result = {}  # ข้าม color analysis เพื่อความเร็ว (optional)
                    # ถ้าต้องการ color ให้เปิดบรรทัดล่าง (ช้าลง)
                    # color_result = analyze_color_groups_hsl(crop_save)

                    # Save both best classes in database
                    secondary_class = None
                    secondary_group = None
                    if len(best_2_results) > 1:
                        secondary_class, secondary_group, _ = best_2_results[1]
                    
                    db_batch.append({
                        "camera_id":   CAMERA_ID,
                        "track_id":    tid,
                        "class_name":  class_name,
                        "group":       primary_group,
                        "secondary_class": secondary_class,
                        "secondary_group": secondary_group,
                        "category":    primary_group,     
                        "color_profile": color_result,
                        "image_path":  img_path,
                    })
                    if len(db_batch) >= BATCH_SIZE:
                        flush_db_batch()

                    # Display with best 2 from different groups
                    display_text = f"📸 ID:{tid} → {class_name}({primary_group})"
                    if secondary_class:
                        display_text += f" | {secondary_class}({secondary_group})"
                    display_text += " (Tracked)"
                    print(display_text)

                    if SHOW_WINDOW:
                        color = COLORS["cloth"] if class_name != "Unknown" else COLORS["track"]
                        p_color = color_result.get("primary_color", "")
                        disp_color = f"[{p_color}]" if p_color and p_color != "unknown" else ""
                        # Show both classes with groups in display
                        bbox_text = f"ID:{tid} | {class_name}({primary_group})"
                        if secondary_class:
                            bbox_text += f" | {secondary_class}({secondary_group})"
                        bbox_text += f" {disp_color}"
                        args_tuple = (x1, y1, x2, y2, bbox_text, color)
                        draw_bbox(display, *args_tuple)
                        last_draw_data.append((draw_bbox, args_tuple))

        # ── ประมวลผล save queue (บันทึกรูปที่ค้างไว้)
        if save_queue:
            for _ in range(min(3, len(save_queue))):  # บันทึกสูงสุด 3 รูปต่อเฟรม
                crop, path, _, _, _, _ = save_queue.pop(0)
                cv2.imwrite(path, crop)

        if args.bg and (int(time.time() * 10) % 30 == 0):
            print(f"⏳ Running... FPS:{fps:.1f} | People:{people_count} | IDs seen:{len(analyzed_ids)}")

        # ── Visual mode: แสดงหน้าต่าง
        if SHOW_WINDOW and display is not None:
            draw_hud(display, mode_label, PHASE, fps, people_count)
            cv2.imshow(f"Pipeline | Phase {PHASE}", display)
            
            # ลด FPS และเพิ่ม delay เพื่อให้ภาพลื่นขึ้น
            key = cv2.waitKey(1) & 0xFF
            
            # ควบคุม FPS ไม่ให้สูงเกินไป (จำกัดไว้ ~30 FPS)
            frame_time = time.time() - prev_time
            min_frame_time = 1.0 / 30.0  # 30 FPS = 33.33ms per frame
            
            if frame_time < min_frame_time:
                sleep_time = (min_frame_time - frame_time) * 1000  # Convert to milliseconds
                cv2.waitKey(int(sleep_time))
            
            if key == ord("q"):
                print("⏹️  ผู้ใช้กด Q หยุดการทำงาน")
                break

except KeyboardInterrupt:
    print("\n⏹️  Ctrl+C — หยุดการทำงาน")


# ==========================================
# CLEANUP
# ==========================================
flush_db_batch()  # flush ที่เหลือ
cap.release()
if SHOW_WINDOW:
    cv2.destroyAllWindows()
if db:
    db.close()

if PHASE >= 2:
    print(f"\n📊 สรุปประวัติการโหวตจาก Tracking (Best 2 from Different Groups):")
    print(f"   Unique IDs ที่เจอ: {len(analyzed_ids)}")
    for tid, best_2_results in analyzed_ids.items():
        votes = cloth_votes.get(tid, {})
        vote_str = ", ".join([f"{k}({v})" for k, v in dict(sorted(votes.items(), key=lambda item: item[1], reverse=True)).items()])
        
        # Display best 2 from different groups
        if best_2_results:
            display_parts = []
            for class_name, group, _ in best_2_results:
                if class_name != "Unknown":
                    display_parts.append(f"{class_name}({group})")
            
            if display_parts:
                display_text = " | ".join(display_parts)
            else:
                display_text = "Unknown"
        else:
            display_text = "Unknown"
            
        print(f"   ID {tid:>4} → {display_text}  [ประวัติโหวต: {vote_str}]")
        
if PHASE == 3:
    print(f"   รูปบันทึกที่: {os.path.abspath(OUTPUT_DIR)}/")
    print(f"\n   ดูผลใน DB ด้วย: python pipeline_test.py --results")

print("\n✅ เสร็จสิ้น!")
