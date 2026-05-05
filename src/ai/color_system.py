#!/usr/bin/env python3
"""
ระบบสีละเอียดและการจัดกลุ่มสี
Detailed Color System with Grouping for Tracking and Search
"""

import cv2
import numpy as np
import warnings

# ปิด warning ของ rembg ถ้ามี
warnings.filterwarnings("ignore")

try:
    from rembg import remove
    REMBG_AVAILABLE = True
except ImportError:
    REMBG_AVAILABLE = False

# ============================================
# 🎨 ระบบสีละเอียด (Detailed Colors) - สำหรับ Tracking
# ============================================

# ช่วงสีละเอียดใน HSV Space (H: 0-179, S: 0-255, V: 0-255)
DETAILED_COLOR_RANGES = {
    # 🔴 Red shades
    "red": {
        "h_range": (0, 10),
        "s_range": (100, 255),
        "v_range": (50, 255)
    },
    "dark_red": {
        "h_range": (0, 10),
        "s_range": (50, 255),
        "v_range": (20, 80)
    },
    "crimson": {
        "h_range": (0, 8),
        "s_range": (150, 255),
        "v_range": (80, 180)
    },
    "scarlet": {
        "h_range": (0, 8),
        "s_range": (200, 255),
        "v_range": (150, 255)
    },
    "maroon": {
        "h_range": (0, 10),
        "s_range": (100, 200),
        "v_range": (30, 90)
    },
    
    # 🟠 Orange shades
    "orange": {
        "h_range": (10, 25),
        "s_range": (100, 255),
        "v_range": (80, 255)
    },
    "dark_orange": {
        "h_range": (10, 25),
        "s_range": (100, 255),
        "v_range": (50, 120)
    },
    "amber": {
        "h_range": (20, 35),
        "s_range": (150, 255),
        "v_range": (150, 255)
    },
    "peach": {
        "h_range": (8, 20),
        "s_range": (50, 150),
        "v_range": (180, 255)
    },
    "coral": {
        "h_range": (8, 15),
        "s_range": (150, 255),
        "v_range": (180, 255)
    },
    
    # 🟡 Yellow shades
    "yellow": {
        "h_range": (20, 40),
        "s_range": (100, 255),
        "v_range": (150, 255)
    },
    "gold": {
        "h_range": (25, 40),
        "s_range": (150, 255),
        "v_range": (150, 220)
    },
    "light_yellow": {
        "h_range": (20, 40),
        "s_range": (30, 100),
        "v_range": (200, 255)
    },
    "mustard": {
        "h_range": (25, 40),
        "s_range": (100, 200),
        "v_range": (100, 180)
    },
    "khaki": {
        "h_range": (20, 35),
        "s_range": (30, 100),
        "v_range": (150, 220)
    },
    
    # 🟢 Green shades
    "green": {
        "h_range": (35, 85),
        "s_range": (50, 255),
        "v_range": (50, 255)
    },
    "dark_green": {
        "h_range": (35, 85),
        "s_range": (50, 255),
        "v_range": (20, 80)
    },
    "light_green": {
        "h_range": (35, 85),
        "s_range": (30, 150),
        "v_range": (150, 255)
    },
    "olive": {
        "h_range": (35, 65),
        "s_range": (30, 100),
        "v_range": (50, 150)
    },
    "lime": {
        "h_range": (35, 55),
        "s_range": (150, 255),
        "v_range": (150, 255)
    },
    "forest_green": {
        "h_range": (40, 70),
        "s_range": (80, 200),
        "v_range": (30, 100)
    },
    "mint": {
        "h_range": (70, 85),
        "s_range": (30, 100),
        "v_range": (180, 255)
    },
    "teal": {
        "h_range": (75, 95),
        "s_range": (100, 255),
        "v_range": (80, 180)
    },
    
    # 🔵 Blue shades
    "blue": {
        "h_range": (85, 135),
        "s_range": (50, 255),
        "v_range": (50, 255)
    },
    "dark_blue": {
        "h_range": (85, 135),
        "s_range": (50, 255),
        "v_range": (20, 80)
    },
    "light_blue": {
        "h_range": (85, 135),
        "s_range": (30, 150),
        "v_range": (180, 255)
    },
    "navy": {
        "h_range": (95, 125),
        "s_range": (100, 255),
        "v_range": (20, 70)
    },
    "sky_blue": {
        "h_range": (85, 105),
        "s_range": (100, 200),
        "v_range": (180, 255)
    },
    "royal_blue": {
        "h_range": (100, 120),
        "s_range": (150, 255),
        "v_range": (80, 180)
    },
    "cobalt": {
        "h_range": (105, 125),
        "s_range": (150, 255),
        "v_range": (100, 200)
    },
    "turquoise": {
        "h_range": (80, 100),
        "s_range": (100, 200),
        "v_range": (150, 255)
    },
    
    # 🟣 Purple shades
    "purple": {
        "h_range": (125, 165),
        "s_range": (50, 255),
        "v_range": (50, 255)
    },
    "dark_purple": {
        "h_range": (125, 165),
        "s_range": (50, 255),
        "v_range": (20, 80)
    },
    "light_purple": {
        "h_range": (125, 165),
        "s_range": (30, 150),
        "v_range": (180, 255)
    },
    "violet": {
        "h_range": (130, 150),
        "s_range": (100, 255),
        "v_range": (100, 255)
    },
    "lavender": {
        "h_range": (130, 155),
        "s_range": (30, 100),
        "v_range": (180, 255)
    },
    "magenta": {
        "h_range": (145, 165),
        "s_range": (150, 255),
        "v_range": (150, 255)
    },
    "fuchsia": {
        "h_range": (150, 165),
        "s_range": (200, 255),
        "v_range": (150, 255)
    },
    "plum": {
        "h_range": (140, 160),
        "s_range": (100, 200),
        "v_range": (80, 180)
    },
    
    # 🟤 Brown shades
    "brown": {
        "h_range": (0, 25),
        "s_range": (50, 150),
        "v_range": (30, 120)
    },
    "dark_brown": {
        "h_range": (0, 25),
        "s_range": (50, 150),
        "v_range": (15, 60)
    },
    "light_brown": {
        "h_range": (0, 25),
        "s_range": (30, 100),
        "v_range": (100, 180)
    },
    "tan": {
        "h_range": (15, 35),
        "s_range": (30, 80),
        "v_range": (120, 200)
    },
    "beige": {
        "h_range": (20, 40),
        "s_range": (20, 60),
        "v_range": (180, 255)
    },
    "camel": {
        "h_range": (20, 35),
        "s_range": (40, 100),
        "v_range": (100, 180)
    },
    
    # 🩷 Pink shades
    "pink": {
        "h_range": (160, 180),
        "s_range": (50, 255),
        "v_range": (150, 255)
    },
    "light_pink": {
        "h_range": (160, 180),
        "s_range": (30, 150),
        "v_range": (200, 255)
    },
    "hot_pink": {
        "h_range": (165, 180),
        "s_range": (150, 255),
        "v_range": (150, 255)
    },
    "rose": {
        "h_range": (165, 180),
        "s_range": (100, 200),
        "v_range": (120, 200)
    },
    "salmon": {
        "h_range": (0, 15),
        "s_range": (100, 200),
        "v_range": (150, 255)
    },
    
    # ⚫⚪ Gray/Black/White shades
    "black": {
        "h_range": (0, 180),
        "s_range": (0, 50),
        "v_range": (0, 40)
    },
    "dark_gray": {
        "h_range": (0, 180),
        "s_range": (0, 30),
        "v_range": (40, 100)
    },
    "gray": {
        "h_range": (0, 180),
        "s_range": (0, 30),
        "v_range": (100, 180)
    },
    "light_gray": {
        "h_range": (0, 180),
        "s_range": (0, 30),
        "v_range": (180, 220)
    },
    "white": {
        "h_range": (0, 180),
        "s_range": (0, 30),
        "v_range": (220, 255)
    },
    "silver": {
        "h_range": (0, 180),
        "s_range": (0, 20),
        "v_range": (180, 230)
    },
}

