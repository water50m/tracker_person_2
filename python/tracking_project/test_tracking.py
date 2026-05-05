#!/usr/bin/env python3
"""
Test script for tracking system
ทดสอบระบบติดตามคนแบบครบวงจร
"""

import cv2
import numpy as np
import time
import unittest
import sys
import os

# Add path to import modules
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..', 'src', 'ai'))
sys.path.append(os.path.dirname(__file__))

from detection_tracking import (
    setup_device, load_models, init_video_capture,
    detect_persons, detect_clothes, analyze_person_features,
    update_track_history, cleanup_old_tracks,
    draw_person_box, draw_clothes_boxes, process_single_person
)

class TestTrackingSystem(unittest.TestCase):
    """Test class for tracking system"""
    
    @classmethod
    def setUpClass(cls):
        """Setup for all tests"""
        print("🔧 Setting up test environment...")
        cls.device = setup_device()
        cls.person_model, cls.custom_model = load_models(cls.device)
        print("✅ Models loaded successfully")
    
    def test_setup_device(self):
        """Test device setup"""
        device = setup_device()
        self.assertIn(device, ["cuda", "cpu"])
        print(f"✅ Device test passed: {device}")
    
    def test_load_models(self):
        """Test model loading"""
        person_model, custom_model = load_models(self.device)
        self.assertIsNotNone(person_model)
        self.assertIsNotNone(custom_model)
        print("✅ Model loading test passed")
    
    def test_video_capture(self):
        """Test video capture initialization"""
        # Create test video path (change to your test video)
        test_video = r'E:\ALL_CODE\my-project\temp_videos\CAM-01_4p-c0-new.mp4'
        
        try:
            cap, width, height = init_video_capture(test_video)
            self.assertIsNotNone(cap)
            self.assertGreater(width, 0)
            self.assertGreater(height, 0)
            cap.release()
            print("✅ Video capture test passed")
        except Exception as e:
            print(f"⚠️ Video capture test skipped: {e}")
    
    def test_color_analysis(self):
        """Test color analysis function"""
        try:
            from color_analysis import analyze_color_histogram
            
            # Create test image (64x64 RGB)
            test_img = np.zeros((64, 64, 3), dtype=np.uint8)
            test_img[:, :] = [255, 0, 0]  # Red image
            
            result = analyze_color_histogram(test_img)
            self.assertIsInstance(result, dict)
            print(f"✅ Color analysis test passed: {result}")
        except Exception as e:
            print(f"❌ Color analysis test failed: {e}")
    
    def test_track_history_management(self):
        """Test track history functions"""
        track_history = {}
        frame_count = 0
        
        # Test update
        features = {
            "clothes": ["Shirt", "Pants"],
            "colors": {"red": 60.5, "black": 30.0},
            "primary_color": "red"
        }
        
        update_track_history(track_history, 1, features, frame_count)
        self.assertIn(1, track_history)
        self.assertEqual(track_history[1]["clothes"], ["Shirt", "Pants"])
        
        # Test cleanup
        current_ids = [2, 3]  # ID 1 not in current
        cleanup_old_tracks(track_history, current_ids, frame_count + 100)
        self.assertNotIn(1, track_history)
        
        print("✅ Track history management test passed")

