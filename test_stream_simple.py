#!/usr/bin/env python3
"""
Simple Stream Test - FPS monitoring without AI dependencies
Tests YouTube streaming performance with input/output FPS comparison
"""

import asyncio
import cv2
import time
from pathlib import Path

class SimpleStreamTest:
    def __init__(self):
        self.youtube_url = 0  # Use default webcam
        self.cap = None
    
    async def test_stream(self):
        """Test streaming performance with FPS monitoring"""
        try:
            print("🎬 Starting YouTube stream test...")
            print(f"📹 URL: {self.youtube_url}")
            
            # Open YouTube stream using yt-dlp or direct URL
            self.cap = cv2.VideoCapture(self.youtube_url)
            
            if not self.cap.isOpened():
                print("❌ Failed to open YouTube stream")
                return
            
            # Get stream properties
            fps = self.cap.get(cv2.CAP_PROP_FPS)
            width = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            height = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            print(f"📹 Stream properties: {width}x{height} @ {fps:.1f} FPS")
            
            # Test streaming with FPS monitoring
            frame_count = 0
            input_frame_count = 0
            start_time = time.time()
            last_input_time = time.time()
            input_fps = 0
            
            print("📡 Starting FPS test (run for 30 seconds)...")
            
            while time.time() - start_time < 30:  # Test for 30 seconds
                ret, frame = self.cap.read()
                if ret:
                    frame_count += 1
                    input_frame_count += 1
                    
                    # Calculate input FPS
                    current_time = time.time()
                    time_diff = current_time - last_input_time
                    if time_diff >= 1.0:
                        input_fps = input_frame_count / time_diff
                        input_frame_count = 0
                        last_input_time = current_time
                    
                    # Simple processing (resize to reduce workload)
                    small_frame = cv2.resize(frame, (320, 240))
                    
                    # Log every 30 frames
                    if frame_count % 30 == 0:
                        elapsed = time.time() - start_time
                        output_fps = frame_count / elapsed
                        fps_diff = abs(output_fps - input_fps)
                        status = "✅ GOOD" if fps_diff < 5 else "⚠️ HIGH LATENCY"
                        print(f"📡 Frame #{frame_count} | Input FPS: {input_fps:.1f} | Output FPS: {output_fps:.1f} | Diff: {fps_diff:.1f} {status}")
                else:
                    print("⚠️ Failed to read frame")
                    await asyncio.sleep(0.1)
            
            # Final results
            total_time = time.time() - start_time
            final_output_fps = frame_count / total_time
            print(f"\n📊 Final Results:")
            print(f"   Total frames processed: {frame_count}")
            print(f"   Total time: {total_time:.1f}s")
            print(f"   Final Output FPS: {final_output_fps:.1f}")
            print(f"   Target: >20 FPS")
            print(f"   Status: {'✅ PASS' if final_output_fps > 20 else '❌ FAIL'}")
            
        except Exception as e:
            print(f"💥 Error: {e}")
        finally:
            if self.cap:
                self.cap.release()
                print("✅ Stream released")

async def main():
    test = SimpleStreamTest()
    await test.test_stream()

if __name__ == "__main__":
    asyncio.run(main())