# ============================================
# 🎯 การจัดกลุ่มสี (Color Groups) - สำหรับการค้นหา
# ============================================

COLOR_GROUPS = {
    # กลุ่มตามโทนหลัก (10 กลุ่ม - เพิ่ม white_tones, black_tones)
    "red_tones": ["red", "dark_red", "crimson", "scarlet", "maroon"],
    "orange_tones": ["orange", "dark_orange", "amber", "peach", "coral"],
    "yellow_tones": ["yellow", "gold", "light_yellow", "mustard", "khaki"],
    "green_tones": ["green", "dark_green", "light_green", "olive", "lime", "forest_green", "mint", "teal"],
    "blue_tones": ["blue", "dark_blue", "light_blue", "navy", "sky_blue", "royal_blue", "cobalt", "turquoise"],
    "purple_tones": ["purple", "dark_purple", "light_purple", "violet", "lavender", "magenta", "fuchsia", "plum"],
    "brown_tones": ["brown", "dark_brown", "light_brown", "tan", "beige", "camel"],
    "pink_tones": ["pink", "light_pink", "hot_pink", "rose", "salmon"],
    "white_tones": ["white", "light_gray", "silver", "beige"],
    "black_tones": ["black", "dark_gray"],
    
    # กลุ่มตามความสว่าง
    "light_colors": ["white", "light_gray", "silver", "light_yellow", "light_green", "light_blue", 
                      "light_purple", "light_pink", "sky_blue", "mint", "peach", "beige"],
    "dark_colors": ["black", "dark_gray", "dark_red", "dark_orange", "dark_green", "dark_blue", 
                    "dark_purple", "dark_brown", "navy", "maroon", "forest_green"],
    "medium_colors": ["gray", "red", "orange", "yellow", "green", "blue", "purple", "brown", 
                      "pink", "tan", "camel", "olive", "teal", "turquoise", "violet", "plum"],
    
    # กลุ่มตามความสดใส
    "vibrant_colors": ["red", "orange", "yellow", "green", "blue", "purple", "pink", 
                       "crimson", "scarlet", "amber", "lime", "sky_blue", "royal_blue", 
                       "cobalt", "violet", "magenta", "fuchsia", "hot_pink", "turquoise"],
    "muted_colors": ["gray", "dark_gray", "light_gray", "silver", "olive", "khaki", 
                     "tan", "beige", "camel", "maroon", "navy", "forest_green", "plum"],
    "pastel_colors": ["light_yellow", "light_green", "light_blue", "light_purple", 
                      "light_pink", "mint", "lavender", "peach", "beige"],
    
    # กลุ่มตามอุณหภูมิสี
    "warm_colors": ["red", "orange", "yellow", "pink", "crimson", "scarlet", "amber", 
                    "gold", "peach", "coral", "mustard", "khaki", "brown", "tan", 
                    "beige", "camel", "rose", "salmon", "hot_pink"],
    "cool_colors": ["green", "blue", "purple", "cyan", "teal", "turquoise", "sky_blue", 
                    "royal_blue", "cobalt", "violet", "lavender", "magenta", "fuchsia", 
                    "plum", "mint", "navy", "forest_green"],
    "neutral_colors": ["black", "white", "gray", "dark_gray", "light_gray", "silver", 
                      "beige", "tan", "camel", "khaki"],
    
    # กลุ่มสำหรับเสื้อผ้าที่พบบ่อย
    "common_shirt_colors": ["white", "black", "blue", "gray", "red", "navy", "light_blue", 
                           "pink", "purple", "green", "yellow", "orange", "brown", "beige"],
    "common_pants_colors": ["black", "blue", "gray", "dark_blue", "navy", "brown", "khaki", 
                           "dark_gray", "white", "beige"],
    "formal_colors": ["black", "white", "gray", "dark_gray", "navy", "dark_blue", "brown"],
    "casual_colors": ["blue", "green", "red", "yellow", "orange", "pink", "purple", "teal", 
                     "turquoise", "coral", "mint", "lavender"],
}