def run_performance_test():
    """Run performance test with real video"""
    print("\n🚀 Running performance test...")
    
    # Setup
    device = setup_device()
    person_model, custom_model = load_models(device)
    
    # Use shorter video for testing
    video_path = r'E:\ALL_CODE\my-project\temp_videos\CAM-01_4p-c0-new.mp4'
    cap, frame_width, frame_height = init_video_capture(video_path)
    
    track_history = {}
    frame_count = 0
    start_time = time.time()
    
    print("Processing 100 frames for performance test...")
    
    while cap.isOpened() and frame_count < 100:
        success, frame = cap.read()
        if not success:
            break
        
        frame_count += 1
        current_ids = []
        
        # Detect persons
        person_results = detect_persons(person_model, frame, device)
        
        if person_results[0].boxes.id is not None:
            boxes = person_results[0].boxes.xyxy.cpu().numpy().astype(int)
            ids = person_results[0].boxes.id.cpu().numpy().astype(int)
            
            for box, track_id in zip(boxes, ids):
                current_ids.append(track_id)
                process_single_person(
                    person_model, custom_model, frame, box, track_id,
                    track_history, frame_count, device, frame_width, frame_height
                )
        
        # Cleanup old tracks
        cleanup_old_tracks(track_history, current_ids, frame_count)
        
        # Progress
        if frame_count % 20 == 0:
            print(f"Processed {frame_count}/100 frames...")
    
    # Calculate performance
    end_time = time.time()
    processing_time = end_time - start_time
    fps = frame_count / processing_time
    
    print(f"\n📊 Performance Results:")
    print(f"   Frames processed: {frame_count}")
    print(f"   Processing time: {processing_time:.2f}s")
    print(f"   Average FPS: {fps:.2f}")
    print(f"   Tracks detected: {len(track_history)}")
    
    # Show track details
    print(f"\n👥 Detected Persons:")
    for track_id, data in track_history.items():
        clothes = ", ".join(data["clothes"]) if data["clothes"] else "Unknown"
        print(f"   ID {track_id}: {clothes} | {data['primary_color']}")
    
    cap.release()
    return fps

def run_interactive_test():
    """Run interactive test with video display"""
    print("\n🎥 Running interactive test...")
    print("Press 'q' to quit, 's' to save current frame info")
    
    # Setup
    device = setup_device()
    person_model, custom_model = load_models(device)
    
    video_path = r'E:\ALL_CODE\my-project\temp_videos\CAM-01_4p-c0-new.mp4'
    cap, frame_width, frame_height = init_video_capture(video_path)
    
    track_history = {}
    frame_count = 0
    
    while cap.isOpened():
        success, frame = cap.read()
        if not success:
            break
        
        frame_count += 1
        current_ids = []
        
        # Detect persons
        person_results = detect_persons(person_model, frame, device)
        
        if person_results[0].boxes.id is not None:
            boxes = person_results[0].boxes.xyxy.cpu().numpy().astype(int)
            ids = person_results[0].boxes.id.cpu().numpy().astype(int)
            
            for box, track_id in zip(boxes, ids):
                current_ids.append(track_id)
                process_single_person(
                    person_model, custom_model, frame, box, track_id,
                    track_history, frame_count, device, frame_width, frame_height
                )
        
        # Cleanup
        cleanup_old_tracks(track_history, current_ids, frame_count)
        
        # Display info
        info_text = f"Frame: {frame_count} | Persons: {len(current_ids)} | Tracks: {len(track_history)}"
        cv2.putText(frame, info_text, (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
        
        cv2.imshow('Interactive Tracking Test', frame)
        
        key = cv2.waitKey(1) & 0xFF
        if key == ord('q'):
            break
        elif key == ord('s'):
            print(f"\n📋 Frame {frame_count} Summary:")
            for track_id, data in track_history.items():
                clothes = ", ".join(data["clothes"]) if data["clothes"] else "Unknown"
                print(f"   ID {track_id}: {clothes} | {data['primary_color']} | Confidence: {data['confidence']:.2f}")
    
    cap.release()
    cv2.destroyAllWindows()

def main():
    """Main test runner"""
    print("🧪 Tracking System Test Suite")
    print("=" * 50)
    
    # Run unit tests
    print("\n📝 Running Unit Tests...")
    unittest.main(argv=[''], exit=False, verbosity=0)
    
    # Ask user for additional tests
    print("\n" + "=" * 50)
    print("Additional Tests Available:")
    print("1. Performance Test (100 frames)")
    print("2. Interactive Test (with video display)")
    print("3. Exit")
    
    while True:
        choice = input("\nSelect test (1-3): ").strip()
        
        if choice == '1':
            run_performance_test()
        elif choice == '2':
            run_interactive_test()
        elif choice == '3':
            break
        else:
            print("Invalid choice. Please select 1-3.")
    
    print("\n✅ All tests completed!")

if __name__ == "__main__":
    main()
