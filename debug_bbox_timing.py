"""
Debug script to verify bbox timing accuracy
ตรวจสอบว่า bbox ที่วาดตรงกับเวลาของวิดีโอหรือไม่
"""
import psycopg2
import os
from dotenv import load_dotenv

load_dotenv()

def check_bbox_timing(video_id: str):
    """ตรวจสอบความถูกต้องของ video_time_offset"""
    
    conn = psycopg2.connect(
        host=os.getenv("DB_HOST", "localhost"),
        port=os.getenv("DB_PORT", "5432"),
        database=os.getenv("DB_NAME", "nexus_eye"),
        user=os.getenv("DB_USER", "postgres"),
        password=os.getenv("DB_PASSWORD", "postgres")
    )
    
    try:
        with conn.cursor() as cur:
            # ดึงข้อมูลวิดีโอ
            cur.execute("""
                SELECT id, filename, file_path, camera_id 
                FROM processed_videos 
                WHERE id::text = %s
            """, (video_id,))
            video = cur.fetchone()
            
            if not video:
                print(f"❌ Video ID {video_id} not found")
                return
            
            print(f"\n📹 Video: {video[1]}")
            print(f"   Camera: {video[3]}")
            print(f"   Path: {video[2]}")
            
            # ดึง detections
            cur.execute("""
                SELECT 
                    id,
                    track_id,
                    video_time_offset,
                    class_name,
                    bbox,
                    timestamp
                FROM detections 
                WHERE video_id = %s 
                ORDER BY video_time_offset ASC
                LIMIT 10
            """, (video_id,))
            
            detections = cur.fetchall()
            
            if not detections:
                print(f"\n⚠️  No detections found for this video")
                return
            
            print(f"\n✅ Found {len(detections)} detections (showing first 10):\n")
            print(f"{'ID':<8} {'Track':<8} {'Time(s)':<12} {'Class':<20} {'BBox':<30} {'Timestamp'}")
            print("-" * 110)
            
            for det in detections:
                det_id, track_id, time_offset, class_name, bbox, timestamp = det
                bbox_str = str(bbox)[:28] if bbox else "None"
                time_str = f"{time_offset:.2f}" if time_offset else "None"
                
                print(f"{str(det_id)[:8]:<8} {track_id:<8} {time_str:<12} {class_name:<20} {bbox_str:<30} {timestamp}")
            
            # คำนวณ FPS จากวิดีโอจริง
            import cv2
            file_path = video[2]
            
            if os.path.exists(file_path):
                cap = cv2.VideoCapture(file_path)
                fps = cap.get(cv2.CAP_PROP_FPS)
                total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
                duration = total_frames / fps if fps > 0 else 0
                cap.release()
                
                print(f"\n📊 Video Properties:")
                print(f"   FPS: {fps:.2f}")
                print(f"   Total Frames: {total_frames}")
                print(f"   Duration: {duration:.2f} seconds")
                
                # ตรวจสอบว่า time_offset อยู่ในช่วงที่ถูกต้องหรือไม่
                print(f"\n🔍 Validation:")
                for det in detections:
                    time_offset = det[2]
                    if time_offset:
                        frame_idx = int(time_offset * fps)
                        if frame_idx < 0 or frame_idx >= total_frames:
                            print(f"   ⚠️  Detection at {time_offset:.2f}s (frame {frame_idx}) is OUT OF RANGE!")
                        else:
                            print(f"   ✅ Detection at {time_offset:.2f}s (frame {frame_idx}) is valid")
            else:
                print(f"\n⚠️  Video file not found: {file_path}")
                
    finally:
        conn.close()


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python debug_bbox_timing.py <video_id>")
        print("\nTo get video IDs, run:")
        print("  SELECT id, filename FROM processed_videos;")
        sys.exit(1)
    
    video_id = sys.argv[1]
    check_bbox_timing(video_id)
