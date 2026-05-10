#!/usr/bin/env python3
"""
Simple Stream Test - CV2 Capture without AI Processing
Tests basic MJPEG streaming functionality by capturing frames and sending to stream manager.
"""

import asyncio
import sys
import time
import cv2
from pathlib import Path
from typing import Optional

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from src.services.stream_manager import stream_manager
from src.api.video_controller import _ACTIVE_STREAMS, _register_stream, _unregister_stream

class SimpleStreamTester:
    """
    Simple stream tester without AI processing
    """
    
    def __init__(self):
        self.camera_id = "11"
        self.source_url = None
        self.stop_event = None
        self.cap = None
        self.test_results = {}
    
    def log_step(self, step_name: str, status: str, details: str = None):
        """Log test step results"""
        timestamp = time.strftime("%H:%M:%S", time.localtime())
        result = {
            "timestamp": timestamp,
            "status": status,
            "details": details
        }
        self.test_results[step_name] = result
        print(f"[{timestamp}] {step_name}: {status}")
        if details:
            print(f"    Details: {details}")
    
    async def step_1_get_rtsp_url(self):
        """Step 1: Get RTSP URL from database"""
        print("\n=== STEP 1: Get RTSP URL ===")
        
        try:
            from src.services.database import DatabaseService
            db = DatabaseService()
            db._ensure_connection()
            
            with db.conn.cursor() as cur:
                cur.execute("SELECT source_url FROM cameras WHERE id = %s", (self.camera_id,))
                row = cur.fetchone()
            
            if row and row[0]:
                self.source_url = row[0]
                self.log_step("rtsp_url_retrieval", "SUCCESS", f"Source URL: {self.source_url}")
                return True
            else:
                self.log_step("rtsp_url_retrieval", "ERROR", f"No source URL found for camera {self.camera_id}")
                return False
                
        except Exception as e:
            self.log_step("rtsp_url_retrieval", "ERROR", str(e))
            return False
    
    async def step_2_register_stream(self):
        """Step 2: Register stream in active streams"""
        print("\n=== STEP 2: Register Stream ===")
        
        try:
            self.stop_event = _register_stream(self.camera_id)
            self.log_step("stream_registration", "SUCCESS", f"Stream registered, stop_event: {self.stop_event}")
            return True
        except Exception as e:
            self.log_step("stream_registration", "ERROR", str(e))
            return False
    
    async def step_3_test_cv2_capture(self):
        """Step 3: Test CV2 capture without AI"""
        print("\n=== STEP 3: Test CV2 Capture ===")
        
        try:
            print(f"[DEBUG] Opening video source: {self.source_url}")
            
            # Handle YouTube URL
            if "youtube.com" in self.source_url or "youtu.be" in self.source_url:
                # For YouTube, we'll use a test video file or webcam
                print("[DEBUG] YouTube URL detected, using webcam (0) for testing")
                self.cap = cv2.VideoCapture(0)
            else:
                self.cap = cv2.VideoCapture(self.source_url)
            
            if not self.cap.isOpened():
                self.log_step("cv2_capture", "ERROR", "Failed to open video source")
                return False
            
            # Test reading a few frames
            frame_count = 0
            start_time = time.time()
            
            while frame_count < 10 and time.time() - start_time < 5:  # Max 5 seconds
                ret, frame = self.cap.read()
                if ret:
                    frame_count += 1
                    print(f"[DEBUG] Frame {frame_count}: {frame.shape}")
                    
                    # Convert to bytes and update stream manager
                    _, buffer = cv2.imencode('.jpg', frame)
                    frame_bytes = buffer.tobytes()
                    
                    stream_manager.update_frame(self.camera_id, frame_bytes, frame_count)
                    print(f"[DEBUG] Frame {frame_count} stored for camera {self.camera_id}, size: {len(frame_bytes)} bytes")
                    
                    await asyncio.sleep(0.1)  # Small delay
                else:
                    print("[DEBUG] Failed to read frame")
                    break
            
            self.log_step("cv2_capture", "SUCCESS", f"Captured {frame_count} frames")
            return True
            
        except Exception as e:
            self.log_step("cv2_capture", "ERROR", str(e))
            return False
    
    async def step_4_start_continuous_stream(self):
        """Step 4: Start continuous streaming"""
        print("\n=== STEP 4: Start Continuous Stream ===")
        
        try:
            if not self.cap:
                self.cap = cv2.VideoCapture(self.source_url if "youtube.com" not in self.source_url else 0)
            
            if not self.cap.isOpened():
                self.log_step("continuous_stream", "ERROR", "Cannot open video source")
                return False
            
            print("\n✅ Stream started successfully!")
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
                    print("[DEBUG] Failed to read frame, trying to reopen...")
                    self.cap.release()
                    await asyncio.sleep(1)
                    self.cap = cv2.VideoCapture(self.source_url if "youtube.com" not in self.source_url else 0)
            
            self.log_step("continuous_stream", "SUCCESS", f"Streamed {frame_count} frames")
            return True
            
        except Exception as e:
            self.log_step("continuous_stream", "ERROR", str(e))
            return False
    
    async def step_5_cleanup(self):
        """Step 5: Cleanup resources"""
        print("\n=== STEP 5: Cleanup ===")
        
        try:
            if self.cap:
                self.cap.release()
                print("✅ Video capture released")
            
            if self.camera_id in _ACTIVE_STREAMS:
                _unregister_stream(self.camera_id)
                print("✅ Stream unregistered")
            
            self.log_step("cleanup", "SUCCESS", "All resources cleaned up")
            return True
            
        except Exception as e:
            self.log_step("cleanup", "ERROR", str(e))
            return False
    
    async def run_test(self):
        """Run the complete simple stream test"""
        print("=" * 60)
        print("SIMPLE STREAM TEST (No AI Processing)")
        print(f"Camera ID: {self.camera_id}")
        print("Press Ctrl+C to stop")
        print("=" * 60)
        
        steps = [
            ("rtsp_url_retrieval", self.step_1_get_rtsp_url),
            ("stream_registration", self.step_2_register_stream),
            ("cv2_capture", self.step_3_test_cv2_capture),
            ("continuous_stream", self.step_4_start_continuous_stream),
            ("cleanup", self.step_5_cleanup),
        ]
        
        for step_name, step_func in steps:
            try:
                success = await step_func()
                if not success and step_name != "cleanup":
                    print(f"\n❌ FAILED at step: {step_name}")
                    break
            except KeyboardInterrupt:
                print(f"\n🛑 Interrupted at step: {step_name}")
                await self.step_5_cleanup()
                break
            except Exception as e:
                print(f"\n💥 EXCEPTION at step {step_name}: {e}")
                self.log_step(step_name, "EXCEPTION", str(e))
                await self.step_5_cleanup()
                break
        
        print("\n" + "=" * 60)
        print("TEST SUMMARY")
        print("=" * 60)
        
        for step_name, result in self.test_results.items():
            status_symbol = "✅" if result["status"] == "SUCCESS" else "❌" if result["status"] == "ERROR" else "⚠️"
            print(f"{status_symbol} {step_name}: {result['status']}")
            if result["details"]:
                print(f"    {result['details']}")
        
        return self.test_results


async def main():
    """Main test runner"""
    tester = SimpleStreamTester()
    await tester.run_test()


if __name__ == "__main__":
    asyncio.run(main())
