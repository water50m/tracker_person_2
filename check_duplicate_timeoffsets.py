"""
ตรวจสอบว่ามี detections หลายตัวที่มี video_time_offset เดียวกันหรือไม่
"""
import psycopg2
import os
from dotenv import load_dotenv
from collections import Counter

load_dotenv()

def check_duplicate_timeoffsets(video_id: str):
    """ตรวจสอบ detections ที่มี time_offset เดียวกัน"""
    
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
                SELECT id, filename, camera_id 
                FROM processed_videos 
                WHERE id::text = %s
            """, (video_id,))
            video = cur.fetchone()
            
            if not video:
                print(f"❌ Video ID {video_id} not found")
                return
            
            print(f"\n📹 Video: {video[1]} (Camera: {video[2]})")
            
            # ดึง detections พร้อม time_offset
            cur.execute("""
                SELECT 
                    video_time_offset,
                    track_id,
                    class_name,
                    bbox
                FROM detections 
                WHERE video_id = %s 
                ORDER BY video_time_offset ASC
            """, (video_id,))
            
            detections = cur.fetchall()
            
            if not detections:
                print(f"\n⚠️  No detections found for this video")
                return
            
            print(f"\n✅ Total detections: {len(detections)}")
            
            # นับจำนวน detections ต่อ time_offset
            time_offset_counts = Counter([d[0] for d in detections if d[0] is not None])
            
            # หา time_offsets ที่มีมากกว่า 1 detection
            duplicates = {k: v for k, v in time_offset_counts.items() if v > 1}
            
            if duplicates:
                print(f"\n🔍 Found {len(duplicates)} time_offsets with MULTIPLE detections:")
                print(f"   (Total {sum(duplicates.values())} detections in these time_offsets)")
                print()
                
                # แสดง top 10 time_offsets ที่มี detection มากที่สุด
                sorted_duplicates = sorted(duplicates.items(), key=lambda x: x[1], reverse=True)
                
                print(f"{'Time Offset (s)':<18} {'Count':<8} {'Details'}")
                print("-" * 80)
                
                for time_offset, count in sorted_duplicates[:10]:
                    # ดึง detections ที่มี time_offset นี้
                    dets_at_time = [d for d in detections if d[0] == time_offset]
                    details = ", ".join([f"ID{d[1]}:{d[2]}" for d in dets_at_time[:3]])
                    if len(dets_at_time) > 3:
                        details += f" ... (+{len(dets_at_time)-3} more)"
                    
                    print(f"{time_offset:<18.3f} {count:<8} {details}")
                
                # คำนวณ frame index (สมมติ 30 FPS)
                print(f"\n📊 Frame Analysis (assuming 30 FPS):")
                for time_offset, count in sorted_duplicates[:5]:
                    frame_idx = int(time_offset * 30)
                    print(f"   Time {time_offset:.3f}s (Frame {frame_idx}): {count} detections")
                    
            else:
                print(f"\n✅ No duplicate time_offsets found")
                print(f"   All {len(detections)} detections have unique time_offsets")
                
            # แสดงสถิติเพิ่มเติม
            print(f"\n📈 Statistics:")
            print(f"   Unique time_offsets: {len(time_offset_counts)}")
            print(f"   Average detections per time_offset: {len(detections) / len(time_offset_counts):.2f}")
            print(f"   Max detections at single time_offset: {max(time_offset_counts.values())}")
            print(f"   Min detections at single time_offset: {min(time_offset_counts.values())}")
                
    finally:
        conn.close()


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python check_duplicate_timeoffsets.py <video_id>")
        print("\nTo get video IDs, run:")
        print("  SELECT id, filename FROM processed_videos;")
        sys.exit(1)
    
    video_id = sys.argv[1]
    check_duplicate_timeoffsets(video_id)
