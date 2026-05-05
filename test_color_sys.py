import cv2
import numpy as np
import os
import torch
from ultralytics import YOLO

# เพื่อให้สามารถรันจากโปรเจ็กต์ Root แล้ว Import ได้ถูกต้อง
import sys
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from src.ai.classifier import ClothingClassifier
from src.ai.color_analysis_unified import analyze_person_colors

# ==========================================
# ⚙️ตั้งค่าภาพที่ต้องการทดสอบตรงนี้
# ==========================================
IMAGE_PATH = r"C:\Users\pmach\Downloads\clothing_me.yolov11\train\images\brave_screenshot_www-youtube-com (5)_png.rf.1zlBvoNAAw1SqWSNleac.png" # <--- เปลี่ยน Path รูปภาพตามต้องการ
# ==========================================

def overlay_rgba(background, overlay_rgba, x, y):
    """
    วาง overlay (RGBA) ลงบน background (BGR) ตรงตำแหน่ง x, y
    """
    h, w = overlay_rgba.shape[:2]
    bg_h, bg_w = background.shape[:2]
    
    y1, y2 = max(0, y), min(bg_h, y + h)
    x1, x2 = max(0, x), min(bg_w, x + w)
    
    y1_o, y2_o = max(0, -y), min(h, bg_h - y)
    x1_o, x2_o = max(0, -x), min(w, bg_w - x)
    
    if y1 >= y2 or x1 >= x2 or y1_o >= y2_o or x1_o >= x2_o:
        return background

    overlay_rgb = overlay_rgba[y1_o:y2_o, x1_o:x2_o, :3]
    alpha = overlay_rgba[y1_o:y2_o, x1_o:x2_o, 3] / 255.0
    
    for c in range(3):
        background[y1:y2, x1:x2, c] = (alpha * overlay_rgb[:, :, c] +
                                       (1 - alpha) * background[y1:y2, x1:x2, c])
    return background

def main():
    if not os.path.exists(IMAGE_PATH):
        print(f"❌ ไม่พบไฟล์ภาพ: {IMAGE_PATH}")
        print("💡 โปรดตั้งค่าตัวแปร IMAGE_PATH ในโค้ดให้ตรงกับไฟล์ที่ต้องการทดสอบ")
        return

    print(f"🖼️ กำลังโหลดภาพ: {IMAGE_PATH}")
    img = cv2.imread(IMAGE_PATH)
    if img is None:
        print("❌ โหลดภาพล้มเหลว")
        return

    # ขยายรูปต้นฉบับก่อนประมวลผล เพื่อให้การวาดกรอบและตัวหนังสือคมชัดขึ้น
    # เนื่องจากถ้ารูปต้นฉบับเล็กเกินไป ตัวหนังสือจะบังรูปหมด
    source_scale = 3.0  # ปรับสเกลขยายรูปต้นฉบับตรงนี้ (เช่น 3.0 = ขยาย 3 เท่า)
    if source_scale != 1.0:
        h, w = img.shape[:2]
        img = cv2.resize(img, (int(w * source_scale), int(h * source_scale)))

    display_img = img.copy()
    map_overlay_img = img.copy()

    print("👕 กำลังโหลดโมเดลและค้นหาเสื้อผ้า...")
    classifier = ClothingClassifier('models/clothing_classifier.pt')
    if classifier.model is None:
        print("❌ โหลดโมเดลไม่สำเร็จ โปรดตรวจสอบ Path ของ Model")
        return

    # รันโมเดลบนภาพเต็มเพื่อหาว่ามีเสื้อผ้าชิ้นไหนอยู่ตำแหน่งใดบ้าง
    results = classifier.model(img, verbose=False, device=classifier.device)
    
    if not results or not results[0].boxes:
        print("⚠️ ไม่พบเสื้อผ้าใดๆ ในภาพ")
    else:
        boxes = results[0].boxes
        names = results[0].names
        
        for box in boxes:
            x1, y1, x2, y2 = map(int, box.xyxy[0].tolist())
            cls_id = int(box.cls.item())
            class_name = names[cls_id]
            conf = box.conf.item()
            
            if conf < 0.3:
                continue

            crop = img[y1:y2, x1:x2]
            if crop.size == 0:
                continue
            
            print(f"🔍 พบ: {class_name} ({conf*100:.1f}%) กำลังวิเคราะห์สี...")
            
            # เรียกใช้ระบบสีใหม่ (63 สี + 22 กลุ่ม)
            color_results = analyze_person_colors(crop, class_name, embedder=None)
            
            # หา dominant color (สีที่เปอร์เซ็นต์เยอะสุด)
            dominant_color = color_results.get("primary_detailed_color", "unknown")
            primary_tone = color_results.get("primary_tone_group", "unknown")
            display_label = f"{dominant_color} {class_name}"
            print(f"🎨 ได้สีหลัก: {dominant_color} (โทน: {primary_tone})")
            
            print("📋 สีละเอียดทั้งหมด (Top 10):")
            detailed_colors = color_results.get("detailed_colors", {})
            for color_name, pct in sorted(detailed_colors.items(), key=lambda item: item[1], reverse=True)[:10]:
                print(f"   - {color_name}: {pct}%")
            
            print("📋 กลุ่มสีทั้งหมด:")
            color_groups = color_results.get("color_groups", {})
            for group_name, pct in sorted(color_groups.items(), key=lambda item: item[1], reverse=True):
                print(f"   - {group_name}: {pct}%")
            
            profile_texts = []
            for color_name, pct in sorted(detailed_colors.items(), key=lambda item: item[1], reverse=True)[:5]:
                profile_texts.append(f"{color_name}: {pct}%")
            
            # --------- วาดภาพด้านซ้าย (แสดงผลลัพธ์การจัดการเสื้อผ้า + ข้อความสี) ---------
            cv2.rectangle(display_img, (x1, y1), (x2, y2), (0, 255, 0), 2)
            cv2.rectangle(display_img, (x1, y1 - 30), (x2, y1), (0, 255, 0), -1)
            cv2.putText(display_img, f"{display_label} {conf:.2f}", (x1 + 5, y1 - 10), 
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 0), 2)
            
            y_offset = y2 + 20
            for text in profile_texts:
                cv2.putText(display_img, text, (x1, y_offset), 
                            cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)
                y_offset += 25

    # ใช้เฉพาะภาพ display เพราะระบบใหม่ไม่มี color map
    combined_img = display_img

    h, w = combined_img.shape[:2]
    
    # ขยายขนาดภาพ (w, h) ขึ้น เช่น 1.5 เท่า
    scale_factor = 1.5
    new_w = int(w * scale_factor)
    new_h = int(h * scale_factor)
    
    # กำหนดความสูงสูงสุด (ป้องกันไม่ให้ล้นจอเกินไป)
    max_height = 1000
    if new_h > max_height:
        true_scale = max_height / h
        new_w = int(w * true_scale)
        new_h = max_height

    combined_img = cv2.resize(combined_img, (new_w, new_h))

    print("✅ วิเคราะห์เสร็จสิ้น! หากภาพปรากฏขึ้น กดปุ่มใดๆ ในหน้าต่างภาพเพื่อปิด")
    window_name = "Color Analysis (63 Colors + 22 Groups)"
    cv2.namedWindow(window_name, cv2.WINDOW_NORMAL) # อนุญาตให้ขยาย/ย่อหน้าต่างได้
    cv2.imshow(window_name, combined_img)
    cv2.waitKey(0)
    cv2.destroyAllWindows()

if __name__ == "__main__":
    main()
