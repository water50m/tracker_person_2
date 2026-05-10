#!/usr/bin/env python3
"""
YouTube Stream Server - Persistent API Server with Built-in Streaming
Starts API server and automatically streams camera 11 from YouTube URL
Runs continuously until manually stopped.
"""

import asyncio
import sys
import time
import cv2
from pathlib import Path
import subprocess
import re

# IP Camera streaming - no need for yt-dlp
IP_CAMERA_SUPPORT = True
print("✅ Using direct IP camera streaming")

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from src.services.stream_manager import stream_manager
from src.api.video_controller import _ACTIVE_STREAMS, _register_stream, _unregister_stream
from src.api.main import app

class YouTubeStreamServer:
    """
    Persistent YouTube streaming server
    """
    
    def __init__(self):
        self.camera_id = "11"
        self.ip_url = "http://10.102.190.89:8080/video"
        self.youtube_url = "https://www.youtube.com/watch?v=VR-x3HdhKLQ"
        self.stop_event = None
        self.cap = None
        self.stream_task = None
    
    def get_youtube_stream_url(self, youtube_url):
        """Extract direct stream URL from YouTube using yt-dlp"""
        try:
            print("🎬 Extracting YouTube stream URL...")
            
            # Use yt-dlp to get the direct URL
            cmd = [
                'yt-dlp', 
                '--format', 'best[height<=720]',  # Limit to 720p for better performance
                '--get-url',
                '--no-playlist',
                youtube_url
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            
            if result.returncode == 0:
                stream_url = result.stdout.strip()
                if stream_url:
                    print(f"✅ YouTube stream extracted: {stream_url[:100]}...")
                    return stream_url
                else:
                    print("❌ No stream URL found")
                    return None
            else:
                print(f"❌ yt-dlp error: {result.stderr}")
                return None
                
        except subprocess.TimeoutExpired:
            print("❌ yt-dlp timeout")
            return None
        except Exception as e:
            print(f"❌ Error extracting YouTube URL: {e}")
            return None
    
    async def start_camera_stream(self):
        """Start camera 11 streaming in background"""
        try:
            print("🎬 Starting IP camera streaming...")
            
            # Register stream
            self.stop_event = _register_stream(self.camera_id)
            print(f"✅ Stream registered for camera {self.camera_id}")
            
            # Use IP camera URL directly
            stream_url = self.ip_url
            print(f"📹 Using IP camera: {stream_url}")
            
            print(f"📹 Opening stream: {stream_url}")
            
            # Try different connection methods
            connection_attempts = [
                stream_url,  # Original URL
            ]
            
            for i, url in enumerate(connection_attempts):
                print(f"🔄 Attempt {i+1}: Trying {url}")
                self.cap = cv2.VideoCapture(url)
                
                # Optimize capture settings for better FPS
                self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)  # Reduce buffer size
                self.cap.set(cv2.CAP_PROP_FPS, 30)  # Request higher FPS
                self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)  # Reduce resolution
                self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)  # Reduce resolution
                self.cap.set(cv2.CAP_PROP_AUTOFOCUS, 0)  # Disable autofocus
                self.cap.set(cv2.CAP_PROP_AUTO_EXPOSURE, 0.25)  # Manual exposure mode
                self.cap.set(cv2.CAP_PROP_EXPOSURE, -6)  # Lower exposure for faster capture
                
                # Get camera capabilities
                actual_fps = self.cap.get(cv2.CAP_PROP_FPS)
                width = self.cap.get(cv2.CAP_PROP_FRAME_WIDTH)
                height = self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT)
                print(f"📹 Camera specs: {width}x{height} @ {actual_fps:.1f} FPS")
                
                # Test if connection works by reading a frame
                ret, test_frame = self.cap.read()
                if ret and self.cap.isOpened():
                    print(f"✅ IP camera stream opened successfully with {url}")
                    break
                else:
                    self.cap.release()
                    print(f"❌ Attempt {i+1} failed")
                    if i == len(connection_attempts) - 1:
                        print("❌ All connection attempts failed")
                        print("💡 Check if IP camera is accessible and URL is correct")
                        print("💡 Try: curl -I http://10.33.99.31:8080/video")
                        return
            
            # Stream frames continuously
            frame_count = 0
            input_frame_count = 0
            start_time = time.time()
            last_input_time = time.time()
            input_fps = 0
            
            while not self.stop_event.is_set():
                ret, frame = self.cap.read()
                if ret:
                    frame_count += 1
                    input_frame_count += 1
                    
                    # Calculate input FPS (camera native rate)
                    current_time = time.time()
                    time_diff = current_time - last_input_time
                    if time_diff >= 1.0:  # Update every second
                        input_fps = input_frame_count / time_diff
                        input_frame_count = 0
                        last_input_time = current_time
                    
                    # Skip drawing to maximize FPS
                    # height, width = frame.shape[:2]
                    # center = (width // 2, height // 2)
                    # radius = 30  # Smaller radius for performance
                    # color = (0, 255, 0)  # Green
                    # thickness = 2  # Thinner line for performance
                    # cv2.circle(frame, center, radius, color, thickness)
                    # 
                    # # Add text label (smaller font for performance)
                    # cv2.putText(frame, "CIRCLE", (center[0] - 30, center[1] - 50), 
                    #            cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1)
                    
                    # Convert to bytes and update stream manager (optimized)
                    _, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 25])  # Lower quality for higher FPS
                    frame_bytes = buffer.tobytes()
                    
                    stream_manager.update_frame(self.camera_id, frame_bytes, frame_count)
                    
                    # Log every 60 frames (~2 seconds for 30fps)
                    if frame_count % 60 == 0:
                        elapsed = time.time() - start_time
                        output_fps = frame_count / elapsed
                        fps_diff = abs(output_fps - input_fps)
                        status = "✅ GOOD" if fps_diff < 5 else "⚠️ HIGH LATENCY"
                        # print(f"📡 Frame #{frame_count} | Input FPS: {input_fps:.1f} | Output FPS: {output_fps:.1f} | Diff: {fps_diff:.1f} {status} | Size: {len(frame_bytes)} bytes")
                    
                    # No sleep - process as fast as camera provides frames
                else:
                    print("⚠️ Failed to read frame, retrying...")
                    await asyncio.sleep(0.1)
            
        except Exception as e:
            print(f"💥 Stream error: {e}")
        finally:
            if self.cap:
                self.cap.release()
                print("✅ IP camera stream released")
    
    async def start_server(self):
        """Start API server with streaming"""
        print("=" * 60)
        print("IP CAMERA STREAM SERVER")
        print(f"🌐 API: http://localhost:8000")
        print(f"📹 Direct Video: http://localhost:8000/video")
        print(f"📹 MJPEG: http://localhost:8000/api/dashboard/mjpeg/{self.camera_id}")
        print(f"🔍 Detections: http://localhost:8000/api/dashboard/latest-detections/{self.camera_id}")
        print(f"📹 Source: {self.youtube_url}")
        print("Press Ctrl+C to stop")
        print("=" * 60)
        
        # Start camera streaming in background
        self.stream_task = asyncio.create_task(self.start_camera_stream())
        
        # Wait a moment for stream to start
        await asyncio.sleep(2)
        
        # Start API server
        import uvicorn
        
        try:
            config = uvicorn.Config(
                app=app,
                host="localhost",
                port=8000,
                log_level="info"
            )
            
            server = uvicorn.Server(config)
            await server.serve()
            
        except KeyboardInterrupt:
            print("\n🛑 Shutting down...")
        finally:
            # Cleanup
            await self.cleanup()
    
    async def cleanup(self):
        """Cleanup resources"""
        print("🧹 Cleaning up...")
        
        # Stop camera stream
        if self.stop_event:
            self.stop_event.set()
        
        # Cancel stream task
        if self.stream_task:
            self.stream_task.cancel()
            try:
                await self.stream_task
            except asyncio.CancelledError:
                pass
        
        # Unregister stream
        if self.camera_id in _ACTIVE_STREAMS:
            _unregister_stream(self.camera_id)
            print("✅ Stream unregistered")
        
        print("✅ Cleanup complete")

async def main():
    """Main function"""
    server = YouTubeStreamServer()
    await server.start_server()

if __name__ == "__main__":
    asyncio.run(main())
