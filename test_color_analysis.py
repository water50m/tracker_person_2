#!/usr/bin/env python3
"""
Test script to debug color analysis pipeline
ทดสอบระบบวิเคราะห์สีเพื่อหาสาเหตุที่ detailed_colors ว่างเปล่า
"""

import cv2
import numpy as np
import sys
import os

# Add project root to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from src.ai.color_system import analyze_detailed_colors, get_color_groups, get_primary_detailed_color, get_primary_color_group
from src.ai.detector import PersonDetector
from src.ai.classifier import ClothingClassifier

def create_test_image():
    """สร้างภาพทดสอบที่มีคนและเสื้อผ้าสีต่างๆ"""
    # สร้างภาพ 640x480 พื้นหลังสีเทา
    img = np.full((480, 640, 3), 128, dtype=np.uint8)
    
    # เพิ่มรูปคน (สี่เหลี่ยมสีแดง)
    cv2.rectangle(img, (200, 100), (400, 400), (0, 0, 255), -1)  # สีแดงใน BGR
    cv2.rectangle(img, (250, 150), (350, 250), (255, 255, 255), -1)  # สีขาว (เสื้อ)
    cv2.rectangle(img, (250, 260), (350, 350), (0, 0, 0), -1)  # สีดำ (กางเกง)
    
    return img

def test_color_analysis_functions():
    """ทดสอบฟังก์ชันวิเคราะห์สีโดยตรง"""
    print("🧪 Testing color analysis functions...")
    
    # สร้างภาพทดสอบ
    test_img = create_test_image()
    
    # ทดสอบ analyze_detailed_colors
    print("\n1. Testing analyze_detailed_colors:")
    detailed_colors = analyze_detailed_colors(test_img)
    print(f"   Result: {detailed_colors}")
    print(f"   Number of colors: {len(detailed_colors)}")
    
    # ทดสอบ get_color_groups
    print("\n2. Testing get_color_groups:")
    color_groups = get_color_groups(detailed_colors)
    print(f"   Result: {color_groups}")
    print(f"   Number of groups: {len(color_groups)}")
    
    # ทดสอบ get_primary_detailed_color
    print("\n3. Testing get_primary_detailed_color:")
    primary_color = get_primary_detailed_color(detailed_colors)
    print(f"   Result: {primary_color}")
    
    # ทดสอบ get_primary_color_group
    print("\n4. Testing get_primary_color_group:")
    primary_group = get_primary_color_group(color_groups)
    print(f"   Result: {primary_group}")
    
    return detailed_colors, color_groups, primary_color, primary_group

def test_person_detection():
    """ทดสอบการตรวจจับคน"""
    print("\n👤 Testing person detection...")
    
    try:
        detector = PersonDetector()
        test_img = create_test_image()
        
        # ตรวจจับคน
        detections = detector.detect(test_img)
        print(f"   Detections: {len(detections)}")
        
        if detections:
            for i, det in enumerate(detections):
                print(f"   Detection {i+1}: {det}")
                bbox = det['bbox']
                person_crop = test_img[bbox[1]:bbox[3], bbox[0]:bbox[2]]
                print(f"   Person crop shape: {person_crop.shape}")
                
                # ทดสอบ color analysis บน person crop
                detailed_colors = analyze_detailed_colors(person_crop)
                print(f"   Colors in person crop: {detailed_colors}")
        
        return detections
    except Exception as e:
        print(f"   ❌ Error in person detection: {e}")
        return []

def test_clothing_classification():
    """ทดสอบการจำแนกเสื้อผ้า"""
    print("\n👔 Testing clothing classification...")
    
    try:
        classifier = ClothingClassifier()
        test_img = create_test_image()
        
        # จำแนกเสื้อผ้า
        predictions = classifier.predict(test_img)
        print(f"   Predictions: {predictions}")
        
        return predictions
    except Exception as e:
        print(f"   ❌ Error in clothing classification: {e}")
        return []

