#!/usr/bin/env python3
"""
Standalone YouTube Stream Server - Fixed Version
Complete self-contained server with minimal dependencies
Only uses yt-dlp for YouTube URL resolution
"""

import asyncio
import sys
import time
import cv2
import subprocess
import re
from pathlib import Path
from typing import Dict, Optional
from collections import defaultdict
import threading

# FastAPI imports
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse
import uvicorn
import json
import base64

# Global frame storage
_frame_storage: Dict[str, bytes] = {}
_frame_counter: Dict[str, int] = defaultdict(int)

# WebSocket connection management
_websocket_connections: Dict[str, set] = defaultdict(set)

class StandaloneYouTubeServer:
    """Standalone YouTube streaming server"""
    
    def __init__(self, use_youtube=False):
        self.camera_id = "11"
        self.ip_url = "http://10.102.190.89:8080/video"
        self.youtube_url = "https://www.youtube.com/watch?v=VR-x3HdhKLQ"
        
        # Easy switching between sources
        self.use_youtube = use_youtube
        self.current_url = self.youtube_url if use_youtube else self.ip_url
        
        self.stop_event = asyncio.Event()
        self.cap = None
        self.stream_task = None
        self.app = FastAPI(title="YouTube Stream Server")
        self._setup_routes()
    
    def _setup_routes(self):
        """Setup FastAPI routes"""
        
        @self.app.get("/")
        async def root():
            return {
                "message": "YouTube Stream Server",
                "endpoints": {
                    "mjpeg": f"/mjpeg/{self.camera_id}",
                    "info": f"/info/{self.camera_id}",
                    "websocket": f"/ws/{self.camera_id}"
                }
            }
        
        @self.app.get("/mjpeg/{camera_id}")
        async def mjpeg_stream(camera_id: str):
            """Stream MJPEG video"""
            return StreamingResponse(
                self._mjpeg_generator(camera_id),
                media_type="multipart/x-mixed-replace; boundary=frame",
                headers={
                    "Cache-Control": "no-cache, no-store, must-revalidate, max-age=0",
                    "Pragma": "no-cache",
                    "Expires": "0",
                    "Connection": "close",
                }
            )
        
        @self.app.get("/info/{camera_id}")
        async def stream_info(camera_id: str):
            """Get stream information"""
            frame_available = camera_id in _frame_storage
            frame_count = _frame_counter.get(camera_id, 0)
            
            return {
                "camera_id": camera_id,
                "stream_active": frame_available,
                "frame_count": frame_count,
                "source_url": self.current_url if camera_id == self.camera_id else None,
                "source_type": "youtube" if self.use_youtube else "ip_camera"
            }
        
        @self.app.websocket("/ws/{camera_id}")
        async def websocket_stream(websocket: WebSocket, camera_id: str):
            """WebSocket streaming endpoint"""
            await websocket.accept()
            print(f"[WebSocket] Client connected to camera {camera_id}")
            
            # Add connection to the set
            _websocket_connections[camera_id].add(websocket)
            
            try:
                while not self.stop_event.is_set():
                    frame_bytes = _frame_storage.get(camera_id)
                    
                    if frame_bytes:
                        # Convert frame to base64 for JSON transmission
                        frame_base64 = base64.b64encode(frame_bytes).decode('utf-8')
                        
                        # Send frame data as JSON
                        message = {
                            "type": "frame",
                            "camera_id": camera_id,
                            "frame": frame_base64,
                            "timestamp": time.time(),
                            "frame_count": _frame_counter.get(camera_id, 0)
                        }
                        
                        try:
                            await websocket.send_json(message)
                        except Exception as e:
                            print(f"[WebSocket] Error sending frame: {e}")
                            break
                    
                    await asyncio.sleep(1/30)  # ~30 FPS
                    
            except WebSocketDisconnect:
                print(f"[WebSocket] Client disconnected from camera {camera_id}")
            except Exception as e:
                print(f"[WebSocket] Error: {e}")
            finally:
                # Remove connection from the set
                _websocket_connections[camera_id].discard(websocket)
                print(f"[WebSocket] Connection removed for camera {camera_id}")
    
    async def _mjpeg_generator(self, camera_id: str):
        """Generate MJPEG frames"""
        print(f"[MJPEG] Starting stream for camera {camera_id}")
        
        while not self.stop_event.is_set():
            frame_bytes = _frame_storage.get(camera_id)
            
            if frame_bytes:
                yield (
                    b"--frame\r\n"
                    b"Content-Type: image/jpeg\r\n\r\n"
                    + frame_bytes
                    + b"\r\n"
                )
            else:
                # Send placeholder if no frame available
                await asyncio.sleep(0.1)
                continue
            
            await asyncio.sleep(1/30)  # ~30 FPS
    
    def get_youtube_stream_url(self, youtube_url):
        """Extract direct stream URL from YouTube using yt-dlp"""
        try:
            print("🎬 Extracting YouTube stream URL...")
            
            cmd = [
                'yt-dlp', 
                '--format', 'best[height<=720]',
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
        """Start camera streaming in background"""
        try:
            print("🎬 Starting YouTube camera streaming...")
            
            # Extract stream URL based on source type
            if self.use_youtube and ("youtube.com" in self.current_url or "youtu.be" in self.current_url):
                stream_url = self.get_youtube_stream_url(self.current_url)
                if not stream_url:
                    print("❌ Failed to extract YouTube stream URL")
                    return
            else:
                stream_url = self.current_url
            
            print(f"📹 Opening stream: {stream_url}")
            
            # Open video capture
            self.cap = cv2.VideoCapture(stream_url)
            
            # Optimize capture settings
            self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            self.cap.set(cv2.CAP_PROP_FPS, 30)
            self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
            self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
            
            # Get camera capabilities
            actual_fps = self.cap.get(cv2.CAP_PROP_FPS)
            width = self.cap.get(cv2.CAP_PROP_FRAME_WIDTH)
            height = self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT)
            print(f"📹 Camera specs: {width}x{height} @ {actual_fps:.1f} FPS")
            
            # Test connection
            ret, test_frame = self.cap.read()
            if not ret or not self.cap.isOpened():
                print("❌ Failed to open stream")
                return
            
            print(f"✅ Stream opened successfully")
            
            # Stream frames continuously
            frame_count = 0
            start_time = time.time()
            
            while not self.stop_event.is_set():
                ret, frame = self.cap.read()
                if ret:
                    frame_count += 1
                    _frame_counter[self.camera_id] = frame_count
                    
                    # Convert to bytes
                    _, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 25])
                    frame_bytes = buffer.tobytes()
                    
                    # Store frame globally
                    _frame_storage[self.camera_id] = frame_bytes
                    
                    # Log progress
                    if frame_count % 60 == 0:
                        elapsed = time.time() - start_time
                        fps = frame_count / elapsed
                        print(f"📡 Frame #{frame_count} | FPS: {fps:.1f} | Size: {len(frame_bytes)} bytes")
                else:
                    print("⚠️ Failed to read frame, retrying...")
                    await asyncio.sleep(0.1)
            
        except Exception as e:
            print(f"💥 Stream error: {e}")
        finally:
            if self.cap:
                self.cap.release()
                print("✅ Camera stream released")
    
    def start_server_sync(self):
        """Start the complete server using synchronous approach"""
        print("=" * 60)
        print("STANDALONE YOUTUBE STREAM SERVER")
        print(f"🌐 API: http://localhost:8001")
        print(f"📹 MJPEG: http://localhost:8001/mjpeg/{self.camera_id}")
        print(f"🔍 Info: http://localhost:8001/info/{self.camera_id}")
        print(f"🔌 WebSocket: ws://localhost:8001/ws/{self.camera_id}")
        print(f"📹 Source: {self.current_url} ({'YouTube' if self.use_youtube else 'IP Camera'})")
        print("Press Ctrl+C to stop")
        print("=" * 60)
        
        # Start camera streaming in background thread
        def run_camera_stream():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(self.start_camera_stream())
            loop.close()
        
        self.stream_thread = threading.Thread(target=run_camera_stream, daemon=True)
        self.stream_thread.start()
        
        # Wait a moment for stream to start
        time.sleep(2)
        
        # Start API server
        try:
            print("🚀 Starting HTTP server...")
            uvicorn.run(
                self.app,
                host="localhost",
                port=8001,
                log_level="info"
            )
            
        except KeyboardInterrupt:
            print("\n🛑 Shutting down...")
        finally:
            self.cleanup_sync()
    
    def cleanup_sync(self):
        """Cleanup resources"""
        print("🧹 Cleaning up...")
        
        # Stop camera stream
        self.stop_event.set()
        
        # Close WebSocket connections
        for camera_id, connections in _websocket_connections.items():
            for websocket in connections.copy():
                try:
                    # Close WebSocket connection
                    asyncio.create_task(websocket.close())
                except:
                    pass
            connections.clear()
        
        # Clear frame storage
        _frame_storage.clear()
        _frame_counter.clear()
        _websocket_connections.clear()
        
        print("✅ Cleanup complete")

def main():
    """Main function"""
    # Set to True to use YouTube, False to use IP Camera
    use_youtube = False   # <-- CHANGE THIS TO SWITCH SOURCES
    
    server = StandaloneYouTubeServer(use_youtube=use_youtube)
    server.start_server_sync()

if __name__ == "__main__":
    main()
