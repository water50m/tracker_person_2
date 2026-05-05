# Terminal Commands Guide - Re-ID Tracking System

คู่มือการใช้งานระบบผ่าน Terminal ทั้งหมด

---

## 🎯 Quick Start

```bash
# 1. ดู Demo AI แบบ Real-time (แนะนำก่อน)
python terminal_demo.py path/to/video.mp4

# 2. ทดสอบระบบจริง (ต้องมี Server รัน)
python terminal_test.py status
```

---

## 📁 Scripts ที่มีให้ใช้

| Script | ไฟล์ | ใช้ทำอะไร |
|--------|------|-----------|
| **Demo** | `terminal_demo.py` | ดู AI ทำงานแบบ real-time ไม่ต้อง DB |
| **Test** | `terminal_test.py` | ทดสอบระบบจริง ผ่าน API |
| **Tests** | `pytest tests/` | รัน automated tests |
| **Debug** | `debug_*.py` | Debug specific issues |

---

## 🎬 1. Terminal Demo (ไม่ต้อง Database/Server)

ดูผลการตรวจจับ AI + Re-ID แบบ real-time โดยตรง

### Usage
```bash
python terminal_demo.py <video_path>
```

### Examples
```bash
# รัน demo กับวิดีโอ
python terminal_demo.py temp_videos/CAM-01_4p-c0-new.mp4

# รันกับ webcam (ถ้าใช้ 0)
python terminal_demo.py 0
```

### Controls ขณะรัน
| ปุ่ม | ทำอะไร |
|------|---------|
| `Q` | ออก |
| `SPACE` | Pause/Resume |
| `S` | บันทึก screenshot |

### สิ่งที่เห็นบนจอ
- **ID:X** - Track ID แบบ persistent (จำคนได้แม้หายจาก frame)
- **Clothing** - เสื้อผ้าที่ตรวจพบ
- **Color** - สีหลัก (เช่น bright_red, dark_blue)
- **Info Panel** - Frame, Active Tracks, Lost Tracks, FPS

---

## 🔧 2. Terminal Test (ต้องมี Server รัน)

ทดสอบระบบจริงผ่าน API endpoints

### 2.1 เริ่ม Server ก่อน
```bash
# Terminal 1 - เปิด Server
uvicorn src.api.main:app --host 0.0.0.0 --port 8000 --reload
```

### 2.2 รัน Tests
```bash
# Terminal 2 - ทดสอบระบบ

# ดูสถานะทั้งหมด
python terminal_test.py status

# ทดสอบแบบ Interactive (ถาม step-by-step)
python terminal_test.py

# อัปโหลดวิดีโอ
python terminal_test.py upload --video path/to/video.mp4 --camera-id CAM-01

# ค้นหาคน
python terminal_test.py search --clothing Shirt --color red

# ทดสอบ real-time events 30 วินาที
python terminal_test.py stream
```

### สิ่งที่ Test ได้
- ✅ Server connection
- ✅ Database connection
- ✅ List cameras
- ✅ Upload video
- ✅ View recent detections
- ✅ Search by clothing/color
- ✅ Real-time SSE stream

---

## 🧪 3. Automated Tests (Pytest)

รัน test suite ที่สร้างไว้

### 3.1 รัน Tests ทั้งหมด
```bash
# รันทั้งหมด
pytest tests/ -v

# รันพร้อม coverage report
pytest tests/ --cov=src --cov-report=html
```

### 3.2 รันเฉพาะ Category
```bash
# Unit Tests - ไม่ต้อง DB (เร็ว)
pytest tests/unit/ -v

# Integration Tests - ต้องมี DB/MinIO
pytest tests/integration/ -v

# E2E Tests - ต้องมี Server
pytest tests/e2e/ -v -m e2e
```

### 3.3 รันเฉพาะไฟล์
```bash
# Test Re-ID utilities
pytest tests/unit/test_reid_utils.py -v

# Test GPU
pytest tests/unit/test_gpu.py -v

# Test database connection
pytest tests/integration/test_database/test_connection.py -v

# Test database performance
pytest tests/integration/test_database/test_benchmark.py -v

# Test API endpoints
pytest tests/e2e/test_api_endpoints.py -v
```

---

