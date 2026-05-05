from minio import Minio
import os
from dotenv import load_dotenv
import cv2
import io

load_dotenv()

class StorageService:
    def __init__(self):
        self.client = Minio(
            os.getenv("MINIO_ENDPOINT"),
            access_key=os.getenv("MINIO_ACCESS_KEY"),
            secret_key=os.getenv("MINIO_SECRET_KEY"),
            secure=os.getenv("MINIO_SECURE") == 'True'
        )
        self.bucket_name = os.getenv("MINIO_BUCKET")
        self.ensure_bucket_exists()

    def ensure_bucket_exists(self):
        """ตรวจสอบว่ามี Bucket หรือยัง ถ้าไม่มีให้สร้างเลย"""
        try:
            if not self.client.bucket_exists(self.bucket_name):
                self.client.make_bucket(self.bucket_name)
                print(f"✅ Created Bucket: {self.bucket_name}")
            else:
                print(f"✅ Bucket '{self.bucket_name}' exists.")
        except Exception as e:
            print(f"❌ MinIO Connection Failed: {e}")

    def upload_image(self, image_numpy, filename):
        """รับภาพ OpenCV (numpy) -> แปลงเป็นไฟล์ -> อัปโหลดขึ้น MinIO"""
        try:
            # 1. แปลงภาพ numpy เป็น bytes (เหมือนเซฟไฟล์ลง RAM)
            _, img_encoded = cv2.imencode('.jpg', image_numpy)
            img_bytes = io.BytesIO(img_encoded.tobytes())
            
            # 2. อัปโหลด
            self.client.put_object(
                self.bucket_name,
                filename,
                img_bytes,
                length=img_bytes.getbuffer().nbytes,
                content_type="image/jpeg"
            )
            
            # 3. คืนค่า Path เพื่อเอาไปเก็บใน DB
            return f"{self.bucket_name}/{filename}"
            
        except Exception as e:
            print(f"❌ Upload Failed: {e}")
            return None

    def clear_bucket(self):
        """ลบ Bucket ทั้งหมดแล้วสร้างใหม่ (ลบรูปภาพทั้งหมด)"""
        import time
        start_time = time.time()
        
        try:
            print(f"[CLEAR_BUCKET] Starting at {time.strftime('%H:%M:%S')}")
            
            # ตรวจสอบว่า bucket มีอยู่หรือไม่
            print(f"[CLEAR_BUCKET] Checking if bucket exists...")
            if not self.client.bucket_exists(self.bucket_name):
                print(f"[CLEAR_BUCKET] Bucket not found, creating...")
                self.client.make_bucket(self.bucket_name)
                elapsed = time.time() - start_time
                print(f"[CLEAR_BUCKET] Created new bucket in {elapsed:.2f}s")
                return {"status": "success", "message": f"Bucket '{self.bucket_name}' created", "deleted_objects": 0, "elapsed_seconds": elapsed}

            # ลบ objects ทั้งหมดใน bucket ก่อน (bucket ต้องว่างก่อนจึงจะลบได้)
            print(f"[CLEAR_BUCKET] Listing objects...")
            deleted_count = 0
            list_start = time.time()
            objects_to_delete = list(self.client.list_objects(self.bucket_name, recursive=True))
            list_elapsed = time.time() - list_start
            print(f"[CLEAR_BUCKET] Found {len(objects_to_delete)} objects in {list_elapsed:.2f}s")
            
            if objects_to_delete:
                print(f"[CLEAR_BUCKET] Deleting {len(objects_to_delete)} objects...")
                delete_start = time.time()
                for obj in objects_to_delete:
                    self.client.remove_object(self.bucket_name, obj.object_name)
                    deleted_count += 1
                    if deleted_count % 100 == 0:
                        print(f"[CLEAR_BUCKET] Deleted {deleted_count}/{len(objects_to_delete)} objects...")
                delete_elapsed = time.time() - delete_start
                print(f"[CLEAR_BUCKET] Deleted {deleted_count} objects in {delete_elapsed:.2f}s")

            # ลบ bucket และสร้างใหม่
            print(f"[CLEAR_BUCKET] Removing bucket...")
            remove_start = time.time()
            self.client.remove_bucket(self.bucket_name)
            remove_elapsed = time.time() - remove_start
            print(f"[CLEAR_BUCKET] Bucket removed in {remove_elapsed:.2f}s")
            
            print(f"[CLEAR_BUCKET] Recreating bucket...")
            create_start = time.time()
            self.client.make_bucket(self.bucket_name)
            create_elapsed = time.time() - create_start
            print(f"[CLEAR_BUCKET] Bucket recreated in {create_elapsed:.2f}s")

            elapsed = time.time() - start_time
            print(f"✅ Bucket '{self.bucket_name}' cleared ({deleted_count} objects, total: {elapsed:.2f}s)")
            return {"status": "success", "message": f"Bucket '{self.bucket_name}' cleared", "deleted_objects": deleted_count, "elapsed_seconds": elapsed}

        except Exception as e:
            elapsed = time.time() - start_time
            print(f"❌ Clear Bucket Failed after {elapsed:.2f}s: {e}")
            return {"status": "error", "message": str(e), "elapsed_seconds": elapsed}

# ตัวอย่างการเรียกใช้
if __name__ == "__main__":
    storage = StorageService()