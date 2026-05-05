"""
Database Connection Test
"""
import os
import psycopg2
from minio import Minio
from dotenv import load_dotenv
import unittest

# Load .env
load_dotenv()


class TestDatabaseConnection(unittest.TestCase):
    """ทดสอบการเชื่อมต่อ PostgreSQL และ MinIO"""
    
    def test_postgresql_connection(self):
        """ทดสอบการเชื่อมต่อ PostgreSQL"""
        print("🐘 Testing PostgreSQL Connection...")
        print(f"   Host: {os.getenv('DB_HOST')}:{os.getenv('DB_PORT')}")
        print(f"   User: {os.getenv('DB_USER')}")
        print(f"   DB:   {os.getenv('DB_NAME')}")
        
        try:
            conn = psycopg2.connect(
                host=os.getenv("DB_HOST"),
                port=os.getenv("DB_PORT"),
                database=os.getenv("DB_NAME"),
                user=os.getenv("DB_USER"),
                password=os.getenv("DB_PASS")
            )
            cur = conn.cursor()
            cur.execute("SELECT version();")
            db_version = cur.fetchone()
            print(f"✅ PostgreSQL CONNECTED SUCCESS! version: {db_version[0][:15]}...")
            conn.close()
        except Exception as e:
            self.fail(f"❌ PostgreSQL FAILED: {e}")
    
    def test_minio_connection(self):
        """ทดสอบการเชื่อมต่อ MinIO"""
        print(f"🪣 Testing MinIO Connection...")
        endpoint = os.getenv('MINIO_ENDPOINT')
        access_key = os.getenv('MINIO_ACCESS_KEY')
        print(f"   Endpoint: {endpoint}")
        print(f"   Key:      {access_key}")
        
        try:
            clean_endpoint = endpoint.replace("http://", "").replace("https://", "")
            client = Minio(
                clean_endpoint,
                access_key=access_key,
                secret_key=os.getenv('MINIO_SECRET_KEY'),
                secure=os.getenv('MINIO_SECURE') == 'True'
            )
            buckets = client.list_buckets()
            print("✅ MinIO CONNECTED SUCCESS!")
            
            target_bucket = os.getenv('MINIO_BUCKET')
            found = False
            print(f"   รายการ Buckets ที่มี:")
            for bucket in buckets:
                print(f"    - {bucket.name}")
                if bucket.name == target_bucket:
                    found = True
                    
            if found:
                print(f"✅ เจอ Bucket '{target_bucket}' แล้ว พร้อมใช้งาน!")
            else:
                print(f"⚠️ เชื่อมต่อได้ แต่ไม่เจอ Bucket '{target_bucket}'")
                
        except Exception as e:
            self.fail(f"❌ MinIO FAILED: {e}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