# ============================================
# 🔄 Reverse Mapping: Color -> Tone Groups (Array for ambiguous colors)
# ============================================

# Mapping from detailed colors to tone groups (array for ambiguous colors)
COLOR_TO_TONE_GROUPS = {
    # Red tones
    "red": ["red_tones"],
    "dark_red": ["red_tones"],
    "crimson": ["red_tones"],
    "scarlet": ["red_tones"],
    "maroon": ["red_tones"],
    
    # Orange tones
    "orange": ["orange_tones"],
    "dark_orange": ["orange_tones"],
    "amber": ["orange_tones"],
    "peach": ["orange_tones"],
    "coral": ["orange_tones"],
    
    # Yellow tones (with ambiguous colors)
    "yellow": ["yellow_tones"],
    "gold": ["orange_tones", "yellow_tones"],  # Ambiguous
    "light_yellow": ["yellow_tones"],
    "mustard": ["orange_tones", "yellow_tones"],  # Ambiguous
    "khaki": ["orange_tones", "yellow_tones"],  # Ambiguous
    
    # Green tones (with ambiguous colors)
    "green": ["green_tones"],
    "dark_green": ["green_tones"],
    "light_green": ["green_tones"],
    "olive": ["green_tones", "brown_tones"],  # Ambiguous
    "lime": ["green_tones"],
    "forest_green": ["green_tones"],
    "mint": ["green_tones"],
    "teal": ["green_tones"],
    
    # Blue tones
    "blue": ["blue_tones"],
    "dark_blue": ["blue_tones"],
    "light_blue": ["blue_tones"],
    "navy": ["blue_tones"],
    "sky_blue": ["blue_tones"],
    "royal_blue": ["blue_tones"],
    "cobalt": ["blue_tones"],
    "turquoise": ["blue_tones"],
    
    # Purple tones
    "purple": ["purple_tones"],
    "dark_purple": ["purple_tones"],
    "light_purple": ["purple_tones"],
    "violet": ["purple_tones"],
    "lavender": ["purple_tones"],
    "magenta": ["purple_tones"],
    "fuchsia": ["purple_tones"],
    "plum": ["purple_tones"],
    
    # Brown tones (with ambiguous colors)
    "brown": ["brown_tones"],
    "dark_brown": ["brown_tones"],
    "light_brown": ["brown_tones"],
    "tan": ["brown_tones"],
    "beige": ["brown_tones", "white_tones"],  # Ambiguous
    "camel": ["brown_tones"],
    
    # Pink tones (with ambiguous colors)
    "pink": ["pink_tones"],
    "light_pink": ["pink_tones"],
    "hot_pink": ["pink_tones"],
    "rose": ["pink_tones"],
    "salmon": ["red_tones", "pink_tones"],  # Ambiguous
    
    # White tones (with ambiguous colors)
    "white": ["white_tones"],
    "light_gray": ["white_tones", "black_tones"],  # Ambiguous
    "silver": ["white_tones"],
    
    # Black tones
    "black": ["black_tones"],
    "dark_gray": ["black_tones"],
    
    # Gray (not in any tone group - neutral)
    "gray": [],
}

