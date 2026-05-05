#!/usr/bin/env python3
"""
Manual debug of color analysis - copy functions directly
ทดสอบฟังก์ชันวิเคราะห์สีโดยคัดลอกโค้ดมาทดสอบโดยตรง
"""

import cv2
import numpy as np

def create_test_image():
    """สร้างภาพทดสอบสีแดง"""
    # สร้างภาพ 200x200 สีแดงล้วน
    img = np.full((200, 200, 3), (0, 0, 255), dtype=np.uint8)  # BGR: สีแดง
    return img

def simple_color_analysis(image_crop):
    """ฟังก์ชันวิเคราะห์สีแบบง่ายๆ"""
    if image_crop is None or image_crop.size == 0:
        return {}
    
    h, w = image_crop.shape[:2]
    if h < 20 or w < 20:
        return {}
    
    # ย่อภาพเพื่อความเร็ว
    small_img = cv2.resize(image_crop, (64, 64))
    
    # แปลงเป็น HSV
    hsv_img = cv2.cvtColor(small_img, cv2.COLOR_BGR2HSV)
    
    # นับสีพื้นฐาน
    color_counts = {}
    total_pixels = 64 * 64
    
    # นับสีแดง (H: 0-10)
    red_mask = cv2.inRange(hsv_img, (0, 100, 50), (10, 255, 255))
    red_count = cv2.countNonZero(red_mask)
    if red_count > 0:
        red_pct = (red_count / total_pixels) * 100
        if red_pct > 2.0:
            color_counts['red'] = round(red_pct, 1)
    
    # นับสีเขียว (H: 45-75)
    green_mask = cv2.inRange(hsv_img, (45, 100, 50), (75, 255, 255))
    green_count = cv2.countNonZero(green_mask)
    if green_count > 0:
        green_pct = (green_count / total_pixels) * 100
        if green_pct > 2.0:
            color_counts['green'] = round(green_pct, 1)
    
    # นับสีน้ำเงิน (H: 100-130)
    blue_mask = cv2.inRange(hsv_img, (100, 100, 50), (130, 255, 255))
    blue_count = cv2.countNonZero(blue_mask)
    if blue_count > 0:
        blue_pct = (blue_count / total_pixels) * 100
        if blue_pct > 2.0:
            color_counts['blue'] = round(blue_pct, 1)
    
    # นับสีขาว (S: 0-30, V: 200-255)
    white_mask = cv2.inRange(hsv_img, (0, 0, 200), (179, 30, 255))
    white_count = cv2.countNonZero(white_mask)
    if white_count > 0:
        white_pct = (white_count / total_pixels) * 100
        if white_pct > 2.0:
            color_counts['white'] = round(white_pct, 1)
    
    # นับสีดำ (V: 0-50)
    black_mask = cv2.inRange(hsv_img, (0, 0, 0), (179, 255, 50))
    black_count = cv2.countNonZero(black_mask)
    if black_count > 0:
        black_pct = (black_count / total_pixels) * 100
        if black_pct > 2.0:
            color_counts['black'] = round(black_pct, 1)
    
    return color_counts

def main():
    """ทดสอบหลัก"""
    print("🚀 Manual Color Analysis Test")
    print("=" * 40)
    
    # สร้างภาพทดสอบ
    test_img = create_test_image()
    print(f"Created test image: {test_img.shape}")
    print(f"Image dtype: {test_img.dtype}")
    print(f"Image range: {test_img.min()} - {test_img.max()}")
    
    # ตรวจสอบค่าสีที่จุดกลาง
    h, w = test_img.shape[:2]
    center_pixel = test_img[h//2, w//2]
    print(f"Center pixel (BGR): {center_pixel}")
    
    # แปลงเป็น HSV
    hsv_img = cv2.cvtColor(test_img, cv2.COLOR_BGR2HSV)
    center_hsv = hsv_img[h//2, w//2]
    print(f"Center pixel (HSV): {center_hsv}")
    
    # ทดสอบวิเคราะห์สี
    print("\n🎨 Testing color analysis...")
    colors = simple_color_analysis(test_img)
    print(f"Result: {colors}")
    print(f"Number of colors found: {len(colors)}")
    
    # ทดสอบภาพอื่นๆ
    print("\n--- Testing different colors ---")
    
    # สีเขียว
    green_img = np.full((200, 200, 3), (0, 255, 0), dtype=np.uint8)
    green_colors = simple_color_analysis(green_img)
    print(f"Green image: {green_colors}")
    
    # สีน้ำเงิน
    blue_img = np.full((200, 200, 3), (255, 0, 0), dtype=np.uint8)
    blue_colors = simple_color_analysis(blue_img)
    print(f"Blue image: {blue_colors}")
    
    # สีขาว
    white_img = np.full((200, 200, 3), (255, 255, 255), dtype=np.uint8)
    white_colors = simple_color_analysis(white_img)
    print(f"White image: {white_colors}")
    
    # สีดำ
    black_img = np.full((200, 200, 3), (0, 0, 0), dtype=np.uint8)
    black_colors = simple_color_analysis(black_img)
    print(f"Black image: {black_colors}")
    
    print("\n" + "=" * 40)
    print("🏁 Test completed!")
    
    # สรุป
    if colors:
        print(f"✅ SUCCESS: Found {len(colors)} colors in red image")
        print(f"📊 Colors found: {list(colors.keys())}")
    else:
        print("❌ ERROR: No colors found in red image!")
        print("🔍 This indicates a problem with the color analysis logic")
    
    # ตรวจสอบว่าเจอสีแดงหรือไม่
    if 'red' in colors:
        print(f"✅ Red color detected: {colors['red']}%")
    else:
        print("❌ Red color NOT detected - this is the problem!")

if __name__ == "__main__":
    main()
