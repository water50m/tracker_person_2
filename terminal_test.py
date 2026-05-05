#!/usr/bin/env python3
"""
Terminal Testing Script - ทดสอบระบบ Re-ID Tracking ผ่าน Terminal
ไม่ต้องเปิด Frontend ก็ใช้งานได้
"""
import requests
import json
import time
import sys
from datetime import datetime

BASE_URL = "http://localhost:8000"

class Colors:
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    END = '\033[0m'

def print_header(text):
    print(f"\n{Colors.BLUE}{'='*60}{Colors.END}")
    print(f"{Colors.BLUE}{text:^60}{Colors.END}")
    print(f"{Colors.BLUE}{'='*60}{Colors.END}\n")

def print_success(text):
    print(f"{Colors.GREEN}✅ {text}{Colors.END}")

def print_error(text):
    print(f"{Colors.RED}❌ {text}{Colors.END}")

def print_warning(text):
    print(f"{Colors.YELLOW}⚠️  {text}{Colors.END}")

def print_info(text):
    print(f"  ℹ️  {text}")

def test_server_connection():
    """1. ตรวจสอบว่า server ทำงานอยู่"""
    print_header("STEP 1: CHECKING SERVER CONNECTION")
    try:
        response = requests.get(f"{BASE_URL}/api/dashboard/cameras", timeout=3)
        if response.status_code == 200:
            print_success("Server is running!")
            return True
        else:
            print_error(f"Server returned status {response.status_code}")
            return False
    except requests.exceptions.ConnectionError:
        print_error("Cannot connect to server")
        print_info("Please start the server with: uvicorn src.api.main:app --port 8000")
        return False
    except Exception as e:
        print_error(f"Error: {e}")
        return False

def test_database_connection():
    """2. ตรวจสอบการเชื่อมต่อ Database"""
    print_header("STEP 2: CHECKING DATABASE CONNECTION")
    try:
        response = requests.get(f"{BASE_URL}/api/video/detections?limit=1", timeout=5)
        if response.status_code == 200:
            print_success("Database connection OK")
            return True
        else:
            print_warning("Database might not be connected properly")
            return False
    except Exception as e:
        print_error(f"Database check failed: {e}")
        return False

def test_camera_list():
    """3. ดูรายการกล้อง"""
    print_header("STEP 3: LISTING CAMERAS")
    try:
        response = requests.get(f"{BASE_URL}/api/dashboard/cameras")
        cameras = response.json()
        
        if cameras:
            print_success(f"Found {len(cameras)} cameras:")
            for cam in cameras:
                status = "🟢 Active" if cam.get('is_active') else "🔴 Inactive"
                print(f"    • {cam.get('camera_id', 'N/A')}: {cam.get('label', 'Unnamed')} - {status}")
        else:
            print_warning("No cameras configured yet")
            print_info("Add a camera via frontend or API")
        return cameras
    except Exception as e:
        print_error(f"Failed to get cameras: {e}")
        return []

def test_video_upload(video_path, camera_id="TEST-CAM-01", label="Test Camera"):
    """4. อัปโหลดวิดีโอทดสอบ"""
    print_header("STEP 4: UPLOADING TEST VIDEO")
    
    import os
    if not os.path.exists(video_path):
        print_error(f"Video file not found: {video_path}")
        print_info("Usage: python terminal_test.py upload <video_path>")
        return None
    
    try:
        print_info(f"Uploading: {video_path}")
        print_info(f"Camera ID: {camera_id}")
        
        with open(video_path, 'rb') as f:
            files = {'file': f}
            data = {'camera_id': camera_id, 'label': label}
            
            response = requests.post(
                f"{BASE_URL}/api/video/analyze/upload",
                files=files,
                data=data
            )
        
        if response.status_code == 200:
            result = response.json()
            print_success("Video uploaded successfully!")
            print_info(f"Video ID: {result.get('video_id')}")
            print_info(f"Status: {result.get('status')}")
            return result
        else:
            print_error(f"Upload failed: {response.text}")
            return None
    except Exception as e:
        print_error(f"Upload error: {e}")
        return None