# Legacy mapping for backward compatibility (returns first tone group)
COLOR_TO_TONE_GROUP = {}
for color_name, tone_groups in COLOR_TO_TONE_GROUPS.items():
    if tone_groups:
        COLOR_TO_TONE_GROUP[color_name] = tone_groups[0]

def get_color_tone_group(color_name: str) -> str:
    """
    หากลุ่มโทนหลักของสีที่ระบุ

    Args:
        color_name: ชื่อสีละเอียด (เช่น "peach", "blue", "navy")

    Returns:
        str: ชื่อกลุ่มโทนหลัก (เช่น "orange_tones", "blue_tones") หรือ "unknown"
    """
    return COLOR_TO_TONE_GROUP.get(color_name, "unknown")


def calculate_tone_groups_from_detailed(detailed_colors: dict) -> dict:
    """
    Calculate tone groups from detailed colors.
    Handles ambiguous colors by splitting percentage across multiple tone groups.

    Args:
        detailed_colors: dict of detailed colors {color_name: percentage}

    Returns:
        dict: tone groups with percentages {tone_group: percentage}
    """
    tone_groups = {}

    if not detailed_colors:
        return tone_groups

    for color_name, percentage in detailed_colors.items():
        # Get tone groups for this color (may be multiple for ambiguous colors)
        color_tone_groups = COLOR_TO_TONE_GROUPS.get(color_name, [])

        if not color_tone_groups:
            # Color not in any tone group (e.g., gray)
            continue

        # Split percentage across multiple tone groups
        num_groups = len(color_tone_groups)
        split_percentage = percentage / num_groups

        for tone_group in color_tone_groups:
            if tone_group not in tone_groups:
                tone_groups[tone_group] = 0.0
            tone_groups[tone_group] += split_percentage

    # Round to 1 decimal place
    tone_groups = {k: round(v, 1) for k, v in tone_groups.items()}

    # Normalize to 100% if total > 0
    total = sum(tone_groups.values())
    if total > 0 and abs(total - 100.0) > 0.1:
        scale_factor = 100.0 / total
        tone_groups = {k: round(v * scale_factor, 1) for k, v in tone_groups.items()}

    return tone_groups

# ============================================
# � ฟังก์ชันช่วยเหลือ - Background Removal
# ============================================

def remove_background_grabcut(img):
    """Fallback: ใช้ GrabCut ตัด Background ออกเพื่อเหลือแต่ Foreground"""
    h, w = img.shape[:2]
    mask = np.ones((h, w), np.uint8) * cv2.GC_PR_FGD
    
    margin_w, margin_h = max(1, int(w * 0.05)), max(1, int(h * 0.05))
    cv2.rectangle(mask, (0, 0), (w-1, h-1), cv2.GC_PR_BGD, margin_w)
    
    mask[0:margin_h, 0:margin_w] = cv2.GC_BGD
    mask[0:margin_h, w-margin_w:w] = cv2.GC_BGD
    
    bgdModel = np.zeros((1, 65), np.float64)
    fgdModel = np.zeros((1, 65), np.float64)
    
    try:
        cv2.grabCut(img, mask, None, bgdModel, fgdModel, 3, cv2.GC_INIT_WITH_MASK)
        return np.where((mask == 2) | (mask == 0), 0, 1).astype(np.uint8)
    except:
        return np.ones(img.shape[:2], dtype=np.uint8)

def get_foreground_mask(img):
    """
    ตัด background ออกและคืนค่า mask
    
    Args:
        img: ภาพ input (BGR)
    
    Returns:
        mask: binary mask (0=background, 1=foreground)
    """
    if REMBG_AVAILABLE:
        try:
            bg_removed = remove(img)
            alpha = bg_removed[:, :, 3]
            fg_mask = (alpha > 50).astype(np.uint8)
            return fg_mask
        except:
            return remove_background_grabcut(img)
    else:
        return remove_background_grabcut(img)

# ============================================
# 🔧 ฟังก์ชันวิเคราะห์สีละเอียด
# ============================================

