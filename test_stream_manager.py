#!/usr/bin/env python3
"""
Quick test to check if stream manager has frames
"""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from src.services.stream_manager import stream_manager

def test_stream_manager():
    """Test if stream manager has frames for camera 11"""
    print("Testing stream manager...")
    
    # Check if camera 11 has frames
    frame = stream_manager.get_frame("11")
    frame_number = stream_manager.latest_frame_numbers.get("11", 0)
    detections = stream_manager.get_detections("11")
    
    print(f"Frame for camera 11: {'EXISTS' if frame else 'NONE'}")
    print(f"Frame number: {frame_number}")
    print(f"Frame size: {len(frame) if frame else 0} bytes")
    print(f"Detections: {len(detections) if detections else 0}")
    
    if frame:
        print("✅ Stream manager HAS frames - MJPEG should work!")
    else:
        print("❌ Stream manager has NO frames - MJPEG will be empty")

if __name__ == "__main__":
    test_stream_manager()