def test_active_streams():
    """5. ดู Active Streams"""
    print_header("STEP 5: CHECKING ACTIVE STREAMS")
    try:
        response = requests.get(f"{BASE_URL}/api/video/active-streams")
        streams = response.json()
        
        if streams:
            print_success(f"{len(streams)} active stream(s):")
            for stream in streams:
                print(f"    • Camera: {stream.get('camera_id')}")
                print(f"      Status: {stream.get('status')}")
                print(f"      URL: {stream.get('url', 'N/A')}")
        else:
            print_warning("No active streams")
        return streams
    except Exception as e:
        print_error(f"Failed to get streams: {e}")
        return []

def test_recent_detections(limit=10):
    """6. ดู Detections ล่าสุด"""
    print_header("STEP 6: RECENT DETECTIONS")
    try:
        response = requests.get(f"{BASE_URL}/api/video/detections?limit={limit}")
        detections = response.json()
        
        if detections:
            print_success(f"Found {len(detections)} detections:")
            for det in detections[:5]:  # Show first 5
                cam_id = det.get('camera_id', 'N/A')
                class_name = det.get('class_name', 'Unknown')
                color = det.get('primary_detailed_color', 'N/A')
                track_id = det.get('track_id', 'N/A')
                
                print(f"    • ID:{track_id} | {class_name} | Color: {color} | Cam: {cam_id}")
        else:
            print_warning("No detections found")
            print_info("Process a video first or wait for stream")
        return detections
    except Exception as e:
        print_error(f"Failed to get detections: {e}")
        return []

def test_search_person(clothing=None, color=None):
    """7. ทดสอบการค้นหาคน"""
    print_header("STEP 7: SEARCHING PERSONS")
    
    params = {}
    if clothing:
        params['clothing'] = clothing
    if color:
        params['color'] = color
    
    try:
        print_info(f"Search params: {params}")
        response = requests.get(f"{BASE_URL}/api/search/persons", params=params)
        
        if response.status_code == 200:
            results = response.json()
            print_success(f"Found {len(results)} matches")
            
            for person in results[:5]:
                print(f"    • Track ID: {person.get('track_id')}")
                print(f"      Clothing: {person.get('clothes', 'N/A')}")
                print(f"      Color: {person.get('primary_detailed_color', 'N/A')}")
        elif response.status_code == 404:
            print_warning("No matches found")
        else:
            print_error(f"Search failed: {response.text}")
    except Exception as e:
        print_error(f"Search error: {e}")

def test_sse_stream(duration=10):
    """8. ทดสอบ Real-time Events (SSE)"""
    print_header(f"STEP 8: TESTING REAL-TIME EVENTS ({duration}s)")
    
    try:
        print_info("Connecting to SSE stream...")
        response = requests.get(
            f"{BASE_URL}/api/events/stream",
            stream=True,
            timeout=duration + 5
        )
        
        if response.status_code != 200:
            print_error(f"Cannot connect: {response.status_code}")
            return
        
        print_success("Connected! Waiting for events...")
        print_info("Press Ctrl+C to stop early")
        
        start_time = time.time()
        event_count = 0
        
        for line in response.iter_lines():
            if line:
                line = line.decode('utf-8')
                if line.startswith('data: '):
                    try:
                        data = json.loads(line[6:])
                        event_type = data.get('type', 'unknown')
                        
                        if event_type == 'connected':
                            print_success("Stream connected")
                        elif event_type == 'detection':
                            event_count += 1
                            cam_id = data.get('camera_id')
                            count = data.get('payload', {}).get('count', 0)
                            print(f"  📹 Detection event: Camera {cam_id}, {count} person(s)")
                        elif event_type == 'heartbeat':
                            print("  💓 Heartbeat received")
                            
                    except json.JSONDecodeError:
                        pass
            
            if time.time() - start_time > duration:
                print_success(f"Received {event_count} detection events in {duration}s")
                break
                
    except KeyboardInterrupt:
        print(f"\n{Colors.YELLOW}Stopped by user{Colors.END}")
    except Exception as e:
        print_error(f"SSE error: {e}")

