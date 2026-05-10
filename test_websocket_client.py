#!/usr/bin/env python3
"""
Simple WebSocket client to test the streaming server
"""

import asyncio
import websockets
import json
import base64
from PIL import Image
import io
import time

async def test_websocket_client():
    """Test WebSocket connection and frame reception"""
    uri = "ws://localhost:8001/ws/11"
    
    try:
        print(f"🔌 Connecting to WebSocket: {uri}")
        async with websockets.connect(uri) as websocket:
            print("✅ WebSocket connected!")
            
            frame_count = 0
            start_time = time.time()
            
            # Receive frames for 10 seconds
            while time.time() - start_time < 10:
                try:
                    message = await asyncio.wait_for(websocket.recv(), timeout=5.0)
                    data = json.loads(message)
                    
                    if data.get("type") == "frame":
                        frame_count += 1
                        timestamp = data.get("timestamp")
                        frame_num = data.get("frame_count")
                        
                        # Decode base64 frame
                        frame_data = base64.b64decode(data["frame"])
                        
                        print(f"📹 Frame #{frame_count} | Server Frame: {frame_num} | Size: {len(frame_data)} bytes | Timestamp: {timestamp}")
                        
                        # Optionally save first frame as image
                        if frame_count == 1:
                            try:
                                img = Image.open(io.BytesIO(frame_data))
                                img.save("test_frame.jpg")
                                print("💾 Saved first frame as test_frame.jpg")
                            except Exception as e:
                                print(f"⚠️ Could not save frame: {e}")
                    
                except asyncio.TimeoutError:
                    print("⏰ Timeout waiting for frame")
                    break
                except Exception as e:
                    print(f"❌ Error receiving frame: {e}")
                    break
            
            print(f"📊 Received {frame_count} frames in {time.time() - start_time:.1f} seconds")
            
    except Exception as e:
        print(f"❌ WebSocket connection error: {e}")

if __name__ == "__main__":
    print("🧪 Testing WebSocket Client")
    print("Make sure the server is running first!")
    print("=" * 50)
    
    asyncio.run(test_websocket_client())