def analyze_detailed_colors(image_crop, return_map=False):
    """
    วิเคราะห์สีแบบละเอียด (Detailed Color Analysis)
    สำหรับการ tracking ที่ต้องการความแม่นยำสูง
    พร้อมตัด background ออก
    
    Args:
        image_crop: ภาพ crop ของคน/เสื้อผ้า
        return_map: คืนค่า map ภาพสีหรือไม่
    
    Returns:
        dict: ชื่อสีละเอียดและเปอร์เซ็นต์ (sums to 100%)
    """
    if image_crop is None or image_crop.size == 0:
        return ({}, None) if return_map else {}
    
    h, w = image_crop.shape[:2]
    if h < 20 or w < 20:
        return ({}, None) if return_map else {}
    
    # ย่อภาพเพื่อความเร็ว
    small_img = cv2.resize(image_crop, (64, 64))
    
    # ตัด background
    fg_mask = get_foreground_mask(small_img)
    
    # ดึงเฉพาะ pixel ที่เป็น foreground
    bgr_fg = small_img[fg_mask == 1]
    
    # ถ้าโดนตัดหายเกลี้ยงเพราะสีกลืนกันมาก ให้ใช้ภาพทั้งกรอบแทน
    if len(bgr_fg) < 50:
        bgr_fg = small_img.reshape(-1, 3)
        fg_mask = np.ones((64, 64), dtype=np.uint8)
    
    # แปลงเป็น HSV
    hsv_img = cv2.cvtColor(small_img, cv2.COLOR_BGR2HSV)
    
    # สร้าง mask สำหรับแต่ละสี - ใช้ competitive grouping
    color_counts = {}
    total_pixels = len(bgr_fg)
    
    # สร้าง mask สำหรับแต่ละสีเพื่อหาความเข้มที่ดีที่สุด
    color_masks = {}
    color_confidences = {}
    
    for color_name, ranges in DETAILED_COLOR_RANGES.items():
        h_min, h_max = ranges["h_range"]
        s_min, s_max = ranges["s_range"]
        v_min, v_max = ranges["v_range"]
        
        # สร้าง mask
        mask = cv2.inRange(hsv_img, 
                          (h_min, s_min, v_min), 
                          (h_max, s_max, v_max))
        
        # นับเฉพาะ pixel ที่เป็น foreground
        fg_masked = cv2.bitwise_and(mask, mask, mask=fg_mask)
        count = cv2.countNonZero(fg_masked)
        
        if count > 0:
            # คำนวณ confidence จากความเข้มของสี (HSV values)
            # ยิ่งใกล้กึ่งกลางของช่วงยิ่ง confidence สูง
            h_center = (h_min + h_max) / 2
            s_center = (s_min + s_max) / 2
            v_center = (v_min + v_max) / 2
            
            # ดึงค่า HSV เฉลี่ยของ pixel ที่ตรงกับสีนี้
            if count > 0:
                masked_pixels = hsv_img[fg_masked > 0]
                if len(masked_pixels) > 0:
                    avg_h = np.mean(masked_pixels[:, 0])
                    avg_s = np.mean(masked_pixels[:, 1])
                    avg_v = np.mean(masked_pixels[:, 2])
                    
                    # คำนวณ confidence - ยิ่งใกล้ center ยิ่งดี
                    h_dist = abs(avg_h - h_center) / (h_max - h_min + 1)
                    s_dist = abs(avg_s - s_center) / (s_max - s_min + 1)
                    v_dist = abs(avg_v - v_center) / (v_max - v_min + 1)
                    confidence = 1.0 - (h_dist + s_dist + v_dist) / 3.0
                else:
                    confidence = 0.5
            else:
                confidence = 0.5
            
            color_masks[color_name] = fg_masked
            color_confidences[color_name] = confidence
    
    # Competitive grouping - แต่ละ pixel จะถูกกำหนดให้สีที่มี confidence สูงสุด
    assigned_pixels = np.zeros((64, 64), dtype=np.int8)  # 0 = unassigned
    color_assignments = {}
    
    # จัดเรียงสีตาม confidence จากสูงไปต่ำ
    sorted_colors = sorted(color_confidences.keys(), 
                          key=lambda x: color_confidences[x], reverse=True)
    
    for color_name in sorted_colors:
        mask = color_masks[color_name]
        # กำหนด pixel ที่ยังไม่ถูกกำหนดให้สีนี้
        unassigned_pixels = (assigned_pixels == 0) & (mask > 0)
        count = np.sum(unassigned_pixels)
        
        if count > 0:
            assigned_pixels[unassigned_pixels] = 1
            pct = (count / total_pixels) * 100
            if pct > 2.0:  # กรอง noise
                color_counts[color_name] = round(pct, 1)
    
    # ปรับให้ sum เป็น 100% ถ้าจำเป็น
    total_pct = sum(color_counts.values())
    if total_pct > 0 and abs(total_pct - 100.0) > 0.1:
        # Normalize ให้ sum เป็น 100%
        scale_factor = 100.0 / total_pct
        color_counts = {k: round(v * scale_factor, 1) 
                       for k, v in color_counts.items()}
    
    if return_map:
        # สร้าง map ภาพสี
        map_img = np.zeros((64, 64, 3), dtype=np.uint8)
        
        for color_name, ranges in DETAILED_COLOR_RANGES.items():
            if color_name in color_counts:
                h_min, h_max = ranges["h_range"]
                s_min, s_max = ranges["s_range"]
                v_min, v_max = ranges["v_range"]
                
                # ใช้ mask ที่ถูกกำหนดแล้ว
                if color_name in color_masks:
                    mask = color_masks[color_name]
                    
                    # ใส่สีเฉลี่ย
                    avg_h = (h_min + h_max) // 2
                    avg_s = (s_min + s_max) // 2
                    avg_v = (v_min + v_max) // 2
                    
                    color = cv2.cvtColor(np.array([[[avg_h, avg_s, avg_v]]], dtype=np.uint8), 
                                       cv2.COLOR_HSV2BGR)[0][0]
                    
                    map_img[mask > 0] = color
        
        return color_counts, map_img
    
    return color_counts