def test_full_pipeline():
    """ทดสอบ pipeline แบบเต็ม"""
    print("\n🔄 Testing full AI pipeline...")
    
    try:
        detector = PersonDetector()
        classifier = ClothingClassifier()
        test_img = create_test_image()
        
        # ตรวจจับคน
        detections = detector.detect(test_img)
        
        if not detections:
            print("   ❌ No person detected")
            return
        
        # ใช้ detection แรก
        det = detections[0]
        bbox = det['bbox']
        person_crop = test_img[bbox[1]:bbox[3], bbox[0]:bbox[2]]
        
        # จำแนกเสื้อผ้า
        predictions = classifier.predict(person_crop)
        clothing_type = predictions[0] if predictions else "unknown"
        confidence = predictions[1] if len(predictions) > 1 else 0.0
        
        print(f"   Clothing type: {clothing_type} (confidence: {confidence:.2f})")
        
        # จำลอง AI pipeline logic
        category = "UNKNOWN"
        detailed_colors = {}
        color_groups = {}
        primary_detailed_color = "unknown"
        primary_color_group = "unknown"
        
        print(f"   🎯 AI Pipeline: clothing_type={clothing_type}, person_crop shape={person_crop.shape}")
        
        if clothing_type in ["Dress", "Robe"]:
            category = "FULL"
            print(f"   🎨 Analyzing FULL clothing: {clothing_type}")
            detailed_colors = analyze_detailed_colors(person_crop)
            print(f"   🎨 detailed_colors result: {detailed_colors}")
            color_groups = get_color_groups(detailed_colors)
            primary_detailed_color = get_primary_detailed_color(detailed_colors)
            primary_color_group = get_primary_color_group(color_groups)
        elif clothing_type in ["Jeans", "Shorts", "Skirt"]:
            category = "BOTTOM"
            ph, pw, _ = person_crop.shape
            bottom_crop = person_crop[int(ph*0.50):int(ph*0.90), :]
            print(f"   🎨 Analyzing BOTTOM clothing: {clothing_type}, crop shape: {bottom_crop.shape}")
            detailed_colors = analyze_detailed_colors(bottom_crop)
            print(f"   🎨 detailed_colors result: {detailed_colors}")
            color_groups = get_color_groups(detailed_colors)
            primary_detailed_color = get_primary_detailed_color(detailed_colors)
            primary_color_group = get_primary_color_group(color_groups)
        else:
            category = "TOP"
            ph, pw, _ = person_crop.shape
            top_crop = person_crop[int(ph*0.15):int(ph*0.50), :]
            print(f"   🎨 Analyzing TOP clothing: {clothing_type}, crop shape: {top_crop.shape}")
            detailed_colors = analyze_detailed_colors(top_crop)
            print(f"   🎨 detailed_colors result: {detailed_colors}")
            color_groups = get_color_groups(detailed_colors)
            primary_detailed_color = get_primary_detailed_color(detailed_colors)
            primary_color_group = get_primary_color_group(color_groups)
        
        print(f"   🎨 Final color data: detailed={len(detailed_colors)} colors, groups={len(color_groups)}, primary={primary_detailed_color}")
        
        # แสดงผลลัพธ์สุดท้าย
        print(f"\n📊 Final Results:")
        print(f"   Category: {category}")
        print(f"   Clothing Type: {clothing_type}")
        print(f"   Detailed Colors: {detailed_colors}")
        print(f"   Color Groups: {color_groups}")
        print(f"   Primary Color: {primary_detailed_color}")
        print(f"   Primary Group: {primary_color_group}")
        
    except Exception as e:
        print(f"   ❌ Error in full pipeline: {e}")
        import traceback
        traceback.print_exc()

def main():
    """ฟังก์ชันหลัก"""
    print("🚀 Starting Color Analysis Test")
    print("=" * 50)
    
    # ทดสอบฟังก์ชันวิเคราะห์สีโดยตรง
    detailed_colors, color_groups, primary_color, primary_group = test_color_analysis_functions()
    
    # ทดสอบการตรวจจับคน
    detections = test_person_detection()
    
    # ทดสอบการจำแนกเสื้อผ้า
    predictions = test_clothing_classification()
    
    # ทดสอบ pipeline แบบเต็ม
    test_full_pipeline()
    
    print("\n" + "=" * 50)
    print("🏁 Test completed!")
    
    # สรุปผล
    if not detailed_colors:
        print("❌ CRITICAL: analyze_detailed_colors() returned empty dict!")
    else:
        print(f"✅ analyze_detailed_colors() works: {len(detailed_colors)} colors found")
    
    if not color_groups:
        print("❌ CRITICAL: get_color_groups() returned empty dict!")
    else:
        print(f"✅ get_color_groups() works: {len(color_groups)} groups found")
    
    if primary_color == "unknown":
        print("❌ WARNING: get_primary_detailed_color() returned 'unknown'")
    else:
        print(f"✅ get_primary_detailed_color() works: {primary_color}")
    
    if primary_group == "unknown":
        print("❌ WARNING: get_primary_color_group() returned 'unknown'")
    else:
        print(f"✅ get_primary_color_group() works: {primary_group}")

if __name__ == "__main__":
    main()
