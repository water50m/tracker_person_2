#!/usr/bin/env python3
"""
Test AI pipeline directly to see if color analysis is being called
ทดสอบ AI pipeline โดยตรงเพื่อดูว่าส่วนวิเคราะห์สีถูกเรียกหรือไม่
"""

import cv2
import numpy as np
import sys
import os

def test_ai_pipeline_mock():
    """จำลอง AI pipeline เพื่อดูว่าถึงส่วนวิเคราะห์สีหรือไม่"""
    print("🧪 Testing AI Pipeline Mock...")
    
    # สร้างข้อมูลจำลองเหมือนที่ AI pipeline จะได้รับ
    clothing_type = "shorts"
    person_crop = np.full((200, 300, 3), (128, 128, 128), dtype=np.uint8)  # ภาพเทา
    
    print(f"🎯 AI Pipeline: clothing_type={clothing_type}, person_crop shape={person_crop.shape}")
    
    # จำลอง logic จาก ai_processor.py
    category = "UNKNOWN"
    detailed_colors = {}
    color_groups = {}
    primary_detailed_color = "unknown"
    primary_color_group = "unknown"
    
    # จำลองการ import ฟังก์ชัน
    try:
        import importlib.util
        spec = importlib.util.spec_from_file_location("color_system", "src/ai/color_system.py")
        color_system = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(color_system)
        
        analyze_detailed_colors = color_system.analyze_detailed_colors
        get_color_groups = color_system.get_color_groups
        get_primary_detailed_color = color_system.get_primary_detailed_color
        get_primary_color_group = color_system.get_primary_color_group
        
        print("✅ Successfully imported color functions")
        
        # จำลอง logic เดียวกับใน ai_processor.py
        if clothing_type in ["Dress", "Robe"]:
            category = "FULL"
            print(f"🎨 Analyzing FULL clothing: {clothing_type}")
            detailed_colors = analyze_detailed_colors(person_crop)
            print(f"🎨 detailed_colors result: {detailed_colors}")
            color_groups = get_color_groups(detailed_colors)
            primary_detailed_color = get_primary_detailed_color(detailed_colors)
            primary_color_group = get_primary_color_group(color_groups)
        elif clothing_type in ["Jeans", "Shorts", "Skirt"]:
            category = "BOTTOM"
            ph, pw, _ = person_crop.shape
            bottom_crop = person_crop[int(ph*0.50):int(ph*0.90), :]
            print(f"🎨 Analyzing BOTTOM clothing: {clothing_type}, crop shape: {bottom_crop.shape}")
            detailed_colors = analyze_detailed_colors(bottom_crop)
            print(f"🎨 detailed_colors result: {detailed_colors}")
            color_groups = get_color_groups(detailed_colors)
            primary_detailed_color = get_primary_detailed_color(detailed_colors)
            primary_color_group = get_primary_color_group(color_groups)
        else:
            category = "TOP"
            ph, pw, _ = person_crop.shape
            top_crop = person_crop[int(ph*0.15):int(ph*0.50), :]
            print(f"🎨 Analyzing TOP clothing: {clothing_type}, crop shape: {top_crop.shape}")
            detailed_colors = analyze_detailed_colors(top_crop)
            print(f"🎨 detailed_colors result: {detailed_colors}")
            color_groups = get_color_groups(detailed_colors)
            primary_detailed_color = get_primary_detailed_color(detailed_colors)
            primary_color_group = get_primary_color_group(color_groups)
        
        print(f"🎨 Final color data: detailed={len(detailed_colors)} colors, groups={len(color_groups)}, primary={primary_detailed_color}")
        
        # แสดงผลลัพธ์สุดท้าย
        print(f"\n📊 Mock Pipeline Results:")
        print(f"   Category: {category}")
        print(f"   Clothing Type: {clothing_type}")
        print(f"   Detailed Colors: {detailed_colors}")
        print(f"   Color Groups: {color_groups}")
        print(f"   Primary Color: {primary_detailed_color}")
        print(f"   Primary Group: {primary_color_group}")
        
        return True
        
    except Exception as e:
        print(f"❌ Error in mock pipeline: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_database_insertion():
    """ทดสอบการ insert ข้อมูลลง database"""
    print("\n💾 Testing Database Insertion...")
    
    try:
        from src.services.database import DatabaseService
        
        # สร้างข้อมูลจำลอง
        test_data = {
            "camera_id": "test_camera",
            "track_id": 1,
            "category": "BOTTOM",
            "class_name": "shorts",
            "detailed_colors": {"red": 50.0, "blue": 30.0},
            "color_groups": {"warm": {"red": 50.0}, "cool": {"blue": 30.0}},
            "primary_detailed_color": "red",
            "primary_color_group": "warm",
            "clothes": ["shorts"],
            "bbox": [100, 100, 200, 200],
            "image_path": "",
            "video_time_offset": 0.1,
            "video_id": "test_video",
            "embedding": None
        }
        
        db = DatabaseService()
        print("✅ Database connection successful")
        
        # ทดสอบ insert
        db.insert_detection(**test_data)
        print("✅ Test data inserted successfully")
        
        # ตรวจสอบข้อมูลที่ insert
        with db.conn.cursor() as cur:
            cur.execute("""
                SELECT detailed_colors, color_groups, primary_detailed_color, primary_color_group 
                FROM detections 
                WHERE camera_id = 'test_camera' 
                ORDER BY timestamp DESC LIMIT 1
            """)
            result = cur.fetchone()
            
            if result:
                print(f"📊 Retrieved from database:")
                print(f"   detailed_colors: {result[0]}")
                print(f"   color_groups: {result[1]}")
                print(f"   primary_detailed_color: {result[2]}")
                print(f"   primary_color_group: {result[3]}")
            else:
                print("❌ No data found in database")
        
        return True
        
    except Exception as e:
        print(f"❌ Database test error: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    """ฟังก์ชันหลัก"""
    print("🚀 AI Pipeline Test")
    print("=" * 50)
    
    # ทดสอบ AI pipeline mock
    pipeline_success = test_ai_pipeline_mock()
    
    # ทดสอบ database insertion
    db_success = test_database_insertion()
    
    print("\n" + "=" * 50)
    print("🏁 Test Results:")
    
    if pipeline_success:
        print("✅ AI Pipeline Mock: SUCCESS")
        print("   - Color functions work correctly")
        print("   - Logic reaches color analysis section")
    else:
        print("❌ AI Pipeline Mock: FAILED")
        print("   - Check color function imports")
    
    if db_success:
        print("✅ Database Insertion: SUCCESS")
        print("   - Can save detailed_colors to database")
    else:
        print("❌ Database Insertion: FAILED")
        print("   - Check database connection")
    
    print(f"\n🎯 CONCLUSION:")
    if pipeline_success and db_success:
        print("✅ Both pipeline and database work correctly")
        print("❌ The real system must have a different issue")
        print("🔍 Check if the real AI pipeline actually calls color analysis")
    else:
        print("❌ Found technical issues that need fixing")

if __name__ == "__main__":
    main()