def group_colors(detailed_colors):
    """
    แปลงสีละเอียดเป็นกลุ่มสี (Alias for get_color_groups)
    สำหรับการค้นหาที่ต้องการความกว้างขวาง

    Args:
        detailed_colors: dict ของสีละเอียดจาก analyze_detailed_colors

    Returns:
        dict: กลุ่มสีที่ตรงกับสีละเอียด
    """
    return get_color_groups(detailed_colors)


def get_color_groups(detailed_colors):
    """
    แปลงสีละเอียดเป็นกลุ่มสีแบบ competitive grouping
    สำหรับการค้นหาที่ต้องการความกว้างขวาง
    แต่ละ pixel จะถูกกำหนดให้กลุ่มที่มี priority สูงสุด

    Args:
        detailed_colors: dict ของสีละเอียดจาก analyze_detailed_colors

    Returns:
        dict: กลุ่มสีที่ตรงกับสีละเอียด (simple structure: {"group_name": percentage})
    """
    detected_groups = {}
    
    # Priority order สำหรับการแข่งขัน - กลุ่มที่มี priority สูงจะชนะ
    # จัดลำดับจากพิเศษไปทั่วไป
    priority_groups = [
        # กลุ่มพิเศษ (มีความเฉพาะตัวสูง)
        "formal_colors", "casual_colors", "vibrant_colors", "pastel_colors",
        # กลุ่มโทนสีหลัก
        "red_tones", "blue_tones", "green_tones", "yellow_tones", 
        "purple_tones", "orange_tones", "pink_tones", "brown_tones",
        # กลุ่มความสว่าง
        "light_colors", "dark_colors", "medium_colors",
        # กลุ่มอุณหภูมิสี
        "warm_colors", "cool_colors", "neutral_colors",
        # กลุ่มเสื้อผ้า
        "common_shirt_colors", "common_pants_colors"
    ]
    
    # สร้าง mapping จากสีละเอียดไปยังกลุ่มที่มี priority สูงสุด
    color_to_best_group = {}
    
    for group_name in priority_groups:
        if group_name in COLOR_GROUPS:
            group_colors = COLOR_GROUPS[group_name]
            for color_name in group_colors:
                if color_name in detailed_colors:
                    # ถ้าสีนี้ยังไม่ถูกกำหนดให้กลุ่มไหน หรือกลุ่มนี้มี priority สูงกว่า
                    if (color_name not in color_to_best_group or 
                        priority_groups.index(group_name) < priority_groups.index(color_to_best_group[color_name])):
                        color_to_best_group[color_name] = group_name
    
    # รวมสีที่อยู่ในกลุ่มเดียวกัน
    group_percentages = {}
    for color_name, group_name in color_to_best_group.items():
        if group_name not in group_percentages:
            group_percentages[group_name] = 0
        group_percentages[group_name] += detailed_colors[color_name]
    
    # กรองกลุ่มที่มีเปอร์เซ็นต์น้อยเกินไปและปรับให้ sum เป็น 100%
    total_pct = sum(group_percentages.values())
    if total_pct > 0:
        for group_name, pct in group_percentages.items():
            if pct > 5.0:  # กรองกลุ่มที่น้อยเกินไป
                # Normalize ให้เป็นเปอร์เซ็นต์ของ total ที่พบ
                normalized_pct = (pct / total_pct) * 100
                detected_groups[group_name] = round(normalized_pct, 1)
    
    # ปรับให้ sum เป็น 100% ถ้าจำเป็น
    final_total = sum(detected_groups.values())
    if final_total > 0 and abs(final_total - 100.0) > 0.1:
        scale_factor = 100.0 / final_total
        detected_groups = {k: round(v * scale_factor, 1) 
                          for k, v in detected_groups.items()}
    
    return detected_groups

def get_primary_detailed_color(detailed_colors):
    """
    หาสีละเอียดหลัก (Primary Detailed Color)
    
    Args:
        detailed_colors: dict ของสีละเอียด
    
    Returns:
        str: ชื่อสีละเอียดที่มีเปอร์เซ็นต์สูงสุด
    """
    if not detailed_colors:
        return "unknown"
    
    return max(detailed_colors, key=detailed_colors.get)

def get_primary_color_group(color_groups):
    """
    หากลุ่มสีหลัก (Primary Color Group)

    Args:
        color_groups: dict ของกลุ่มสีจาก get_color_groups (simple structure)

    Returns:
        str: ชื่อกลุ่มสีที่มีเปอร์เซ็นต์สูงสุด
    """
    if not color_groups:
        return "unknown"

    return max(color_groups, key=lambda x: color_groups[x])


