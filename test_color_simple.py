#!/usr/bin/env python3
"""
Simple test script to debug color analysis functions only
ทดสอบเฉพาะฟังก์ชันวิเคราะห์สีโดยไม่ต้องโหลด AI models
"""

import cv2
import numpy as np
import sys
import os

# Add project root to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

def create_test_images():
    """สร้างภาพทดสอบหลายแบบ"""
    test_images = {}
    
    # 1. ภาพสีแดงล้วน
    red_img = np.full((200, 200, 3), (0, 0, 255), dtype=np.uint8)  # BGR: สีแดง
    test_images['red'] = red_img
    
    # 2. ภาพสีเขียวล้วน
    green_img = np.full((200, 200, 3), (0, 255, 0), dtype=np.uint8)  # BGR: สีเขียว
    test_images['green'] = green_img
    
    # 3. ภาพสีน้ำเงินล้วน
    blue_img = np.full((200, 200, 3), (255, 0, 0), dtype=np.uint8)  # BGR: สีน้ำเงิน
    test_images['blue'] = blue_img
    
    # 4. ภาพสีขาวล้วน
    white_img = np.full((200, 200, 3), (255, 255, 255), dtype=np.uint8)  # BGR: สีขาว
    test_images['white'] = white_img
    
    # 5. ภาพสีดำล้วน
    black_img = np.full((200, 200, 3), (0, 0, 0), dtype=np.uint8)  # BGR: สีดำ
    test_images['black'] = black_img
    
    # 6. ภาพผสมสี (เหมือนคนใส่เสื้อ)
    mixed_img = np.full((200, 200, 3), 128, dtype=np.uint8)  # พื้นเทา
    cv2.rectangle(mixed_img, (50, 50), (150, 100), (0, 0, 255), -1)  # สีแดง (เสื้อ)
    cv2.rectangle(mixed_img, (50, 110), (150, 160), (0, 0, 0), -1)  # สีดำ (กางเกง)
    test_images['mixed'] = mixed_img
    
    return test_images

def test_color_functions_only():
    """ทดสอบเฉพาะฟังก์ชันวิเคราะห์สี"""
    print("🧪 Testing color analysis functions only...")
    
    try:
        # Import เฉพาะฟังก์ชันที่ต้องการ
        from src.ai.color_system import (
            analyze_detailed_colors, 
            get_color_groups, 
            get_primary_detailed_color, 
            get_primary_color_group
        )
        
        test_images = create_test_images()
        
        for name, img in test_images.items():
            print(f"\n--- Testing {name.upper()} image ---")
            print(f"Image shape: {img.shape}")
            
            # ทดสอบ analyze_detailed_colors
            detailed_colors = analyze_detailed_colors(img)
            print(f"🎨 detailed_colors: {detailed_colors}")
            print(f"   Number of colors: {len(detailed_colors)}")
            
            # ทดสอบ get_color_groups
            color_groups = get_color_groups(detailed_colors)
            print(f"🎨 color_groups: {color_groups}")
            print(f"   Number of groups: {len(color_groups)}")
            
            # ทดสอบ get_primary_detailed_color
            primary_color = get_primary_detailed_color(detailed_colors)
            print(f"🎨 primary_detailed_color: {primary_color}")
            
            # ทดสอบ get_primary_color_group
            primary_group = get_primary_color_group(color_groups)
            print(f"🎨 primary_color_group: {primary_group}")
            
            # ตรวจสอบว่าข้อมูลว่างเปล่าหรือไม่
            if not detailed_colors:
                print(f"❌ ERROR: detailed_colors is empty for {name}!")
            if not color_groups:
                print(f"❌ ERROR: color_groups is empty for {name}!")
            if primary_color == "unknown":
                print(f"⚠️  WARNING: primary_detailed_color is 'unknown' for {name}")
            if primary_group == "unknown":
                print(f"⚠️  WARNING: primary_color_group is 'unknown' for {name}")
        
        return True
        
    except Exception as e:
        print(f"❌ Error in color functions test: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_image_properties():
    """ทดสอบคุณสมบัติของภาพ"""
    print("\n🔍 Testing image properties...")
    
    test_images = create_test_images()
    
    for name, img in test_images.items():
        print(f"\n--- {name.upper()} image ---")
        print(f"Shape: {img.shape}")
        print(f"Dtype: {img.dtype}")
        print(f"Min value: {img.min()}")
        print(f"Max value: {img.max()}")
        print(f"Mean value: {img.mean():.2f}")
        
        # ตรวจสอบค่าสีที่จุดกลาง
        h, w = img.shape[:2]
        center_pixel = img[h//2, w//2]
        print(f"Center pixel (BGR): {center_pixel}")
        
        # แปลงเป็น HSV เพื่อดูค่า
        hsv_img = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
        center_hsv = hsv_img[h//2, w//2]
        print(f"Center pixel (HSV): {center_hsv}")

def main():
    """ฟังก์ชันหลัก"""
    print("🚀 Starting Simple Color Analysis Test")
    print("=" * 60)
    
    # ทดสอบคุณสมบัติภาพ
    test_image_properties()
    
    # ทดสอบฟังก์ชันวิเคราะห์สี
    success = test_color_functions_only()
    
    print("\n" + "=" * 60)
    print("🏁 Test completed!")
    
    if success:
        print("✅ Color functions test completed successfully")
        print("📝 Check the output above to see if detailed_colors are empty")
    else:
        print("❌ Color functions test failed")
        print("🔧 Check the error messages above")

if __name__ == "__main__":
    main()
