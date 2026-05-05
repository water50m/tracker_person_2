#!/usr/bin/env python3
"""
Quick test for tracking system - minimal version
ทดสอบเร็วๆ สำหรับตรวจสอบว่าระบบทำงานได้ปกติ
"""

import cv2
import time
import sys
import os

# Add path to import modules
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..', 'src', 'ai'))
sys.path.append(os.path.dirname(__file__))

from detection_tracking import setup_device, load_models, init_video_capture, detect_persons

def quick_test():
    """Quick test to verify system works"""
    print("🚀 Quick Test Starting...")
    
    # 1. Test device
    device = setup_device()
    print(f"✅ Device: {device}")
    
    # 2. Test models
    person_model, custom_model = load_models(device)
    print("✅ Models loaded")
    
    # 3. Test video
    video_path = r'E:\ALL_CODE\my-project\temp_videos\CAM-01_4p-c0-new.mp4'
    cap, width, height = init_video_capture(video_path)
    print(f"✅ Video: {width}x{height}")
    
    # 4. Test detection (5 frames only)
    print("🔍 Testing detection (5 frames)...")
    frame_count = 0
    total_detections = 0
    
    start_time = time.time()
    
    while cap.isOpened() and frame_count < 5:
        success, frame = cap.read()
        if not success:
            break
        
        frame_count += 1
        
        # Detect persons
        results = detect_persons(person_model, frame, device)
        
        if results[0].boxes.id is not None:
            num_persons = len(results[0].boxes.id)
            total_detections += num_persons
            print(f"   Frame {frame_count}: {num_persons} persons detected")
        else:
            print(f"   Frame {frame_count}: No persons detected")
    
    end_time = time.time()
    processing_time = end_time - start_time
    
    print(f"\n📊 Quick Test Results:")
    print(f"   Frames processed: {frame_count}")
    print(f"   Processing time: {processing_time:.2f}s")
    print(f"   Total detections: {total_detections}")
    print(f"   Average FPS: {frame_count/processing_time:.2f}")
    
    cap.release()
    
    if total_detections > 0:
        print("✅ Quick test PASSED - System working!")
        return True
    else:
        print("⚠️ Quick test WARNING - No persons detected")
        return False

if __name__ == "__main__":
    quick_test()
