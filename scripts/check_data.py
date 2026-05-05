"""
check_data.py - ตรวจสอบ Detection Records และ Images

ใช้ตรวจสอบว่า VideoProcessor/StreamProcessor บันทึกข้อมูลถูกต้องหรือไม่

Usage:
    cd e:\ALL_CODE\my-project
    uv run python scripts\check_data.py --video-id <uuid>
    uv run python scripts\check_data.py --camera-id CAM-01 --limit 10
    uv run python scripts\check_data.py --check-minio --bucket detections
"""
import sys
import os
import argparse
from datetime import datetime, timedelta
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from services.database import DatabaseService
from services.storage import StorageService


def check_database_detections(video_id: str = None, camera_id: str = None, limit: int = 20):
    """ตรวจสอบ detection records ใน database"""
    print("=" * 60)
    print("🔍 Checking Database Detections")
    print("=" * 60)
    
    db = DatabaseService()
    
    def execute_query(conn, query, params=None):
        """Helper to execute query and return results as dict"""
        with conn.cursor() as cur:
            cur.execute(query, params)
            if cur.description:
                columns = [desc[0] for desc in cur.description]
                rows = cur.fetchall()
                return [dict(zip(columns, row)) for row in rows]
            return []
    
    try:
        if video_id:
            # ตรวจสอบตาม video_id
            print(f"\n📹 Video ID: {video_id}")
            
            # Query detections สำหรับ video นี้
            query = """
                SELECT 
                    id, 
                    video_id, 
                    camera_id, 
                    timestamp,
                    image_path,
                    clothing_category,
                    class_name
                FROM detections 
                WHERE video_id = %s 
                ORDER BY timestamp 
                LIMIT %s
            """
            results = execute_query(db.conn, query, (video_id, limit))
            
            if not results:
                print("   ⚠️  No detections found for this video")
                return False
            
            print(f"   ✅ Found {len(results)} detection records")
            print("\n   Sample records:")
            print("   " + "-" * 70)
            for row in results[:5]:  # แสดง 5 แถวแรก
                print(f"   {row['id'][:8]} | {row['class_name'] or 'N/A':20s} | "
                      f"{row['clothing_category'] or 'N/A':15s} | {str(row['timestamp'])[:19]}")
            
            # สรุปสถิติ
            stats_query = """
                SELECT 
                    COUNT(*) as total,
                    COUNT(DISTINCT camera_id) as unique_cameras,
                    MIN(timestamp) as first_detection,
                    MAX(timestamp) as last_detection
                FROM detections 
                WHERE video_id = %s
            """
            stats = execute_query(db.conn, stats_query, (video_id,))[0]
            
            print(f"\n   📊 Statistics:")
            print(f"      Total detections: {stats['total']}")
            print(f"      Unique cameras: {stats['unique_cameras']}")
            print(f"      First detection: {stats['first_detection']}")
            print(f"      Last detection: {stats['last_detection']}")
            
            return True
            
        elif camera_id:
            # ตรวจสอบตาม camera_id
            print(f"\n📷 Camera ID: {camera_id}")
            
            query = """
                SELECT 
                    id, 
                    video_id, 
                    camera_id, 
                    timestamp,
                    class_name,
                    image_path
                FROM detections 
                WHERE camera_id = %s 
                ORDER BY timestamp DESC 
                LIMIT %s
            """
            results = execute_query(db.conn, query, (camera_id, limit))
            
            if not results:
                print("   ⚠️  No detections found for this camera")
                return False
            
            print(f"   ✅ Found {len(results)} recent detections")
            return True
            
        else:
            # แสดงสรุปทั้งหมด
            print("\n📊 Overall Database Summary")
            
            query = """
                SELECT 
                    COUNT(*) as total_detections,
                    COUNT(DISTINCT video_id) as unique_videos,
                    COUNT(DISTINCT camera_id) as unique_cameras,
                    MAX(timestamp) as latest_detection
                FROM detections
            """
            result = execute_query(db.conn, query)[0]
            
            print(f"   Total detections: {result['total_detections']}")
            print(f"   Unique videos: {result['unique_videos']}")
            print(f"   Unique cameras: {result['unique_cameras']}")
            print(f"   Latest detection: {result['latest_detection']}")
            
            return True
            
    except Exception as e:
        print(f"   ❌ Database error: {e}")
        return False