## 🗄️ 4. Database Controls

### 4.1 ถ้าใช้ Docker
```bash
# เปิด DB + MinIO
docker-compose -f docker/docker-compose.yml up -d

# ดูสถานะ
docker-compose -f docker/docker-compose.yml ps

# ปิด
docker-compose -f docker/docker-compose.yml down
```

### 4.2 ถ้าใช้ Windows Service
```bash
# เปิด PostgreSQL
net start postgresql-x64-15

# ปิด PostgreSQL
net stop postgresql-x64-15

# เปิด MinIO (run โดยตรง)
minio server E:\minio-data --console-address :9001
```

### 4.3 Test Connection
```bash
# ผ่าน Python script
python tests/integration/test_database/test_connection.py

# ผ่าน psql
psql -h localhost -U postgres -d nexus_eye -c "SELECT version();"
```

---

## 🐛 5. Debug Scripts

| Script | ใช้สำหรับ |
|--------|-----------|
| `debug_bbox_timing.py` | ตรวจสอบว่า bbox ตรงกับเวลาวิดีโอ |
| `debug_db.py` | Debug database queries |
| `debug_frame.py` | Debug frame processing |
| `check_duplicate_timeoffsets.py` | ตรวจหา time offset ซ้ำ |
| `check_person_id.py` | ตรวจสอบ person ID |

### Usage
```bash
# Debug bbox timing
python debug_bbox_timing.py <video_id>

# Example
python debug_bbox_timing.py 123e4567-e89b-12d3-a456-426614174000
```

---

## 🔄 6. Workflow Examples

### Scenario A: ทดสอบ AI เร็วๆ (ไม่ต้อง DB)
```bash
# รัน demo ดูผลทันที
python terminal_demo.py temp_videos/test.mp4
```

### Scenario B: ทดสอบระบบครบวงจร
```bash
# Terminal 1: เปิด Server
uvicorn src.api.main:app --port 8000

# Terminal 2: เปิด DB
docker-compose -f docker/docker-compose.yml up -d

# Terminal 3: ทดสอบระบบ
python terminal_test.py upload --video test.mp4 --camera-id CAM-01
python terminal_test.py search --clothing t-shirt
```

### Scenario C: Development & Debug
```bash
# รัน unit tests ก่อน push code
pytest tests/unit/ -v

# ตรวจสอบ database
pytest tests/integration/test_database/test_connection.py -v

# Debug ปัญหาเฉพาะ
python debug_bbox_timing.py <video_id>
```

---

## 📝 Summary Table

| ต้องการ... | ใช้คำสั่ง... | ต้องมี... |
|-----------|-------------|----------|
| ดู AI ทำงานแบบ real-time | `python terminal_demo.py` | ไฟล์วิดีโอ |
| ทดสอบ API endpoints | `python terminal_test.py` | Server รัน |
| รัน automated tests | `pytest tests/` | - (หรือ DB/Server ตาม type) |
| ทดสอบ database | `pytest tests/integration/` | PostgreSQL + MinIO |
| Debug issues | `python debug_*.py` | ขึ้นอยู่กับ script |
| เปิด/ปิด DB | `docker-compose` | Docker |

---

## 💡 Tips

1. **เริ่มจาก Demo ก่อน** - ไม่ต้อง setup อะไรเลย
2. **Unit tests เร็วที่สุด** - ไม่ต้อง DB, รันเช็ค logic ได้
3. **ใช้ `status` ดูภาพรวม** - `python terminal_test.py status`
4. **Screenshot ได้** - กด `S` ขณะรัน demo

---

## 🆘 Troubleshooting

### Server ไม่ start
```bash
# Check port 8000 ว่างไหม
netstat -an | findstr 8000

# เปิด port อื่น
uvicorn src.api.main:app --port 8080
```

### Database ไม่ connect
```bash
# Test connection
python tests/integration/test_database/test_connection.py

# ดู logs
docker-compose -f docker/docker-compose.yml logs postgres
```

### Demo ไม่แสดงหน้าจอ
```bash
# ถ้าไม่มีจอ (SSH), ใช้ test mode
python -c "from terminal_demo import TerminalDemo; d = TerminalDemo('test.mp4'); print('OK')"
```