def get_primary_colors(detailed_colors, color_groups):
    """
    หาสีหลักทั้งแบบละเอียดและแบบกลุ่ม

    Args:
        detailed_colors: dict ของสีละเอียด
        color_groups: dict ของกลุ่มสี

    Returns:
        tuple: (primary_detailed_color, primary_color_group)
    """
    primary_detailed = get_primary_detailed_color(detailed_colors)
    primary_group = get_primary_color_group(color_groups)
    return primary_detailed, primary_group


def get_top_colors(detailed_colors, n=3, include_group=True):
    """
    ดึงสีละเอียดที่มีเปอร์เซ็นต์สูงสุด n สี
    
    Args:
        detailed_colors: dict ของสีละเอียด {color_name: percentage}
        n: จำนวนสีที่ต้องการ (default: 3)
        include_group: รวมข้อมูลกลุ่มโทนหลักด้วยหรือไม่ (default: True)
        
    Returns:
        list: รายการสี [{"name": "red", "percentage": 45.5, "group": "red_tones"}, ...]
              หรือ [{"name": "red", "percentage": 45.5}, ...] ถ้า include_group=False
    """
    if not detailed_colors:
        return []
    
    # Sort by percentage descending and get top n
    sorted_colors = sorted(
        detailed_colors.items(),
        key=lambda x: x[1],
        reverse=True
    )[:n]
    
    if include_group:
        return [
            {
                "name": name, 
                "percentage": round(pct, 1),
                "group": get_color_tone_group(name)
            }
            for name, pct in sorted_colors
        ]
    else:
        return [
            {"name": name, "percentage": round(pct, 1)}
            for name, pct in sorted_colors
        ]


def calculate_category_groups(detailed_colors):
    """
    Calculate all 5 color categories independently from detailed_colors.
    Each color can belong to multiple groups across categories (overlapping grouping).
    
    Args:
        detailed_colors: dict of detailed colors {color_name: percentage}
        
    Returns:
        dict: {
            "tone_groups": {...},
            "brightness_groups": {...},
            "vibrancy_groups": {...},
            "temperature_groups": {...},
            "clothing_groups": {...}
        }
    """
    tone_groups = {}
    brightness_groups = {}
    vibrancy_groups = {}
    temperature_groups = {}
    clothing_groups = {}
    
    if not detailed_colors:
        return {
            "tone_groups": tone_groups,
            "brightness_groups": brightness_groups,
            "vibrancy_groups": vibrancy_groups,
            "temperature_groups": temperature_groups,
            "clothing_groups": clothing_groups
        }
    
    # กลุ่มตามโทนสีหลัก (8 กลุ่ม)
    tone_names = [
        "red_tones", "orange_tones", "yellow_tones", "green_tones",
        "blue_tones", "purple_tones", "brown_tones", "pink_tones"
    ]
    
    # กลุ่มตามความสว่าง (3 กลุ่ม)
    brightness_names = ["light_colors", "dark_colors", "medium_colors"]
    
    # กลุ่มตามความสดใส (3 กลุ่ม)
    vibrancy_names = ["vibrant_colors", "muted_colors", "pastel_colors"]
    
    # กลุ่มตามอุณหภูมิสี (3 กลุ่ม)
    temperature_names = ["warm_colors", "cool_colors", "neutral_colors"]
    
    # กลุ่มสำหรับเสื้อผ้า (4 กลุ่ม)
    clothing_names = [
        "common_shirt_colors", "common_pants_colors",
        "formal_colors", "casual_colors"
    ]
    
    # Calculate each category independently from detailed_colors
    # Each color can contribute to multiple groups across categories
    
    # Tone groups
    for group_name in tone_names:
        if group_name in COLOR_GROUPS:
            group_colors = COLOR_GROUPS[group_name]
            total_pct = 0.0
            for color_name in group_colors:
                if color_name in detailed_colors:
                    total_pct += detailed_colors[color_name]
            if total_pct > 0:
                tone_groups[group_name] = round(total_pct, 1)
    
    # Brightness groups
    for group_name in brightness_names:
        if group_name in COLOR_GROUPS:
            group_colors = COLOR_GROUPS[group_name]
            total_pct = 0.0
            for color_name in group_colors:
                if color_name in detailed_colors:
                    total_pct += detailed_colors[color_name]
            if total_pct > 0:
                brightness_groups[group_name] = round(total_pct, 1)
    
    # Vibrancy groups
    for group_name in vibrancy_names:
        if group_name in COLOR_GROUPS:
            group_colors = COLOR_GROUPS[group_name]
            total_pct = 0.0
            for color_name in group_colors:
                if color_name in detailed_colors:
                    total_pct += detailed_colors[color_name]
            if total_pct > 0:
                vibrancy_groups[group_name] = round(total_pct, 1)
    
    # Temperature groups
    for group_name in temperature_names:
        if group_name in COLOR_GROUPS:
            group_colors = COLOR_GROUPS[group_name]
            total_pct = 0.0
            for color_name in group_colors:
                if color_name in detailed_colors:
                    total_pct += detailed_colors[color_name]
            if total_pct > 0:
                temperature_groups[group_name] = round(total_pct, 1)
    
    # Clothing groups
    for group_name in clothing_names:
        if group_name in COLOR_GROUPS:
            group_colors = COLOR_GROUPS[group_name]
            total_pct = 0.0
            for color_name in group_colors:
                if color_name in detailed_colors:
                    total_pct += detailed_colors[color_name]
            if total_pct > 0:
                clothing_groups[group_name] = round(total_pct, 1)
    
    return {
        "tone_groups": tone_groups,
        "brightness_groups": brightness_groups,
        "vibrancy_groups": vibrancy_groups,
        "temperature_groups": temperature_groups,
        "clothing_groups": clothing_groups
    }