def check_minio_images(bucket: str = None, prefix: str = None, limit: int = 20):
    """ตรวจสอบ images ใน MinIO"""
    print("\n" + "=" * 60)
    print("🔍 Checking MinIO Storage")
    print("=" * 60)
    
    try:
        storage = StorageService()
        
        # Use default bucket from storage service
        bucket = bucket or storage.bucket_name
        
        print(f"\n🪣 Bucket: {bucket}")
        
        # List objects using MinIO client directly
        objects = []
        for obj in storage.client.list_objects(bucket, prefix=prefix or "", recursive=True):
            objects.append({
                'name': obj.object_name,
                'size': obj.size,
                'last_modified': obj.last_modified,
            })
            if len(objects) >= limit:
                break
        
        if not objects:
            print("   ⚠️  No images found")
            return False
        
        print(f"   ✅ Found {len(objects)} objects")
        
        # แสดงตัวอย่าง
        print("\n   Sample images:")
        print("   " + "-" * 70)
        
        total_size = 0
        for obj in objects[:10]:  # แสดง 10 อันแรก
            size_mb = obj.get('size', 0) / (1024 * 1024)
            total_size += obj.get('size', 0)
            last_modified = obj.get('last_modified', 'N/A')
            if hasattr(last_modified, 'strftime'):
                last_modified = last_modified.strftime('%Y-%m-%d %H:%M:%S')
            print(f"   {obj['name'][:50]:50s} | {size_mb:6.2f} MB | {last_modified}")
        
        print(f"\n   📊 Storage Summary:")
        print(f"      Total objects: {len(objects)}")
        print(f"      Total size: {total_size / (1024*1024):.2f} MB")
        
        # ตรวจสอบว่า image เปิดได้หรือไม่ (sample 1 ไฟล์)
        if objects:
            sample_obj = objects[0]
            print(f"\n   🔗 Sample URL:")
            url = storage.client.presigned_get_object(bucket, sample_obj['name'], expires=timedelta(hours=1))
            print(f"      {url[:80]}...")
        
        return True
        
    except Exception as e:
        print(f"   ❌ MinIO error: {e}")
        return False


def check_video_status(video_id: str):
    """ตรวจสอบสถานะ video processing"""
    print("\n" + "=" * 60)
    print("🔍 Checking Video Processing Status")
    print("=" * 60)
    
    db = DatabaseService()
    
    def execute_query(conn, query, params=None):
        """Helper to execute query and return results as dict"""
        with conn.cursor() as cur:
            cur.execute(query, params)
            if cur.description:
                columns = [desc[0] for desc in cur.description]
                rows = cur.fetchall()
                return [dict(zip(columns, row)) for row in rows]
            return []
    
    try:
        query = """
            SELECT 
                id, 
                camera_id, 
                label, 
                filename,
                status,
                created_at,
                progress,
                width,
                height
            FROM processed_videos 
            WHERE id = %s::uuid
        """
        result = execute_query(db.conn, query, (video_id,))
        
        if not result:
            print(f"\n   ⚠️  Video {video_id} not found")
            return False
        
        video = result[0]
        print(f"\n   📹 Video: {video.get('label', 'N/A')} ({video.get('filename', 'N/A')})")
        print(f"   🏷️  Camera: {video.get('camera_id', 'N/A')}")
        print(f"   📊 Status: {video.get('status', 'unknown')}")
        print(f"   � Progress: {video.get('progress', 0)}%")
        print(f"   🕐 Created: {video.get('created_at', 'N/A')}")
        
        if video.get('width') and video.get('height'):
            print(f"   📐 Resolution: {video['width']}x{video['height']}")
        
        return video.get('status') == 'completed'
        
    except Exception as e:
        print(f"   ❌ Error: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(
        description="Check detection records and images",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  uv run python scripts\check_data.py --video-id abc-123
  uv run python scripts\check_data.py --camera-id CAM-01 --limit 50
  uv run python scripts\check_data.py --check-minio --bucket detections
  uv run python scripts\check_data.py --video-id abc-123 --check-minio
        """
    )
    
    parser.add_argument('--video-id', type=str, help='Video UUID to check')
    parser.add_argument('--camera-id', type=str, help='Camera ID to check')
    parser.add_argument('--limit', type=int, default=20, help='Limit results')
    parser.add_argument('--check-minio', action='store_true', help='Also check MinIO storage')
    parser.add_argument('--bucket', type=str, default='detections', help='MinIO bucket name')
    parser.add_argument('--prefix', type=str, help='MinIO object prefix')
    
    args = parser.parse_args()
    
    print("\n" + "=" * 60)
    print("🚀 Data Verification Tool")
    print("=" * 60)
    print(f"⏰ Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    results = []
    
    # Check Database
    if args.video_id or args.camera_id:
        db_ok = check_database_detections(
            video_id=args.video_id,
            camera_id=args.camera_id,
            limit=args.limit
        )
        results.append(('Database', db_ok))
        
        if args.video_id:
            status_ok = check_video_status(args.video_id)
            results.append(('Video Status', status_ok))
    else:
        db_ok = check_database_detections()
        results.append(('Database', db_ok))
    
    # Check MinIO
    if args.check_minio:
        minio_ok = check_minio_images(
            bucket=args.bucket,
            prefix=args.prefix,
            limit=args.limit
        )
        results.append(('MinIO', minio_ok))
    
    # Summary
    print("\n" + "=" * 60)
    print("📋 Summary")
    print("=" * 60)
    
    all_passed = True
    for name, status in results:
        icon = "✅" if status else "❌"
        print(f"   {icon} {name}: {'PASS' if status else 'FAIL'}")
        if not status:
            all_passed = False
    
    print("\n" + "=" * 60)
    if all_passed:
        print("🎉 All checks passed!")
    else:
        print("⚠️  Some checks failed. Review output above.")
    print("=" * 60 + "\n")
    
    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
