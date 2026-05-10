#!/usr/bin/env python3
"""
Pure Stream Test - Only CV2 Capture + Stream Manager
No AI processing, no YOLO, no color analysis.
Just capture frames and send to stream manager.
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

class PureStreamTester:
    """
    Pure stream tester - CV2 capture only
    """
    
    def __init__(self):
        self.camera_id = "11"
        self.source_url = None
        self.stop_event = None
        self.cap = None
    
    async def test_pure_stream(self):
        """Test pure streaming without AI"""
        print("=" * 60)
        print("PURE STREAM TEST (No AI Processing)")
        print(f"Camera ID: {self.camera_id}")
        print("Press Ctrl+C to stop")
        print("=" * 60)
        
        try:
            # Step 1: Get RTSP URL
            print("\n=== STEP 1: Get RTSP URL ===")
            from src.services.database import DatabaseService
            db = DatabaseService()
            db._ensure_connection()
            
            with db.conn.cursor() as cur:
                cur.execute("SELECT source_url FROM cameras WHERE id = %s", (self.camera_id,))
                row = cur.fetchone()
            
            if row and row[0]:
                self.source_url = row[0]
                print(f"[SUCCESS] RTSP URL: {self.source_url}")
            else:
                print(f"[ERROR] No RTSP URL found for camera {self.camera_id}")
                return
            
            # Step 2: Register stream
            print("\n=== STEP 2: Register Stream ===")
            self.stop_event = _register_stream(self.camera_id)
            print(f"[SUCCESS] Stream registered")
            
            # Step 3: Test CV2 capture
            print("\n=== STEP 3: Test CV2 Capture ===")
            
            # Handle YouTube URL - use webcam for testing
            if "youtube.com" in self.source_url:
                print("[INFO] YouTube URL detected, using webcam (0) for testing")
                self.cap = cv2.VideoCapture(0)
            else:
                print(f"[INFO] Opening video source: {self.source_url}")
                self.cap = cv2.VideoCapture(self.source_url)
            
            if not self.cap.isOpened():
                print("[ERROR] Failed to open video source")
                return
            
            print("[SUCCESS] Video source opened")
            
            # Test a few frames
            frame_count = 0
            for i in range(10):
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
            print(f"📹 MJPEG Stream available at: http://localhost:8000/api/dashboard/mjpeg/{self.camera_id}")
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
                    self.cap = cv2.VideoCapture(self.source_url if "youtube.com" not in self.source_url else 0)
            
        except KeyboardInterrupt:
            print("\n🛑 Stopping stream...")
        except Exception as e:
            print(f"\n💥 Error: {e}")
        finally:
            # Cleanup
            print("\n=== STEP 5: Cleanup ===")
            if self.cap:
                self.cap.release()
                print("✅ Video capture released")
            
            if self.camera_id in _ACTIVE_STREAMS:
                _unregister_stream(self.camera_id)
                print("✅ Stream unregistered")
            
            print("✅ Cleanup completed")


async def main():
    """Main test runner"""
    tester = PureStreamTester()
    await tester.test_pure_stream()


if __name__ == "__main__":
    asyncio.run(main())
