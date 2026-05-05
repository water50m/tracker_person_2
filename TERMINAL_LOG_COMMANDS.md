# Terminal Log Manager Commands

## 📋 คำสั่งพื้นฐาน

### ดูสถานะ logs
```bash
python terminal_log_manager.py status
```

### เปิด Silent Mode (ซ่อน logs ใน terminal)
```bash
python terminal_log_manager.py enable

# พร้อมบันทึกลงไฟล์
python terminal_log_manager.py enable --file my_session
```

### ปิด Silent Mode (แสดง logs ใน terminal)
```bash
python terminal_log_manager.py disable
```

### สลับการแสดง logs
```bash
python terminal_log_manager.py toggle

# พร้อมบันทึกลงไฟล์เมื่อเปิด silent mode
python terminal_log_manager.py toggle --file session_logs
```

### ดู logs ล่าสุด
```bash
# ดู 20 logs ล่าสุด (default)
python terminal_log_manager.py show

# ดู 50 logs ล่าสุด
python terminal_log_manager.py show --count 50
```

### ล้าง log buffer
```bash
python terminal_log_manager.py clear
```

## 🎯 การใช้งานร่วมกับ CV2 Analysis

### เริ่มต้น (ซ่อน logs)
```bash
python terminal_log_manager.py enable --file cv2_analysis
```

### รัน CV2 Analysis
```bash
uv run uvicorn src.api.main:app --reload
```

### ดู logs ระหว่างทำงาน (ใน terminal อื่น)
```bash
python terminal_log_manager.py show --count 100
```

### สิ้นสุด (แสดง logs อีกครั้ง)
```bash
python terminal_log_manager.py disable
```

## 📁 ตำแหน่ง Log Files
- **Logs จะถูกบันทึกที่:** `logs/`
- **รูปแบบชื่อไฟล์:** `{filename}_{timestamp}.log`
- **ตัวอย่าง:** `logs/cv2_analysis_20260428_185700.log`

## 🔧 การใช้ใน Code

```python
from src.utils.log_manager import enable_silent_logs, disable_silent_logs, toggle_logs

# เปิด silent mode
enable_silent_logs("my_session")

# ปิด silent mode  
disable_silent_logs()

# สลับ
toggle_logs("another_session")
```
