#!/usr/bin/env python3
"""Debug script to test MJPEG stream functionality"""

import asyncio
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from src.services.stream_manager import stream_manager
from src.api.video_controller import _ACTIVE_STREAMS

async def test_stream_manager():
    print("=== Stream Manager Debug ===")
    print(f"Active streams: {list(_ACTIVE_STREAMS.keys())}")
    print(f"Available frames in stream_manager: {list(stream_manager.latest_frames.keys())}")
    print(f"Frame numbers: {stream_manager.latest_frame_numbers}")
    
    # Test retrieval for camera 11
    camera_id = "11"
    print(f"\n--- Testing camera {camera_id} ---")
    
    frame = stream_manager.get_frame(camera_id)
    print(f"get_frame('{camera_id}'): {frame is not None}")
    if frame:
        print(f"Frame size: {len(frame)} bytes")
    else:
        print("No frame available")
        
    # Test with integer camera ID
    camera_id_int = 11
    print(f"\n--- Testing camera {camera_id_int} (int) ---")
    frame_int = stream_manager.get_frame(str(camera_id_int))
    print(f"get_frame('{camera_id_int}'): {frame_int is not None}")
    if frame_int:
        print(f"Frame size: {len(frame_int)} bytes")

if __name__ == "__main__":
    asyncio.run(test_stream_manager())
