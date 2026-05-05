import time
import uuid
import random
from src.services.database import DatabaseService

def run_benchmark():
    print("🚀 Starting Database Benchmark...")
    print("------------------------------------------------")
    
    # 1. เชื่อมต่อ Database
    try:
        db = DatabaseService()
        if db.conn is None:
            print("❌ Connection Failed. Aborting.")
            return
    except Exception as e:
        print(f"❌ Error: {e}")
        return

    # จำนวนรอบที่จะทดสอบ
    TOTAL_OPERATIONS = 1000 
    
    # สร้างข้อมูลจำลอง
    fake_track_id = 999999
    fake_image = "benchmark_test.jpg"
    fake_color = {"red": 50, "benchmark": True}

    # ==========================================
    # 🧪 TEST 1: WRITE SPEED (INSERT)
    # ==========================================
    print(f"📝 Testing WRITE speed ({TOTAL_OPERATIONS} rows)...")
    
    start_time = time.time()
    
    for i in range(TOTAL_OPERATIONS):
        # เรียกใช้ฟังก์ชัน insert ของจริงที่เราเขียนไว้
        db.insert_detection(
            track_id=fake_track_id,
            image_path=fake_image,
            category="TEST",
            class_name="Benchmark_Bot",
            color_profile=fake_color,
            camera_id="TEST-CAM"
        )
        
    end_time = time.time()
    duration = end_time - start_time
    writes_per_sec = TOTAL_OPERATIONS / duration
    
    print(f"   ✅ Finished in {duration:.4f} seconds")
    print(f"   ⚡ Speed: {writes_per_sec:.2f} inserts/second")
    print("------------------------------------------------")

    # ==========================================
    # 🧪 TEST 2: READ SPEED (SELECT)
    # ==========================================
    print(f"📖 Testing READ speed (Querying {TOTAL_OPERATIONS} rows)...")
    
    start_time = time.time()
    
    with db.conn.cursor() as cur:
        # ลองดึงข้อมูลที่เราเพิ่งใส่ลงไปกลับมาทั้งหมด
        cur.execute("SELECT * FROM detections WHERE class_name = 'Benchmark_Bot'")
        rows = cur.fetchall()
        
    end_time = time.time()
    duration = end_time - start_time
    reads_per_sec = len(rows) / duration if duration > 0 else 0

    print(f"   ✅ Fetched {len(rows)} rows in {duration:.4f} seconds")
    print(f"   ⚡ Speed: {reads_per_sec:.2f} reads/second")
    print("------------------------------------------------")

    # ==========================================
    # 🧹 CLEANUP (ลบข้อมูลขยะทิ้ง)
    # ==========================================
    print("🧹 Cleaning up test data...")
    with db.conn.cursor() as cur:
        cur.execute("DELETE FROM detections WHERE class_name = 'Benchmark_Bot'")
    print("✅ Cleanup done.")
    
    db.close()
    print("👋 Benchmark Complete.")

if __name__ == "__main__":
    run_benchmark()