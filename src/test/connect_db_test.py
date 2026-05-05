import os
import psycopg2
from minio import Minio
from dotenv import load_dotenv

# 1. โหลดค่าจากไฟล์ .env
print("📂 Loading .env file...")
load_success = load_dotenv()
if not load_success:
    print("❌ Error: ไม่เจอไฟล์ .env หรือไฟล์ว่างเปล่า")
    exit()

print("------------------------------------------------")

# --- TEST 1: POSTGRESQL ---
print(f"🐘 Testing PostgreSQL Connection...")
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
    # ลองดึงเวอร์ชั่น DB เพื่อความชัวร์
    cur = conn.cursor()
    cur.execute("SELECT version();")
    db_version = cur.fetchone()
    print(f"✅ PostgreSQL CONNECTED SUCCESS! version: {db_version[0][:15]}...")
    conn.close()
except Exception as e:
    print(f"❌ PostgreSQL FAILED: {e}")
    print("   👉 คำแนะนำ: เช็ค User/Password หรือเช็คว่าสร้าง Database ชื่อนี้หรือยัง")

print("------------------------------------------------")

# --- TEST 2: MINIO ---
print(f"🪣 Testing MinIO Connection...")
endpoint = os.getenv('MINIO_ENDPOINT')
access_key = os.getenv('MINIO_ACCESS_KEY')
print(f"   Endpoint: {endpoint}")
print(f"   Key:      {access_key}")

try:
    # ตัด http:// ออกถ้ามี เพราะ library minio ไม่ต้องการ
    clean_endpoint = endpoint.replace("http://", "").replace("https://", "")
    
    client = Minio(
        clean_endpoint,
        access_key=access_key,
        secret_key=os.getenv('MINIO_SECRET_KEY'),
        secure=os.getenv('MINIO_SECURE') == 'True'
    )
    
    # ลอง List Buckets ดู
    buckets = client.list_buckets()
    print("✅ MinIO CONNECTED SUCCESS!")
    
    # เช็คว่ามี Bucket ที่เราต้องการไหม
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
        print(f"   👉 คำแนะนำ: ไปที่ localhost:9001 แล้วกด Create Bucket ชื่อ {target_bucket}")

except Exception as e:
    print(f"❌ MinIO FAILED: {e}")
    print("   👉 คำแนะนำ: เช็ค Port (ต้องเป็น 9000) และเช็ค Access/Secret Key")

print("------------------------------------------------")