def test_system_stats():
    """9. ดูสถิติระบบ"""
    print_header("STEP 9: SYSTEM STATISTICS")
    try:
        # Get detection counts
        response = requests.get(f"{BASE_URL}/api/video/detections?limit=1")
        
        if response.status_code == 200:
            print_success("System is operational")
            
            # Try to get more stats if available
            try:
                stats_response = requests.get(f"{BASE_URL}/api/dashboard/stats")
                if stats_response.status_code == 200:
                    stats = stats_response.json()
                    print_info(f"Total videos: {stats.get('total_videos', 'N/A')}")
                    print_info(f"Total detections: {stats.get('total_detections', 'N/A')}")
                    print_info(f"Active cameras: {stats.get('active_cameras', 'N/A')}")
            except:
                pass
        else:
            print_warning("System might be initializing")
    except Exception as e:
        print_error(f"Stats error: {e}")

def run_full_test(video_path=None):
    """รันการทดสอบทั้งหมด"""
    print_header("🚀 RE-ID TRACKING SYSTEM - TERMINAL TEST")
    print(f"  Server: {BASE_URL}")
    print(f"  Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
    
    # Check server
    if not test_server_connection():
        sys.exit(1)
    
    # Check database
    test_database_connection()
    
    # List cameras
    cameras = test_camera_list()
    
    # Check active streams
    test_active_streams()
    
    # Upload video if provided
    if video_path:
        camera_id = input("Enter camera ID (default: TEST-CAM-01): ").strip() or "TEST-CAM-01"
        label = input("Enter camera label (default: Test Camera): ").strip() or "Test Camera"
        test_video_upload(video_path, camera_id, label)
    
    # Show recent detections
    test_recent_detections()
    
    # Test search
    clothing = input("\nEnter clothing type to search (or press Enter to skip): ").strip()
    if clothing:
        color = input("Enter color (or press Enter to skip): ").strip()
        test_search_person(clothing, color or None)
    
    # Test SSE
    print("\n" + "="*60)
    sse_choice = input("Test real-time events? (y/n): ").strip().lower()
    if sse_choice == 'y':
        duration = input("How many seconds? (default 10): ").strip()
        test_sse_stream(int(duration) if duration.isdigit() else 10)
    
    # Final stats
    test_system_stats()
    
    print_header("✨ TEST COMPLETED")
    print_info("Use Ctrl+C to stop any streaming")
    print_info("Server URL: http://localhost:8000/docs for API documentation")

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='Test Re-ID Tracking System via Terminal')
    parser.add_argument('command', nargs='?', choices=['full', 'upload', 'search', 'stream', 'status'], 
                       help='Test command to run')
    parser.add_argument('--video', '-v', help='Path to video file')
    parser.add_argument('--camera-id', '-c', default='TEST-CAM-01', help='Camera ID')
    parser.add_argument('--label', '-l', default='Test Camera', help='Camera label')
    parser.add_argument('--clothing', help='Clothing type to search')
    parser.add_argument('--color', help='Color to search')
    
    args = parser.parse_args()
    
    if args.command == 'upload' and args.video:
        test_video_upload(args.video, args.camera_id, args.label)
    elif args.command == 'search':
        test_search_person(args.clothing, args.color)
    elif args.command == 'stream':
        test_sse_stream(30)
    elif args.command == 'status':
        test_server_connection()
        test_database_connection()
        test_camera_list()
        test_active_streams()
        test_recent_detections()
    else:
        # Full interactive test
        video = args.video if args.video else None
        run_full_test(video)