def get_color_categories(detailed_colors):
    """
    จัดกลุ่มสีตามหมวดหมู่ 5 ประเภท
    ใช้ overlapping grouping เพื่อให้ทุกหมวดหมู่มีข้อมูล
    
    Args:
        detailed_colors: dict ของสีละเอียด {color_name: percentage}
        
    Returns:
        dict: {
            "tone_groups": {...},
            "brightness_groups": {...},
            "vibrancy_groups": {...},
            "temperature_groups": {...},
            "clothing_groups": {...}
        }
    """
    return calculate_category_groups(detailed_colors)


def get_primary_tone_group(color_groups):
    """
    หากลุ่มโทนสีหลัก (จาก 8 กลุ่มหลัก)
    
    Args:
        color_groups: dict ของกลุ่มสี
        
    Returns:
        str: ชื่อกลุ่มโทนสีหลัก หรือ "unknown"
    """
    tone_names = [
        "red_tones", "orange_tones", "yellow_tones", "green_tones",
        "blue_tones", "purple_tones", "brown_tones", "pink_tones"
    ]
    
    tone_groups = {k: v for k, v in color_groups.items() if k in tone_names}
    
    if not tone_groups:
        return "unknown"
    
    return max(tone_groups, key=tone_groups.get)

def search_by_color_group(track_history, group_name, min_percentage=10.0):
    """
    ค้นหาคนตามกลุ่มสี
    
    Args:
        track_history: dict ของข้อมูล tracking
        group_name: ชื่อกลุ่มสีที่ต้องการค้นหา
        min_percentage: เปอร์เซ็นต์ขั้นต่ำ
    
    Returns:
        list: รายการ track_id ที่ตรงกับเงื่อนไข
    """
    results = []
    
    for track_id, data in track_history.items():
        if "color_groups" in data and group_name in data["color_groups"]:
            group_percentage = data["color_groups"][group_name]
            if group_percentage >= min_percentage:
                results.append({
                    "track_id": track_id,
                    "percentage": group_percentage,
                    **data
                })
    
    return results

def search_by_detailed_color(track_history, color_name, min_percentage=5.0):
    """
    ค้นหาคนตามสีละเอียด
    
    Args:
        track_history: dict ของข้อมูล tracking
        color_name: ชื่อสีละเอียดที่ต้องการค้นหา
        min_percentage: เปอร์เซ็นต์ขั้นต่ำ
    
    Returns:
        list: รายการ track_id ที่ตรงกับเงื่อนไข
    """
    results = []
    
    for track_id, data in track_history.items():
        if "detailed_colors" in data and color_name in data["detailed_colors"]:
            if data["detailed_colors"][color_name] >= min_percentage:
                results.append({
                    "track_id": track_id,
                    "percentage": data["detailed_colors"][color_name],
                    **data
                })
    
    return results

# ============================================
# 🎨 ฟังก์ชันช่วยเหลือเพิ่มเติม
# ============================================

def get_all_detailed_colors():
    """คืนค่ารายชื่อสีละเอียดทั้งหมด"""
    return list(DETAILED_COLOR_RANGES.keys())

def get_all_color_groups():
    """คืนค่ารายชื่อกลุ่มสีทั้งหมด"""
    return list(COLOR_GROUPS.keys())

def get_color_group_members(group_name):
    """คืนค่าสมาชิกของกลุ่มสี"""
    return COLOR_GROUPS.get(group_name, [])

def is_color_in_group(color_name, group_name):
    """ตรวจสอบว่าสีอยู่ในกลุ่มที่ระบุหรือไม่"""
    return color_name in COLOR_GROUPS.get(group_name, [])

if __name__ == "__main__":
    # ทดสอบระบบ
    print("🎨 Detailed Color System")
    print(f"Total detailed colors: {len(DETAILED_COLOR_RANGES)}")
    print(f"Total color groups: {len(COLOR_GROUPS)}")
    print(f"\nDetailed colors: {get_all_detailed_colors()}")
    print(f"\nColor groups: {get_all_color_groups()}")
