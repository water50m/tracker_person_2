#!/usr/bin/env python3
"""
Direct test of color analysis functions without AI module imports
ทดสอบฟังก์ชันวิเคราะห์สีโดยตรงโดยไม่ผ่าน __init__.py
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

def test_color_functions_direct():
    """ทดสอบฟังก์ชันวิเคราะห์สีโดยตรง"""
    print("🧪 Testing color analysis functions directly...")
    
    try:
        # Import แบบตรงๆ ไม่ผ่าน __init__.py
        sys.path.append(os.path.join(os.path.dirname(__file__), 'src', 'ai'))
        
        # Import ฟังก์ชันที่ต้องการโดยตรง
        import importlib.util
        spec = importlib.util.spec_from_file_location("color_system", "src/ai/color_system.py")
        color_system = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(color_system)
        
        # ดึงฟังก์ชัน
        analyze_detailed_colors = color_system.analyze_detailed_colors
        get_color_groups = color_system.get_color_groups
        get_primary_detailed_color = color_system.get_primary_detailed_color
        get_primary_color_group = color_system.get_primary_color_group
        
        print("✅ Successfully imported color functions")
        
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

def test_edge_cases():
    """ทดสอบกรณีพิเศษ"""
    print("\n🔍 Testing edge cases...")
    
    try:
        # Import ฟังก์ชัน
        import importlib.util
        spec = importlib.util.spec_from_file_location("color_system", "src/ai/color_system.py")
        color_system = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(color_system)
        
        analyze_detailed_colors = color_system.analyze_detailed_colors
        
        # ทดสอบภาพว่าง
        print("\n--- Testing EMPTY image ---")
        empty_img = np.array([])
        try:
            result = analyze_detailed_colors(empty_img)
            print(f"Empty image result: {result}")
        except Exception as e:
            print(f"Empty image error: {e}")
        
        # ทดสอบภาพเล็กมาก
        print("\n--- Testing VERY SMALL image ---")
        small_img = np.full((10, 10, 3), (255, 0, 0), dtype=np.uint8)
        result = analyze_detailed_colors(small_img)
        print(f"Small image result: {result}")
        
        # ทดสอบภาพที่มีค่าสีผิดปกติ
        print("\n--- Testing INVALID image ---")
        try:
            invalid_img = np.full((100, 100, 3), 500, dtype=np.uint8)  # ค่าเกิน 255
            result = analyze_detailed_colors(invalid_img)
            print(f"Invalid image result: {result}")
        except Exception as e:
            print(f"Invalid image error: {e}")
        
        # ทดสอบ None
        print("\n--- Testing NONE image ---")
        try:
            result = analyze_detailed_colors(None)
            print(f"None image result: {result}")
        except Exception as e:
            print(f"None image error: {e}")
        
    except Exception as e:
        print(f"❌ Error in edge cases test: {e}")

def main():
    """ฟังก์ชันหลัก"""
    print("🚀 Starting Direct Color Analysis Test")
    print("=" * 60)
    
    # ทดสอบฟังก์ชันวิเคราะห์สี
    success = test_color_functions_direct()
    
    # ทดสอบกรณีพิเศษ
    test_edge_cases()
    
    print("\n" + "=" * 60)
    print("🏁 Test completed!")
    
    if success:
        print("✅ Color functions test completed successfully")
        print("📝 Check if detailed_colors are empty in the output above")
    else:
        print("❌ Color functions test failed")
        print("🔧 Check the error messages above")

if __name__ == "__main__":
    main()
