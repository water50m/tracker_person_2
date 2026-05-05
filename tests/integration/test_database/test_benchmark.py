"""
Database Benchmark Test
ทดสอบความเร็วการ read/write ของ database
"""
import unittest
import time
import uuid
import random
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..', 'src'))

from services.database import DatabaseService


class TestDatabaseBenchmark(unittest.TestCase):
    """ทดสอบความเร็ว database operations"""
    
    def setUp(self):
        """Setup database connection"""
        self.db = DatabaseService()
        if self.db.conn is None:
            self.skipTest("Database connection failed")
    
    def tearDown(self):
        """Cleanup test data"""
        if self.db.conn:
            with self.db.conn.cursor() as cur:
                cur.execute("DELETE FROM detections WHERE class_name = 'Benchmark_Bot'")
            self.db.close()
    
    def test_write_speed(self):
        """ทดสอบความเร็วการ INSERT"""
        print("🚀 Starting Database Benchmark...")
        print("------------------------------------------------")
        
        TOTAL_OPERATIONS = 100
        fake_track_id = 999999
        fake_image = "benchmark_test.jpg"
        fake_color = {"red": 50, "benchmark": True}
        
        print(f"📝 Testing WRITE speed ({TOTAL_OPERATIONS} rows)...")
        
        start_time = time.time()
        
        for i in range(TOTAL_OPERATIONS):
            self.db.insert_detection(
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
        
        self.assertGreater(writes_per_sec, 10)  # At least 10 writes per second
    
    def test_read_speed(self):
        """ทดสอบความเร็วการ SELECT"""
        # First insert some data
        TOTAL_OPERATIONS = 100
        fake_track_id = 999999
        fake_image = "benchmark_test.jpg"
        fake_color = {"red": 50, "benchmark": True}
        
        for i in range(TOTAL_OPERATIONS):
            self.db.insert_detection(
                track_id=fake_track_id,
                image_path=fake_image,
                category="TEST",
                class_name="Benchmark_Bot",
                color_profile=fake_color,
                camera_id="TEST-CAM"
            )
        
        print(f"📖 Testing READ speed (Querying {TOTAL_OPERATIONS} rows)...")
        
        start_time = time.time()
        
        with self.db.conn.cursor() as cur:
            cur.execute("SELECT * FROM detections WHERE class_name = 'Benchmark_Bot'")
            rows = cur.fetchall()
        
        end_time = time.time()
        duration = end_time - start_time
        reads_per_sec = len(rows) / duration if duration > 0 else 0

        print(f"   ✅ Fetched {len(rows)} rows in {duration:.4f} seconds")
        print(f"   ⚡ Speed: {reads_per_sec:.2f} reads/second")
        print("------------------------------------------------")
        
        self.assertEqual(len(rows), TOTAL_OPERATIONS)
        self.assertGreater(reads_per_sec, 50)  # At least 50 reads per second


if __name__ == "__main__":
    unittest.main(verbosity=2)
