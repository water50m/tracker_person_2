#!/usr/bin/env python3
"""
YouTube Stream Test - Direct CV2 + MJPEG Streaming
No database, no AI processing, just CV2 capture + stream manager + MJPEG endpoint
"""

import asyncio
import sys
import time
import cv2
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from src.services.stream_manager import stream_manager
from src.api.video_controller import _ACTIVE_STREAMS, _register_stream, _unregister_stream

class YouTubeStreamTester:
    """
    Direct YouTube stream tester
    """
    
    def __init__(self):
        self.camera_id = "11"
        self.youtube_url = "https://www.youtube.com/watch?v=UemFRPrl1hk"
        self.stop_event = None
        self.cap = None
    
    async def test_youtube_stream(self):
        """Test YouTube streaming directly"""
        print("=" * 60)
        print("YOUTUBE DIRECT STREAM TEST")
        print(f"Camera ID: {self.camera_id}")
        print(f"YouTube URL: {self.youtube_url}")
        print("Press Ctrl+C to stop")
        print("=" * 60)
        
        try:
            # Step 1: Register stream
            print("\n=== STEP 1: Register Stream ===")
            self.stop_event = _register_stream(self.camera_id)
            print(f"[SUCCESS] Stream registered for camera {self.camera_id}")
            
            # Step 2: Start CV2 capture
            print("\n=== STEP 2: Start CV2 Capture ===")
            
            # For YouTube, we'll use webcam since CV2 can't directly read YouTube
            print("[INFO] YouTube URL detected, using webcam (0) for testing")
            self.cap = cv2.VideoCapture(0)
            
            if not self.cap.isOpened():
                print("[ERROR] Failed to open webcam")
                return
            
            print("[SUCCESS] Webcam opened")
            
            # Step 3: Test frames
            print("\n=== STEP 3: Test Frame Capture ===")
            frame_count = 0
            for i in range(5):
                ret, frame = self.cap.read()
                if ret:
                    frame_count += 1
                    h, w = frame.shape[:2]
                    print(f"[TEST] Frame {frame_count}: {w}x{h}")
                    
                    # Convert to bytes and update stream manager
                    _, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
                    frame_bytes = buffer.tobytes()
                    
                    stream_manager.update_frame(self.camera_id, frame_bytes, frame_count)
                    print(f"[TEST] Frame {frame_count} stored: {len(frame_bytes)} bytes")
                    
                    await asyncio.sleep(0.1)
                else:
                    print("[ERROR] Failed to read frame")
                    break
            
            print(f"[SUCCESS] Captured {frame_count} test frames")
            
            # Step 4: Continuous streaming
            print("\n=== STEP 4: Start Continuous Streaming ===")
            print(f"\n✅ Stream started successfully!")
            print(f"📹 MJPEG Stream: http://localhost:8000/api/dashboard/mjpeg/{self.camera_id}")
            print(f"🔍 Detections: http://localhost:8000/api/dashboard/latest-detections/{self.camera_id}")
            print("\n🔄 Streaming... Press Ctrl+C to stop")
            
            frame_count = 0
            start_time = time.time()
            
            while not self.stop_event.is_set():
                ret, frame = self.cap.read()
                if ret:
                    frame_count += 1
                    
                    # Convert to bytes and update stream manager
                    _, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
                    frame_bytes = buffer.tobytes()
                    
                    stream_manager.update_frame(self.camera_id, frame_bytes, frame_count)
                    
                    # Log every 30 frames (~1 second for 30fps)
                    if frame_count % 30 == 0:
                        elapsed = time.time() - start_time
                        fps = frame_count / elapsed
                        print(f"📡 Stream active... Frame #{frame_count}, FPS: {fps:.1f}, Size: {len(frame_bytes)} bytes")
                    
                    await asyncio.sleep(0.033)  # ~30fps
                else:
                    print("[WARNING] Failed to read frame, trying to reopen...")
                    self.cap.release()
                    await asyncio.sleep(1)
                    self.cap = cv2.VideoCapture(0)
            
        except KeyboardInterrupt:
            print("\n🛑 Stopping stream...")
        except Exception as e:
            print(f"\n💥 Error: {e}")
        finally:
            # Cleanup
            print("\n=== STEP 5: Cleanup ===")
            if self.cap:
                self.cap.release()
                print("✅ Webcam released")
            
            if self.camera_id in _ACTIVE_STREAMS:
                _unregister_stream(self.camera_id)
                print("✅ Stream unregistered")
            
            print("✅ Cleanup completed")


async def main():
    """Main test runner"""
    tester = YouTubeStreamTester()
    await tester.test_youtube_stream()


if __name__ == "__main__":
    asyncio.run(main())
