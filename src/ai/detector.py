import cv2
from ultralytics import YOLO
import torch
import sys
from pathlib import Path

# Add parent directory to path for config_loader import
sys.path.insert(0, str(Path(__file__).parent.parent))
from config_loader import get_detector_model_path, get_device

class PersonDetector:
    def __init__(self, model_path=None):
        # Load model path from config if not provided
        if model_path is None:
            model_path = get_detector_model_path()
        
        # Get device from config
        config_device = get_device()
        self.device = config_device if config_device in ['cuda', 'cpu'] else ('cuda' if torch.cuda.is_available() else 'cpu')
        print(f"🚀 Person Detector using device: {self.device.upper()}")

        # โหลดโมเดลแล้วส่งไปที่ Device นั้น
        self.model = YOLO(model_path)
        self.model.to(self.device)  # <--- คำสั่งสำคัญ! ย้ายไป GPU

    def track_people(self, frame):
        # 4. ส่ง device=self.device เข้าไปเพื่อความชัวร์
        results = self.model.track(
            frame, 
            persist=True, 
            classes=[0], 
            verbose=False,
            device=self.device,      # <--- เพิ่มตรงนี้
            imgsz=320,               # <--- ลดขนาดภาพให้ AI คิดเร็วขึ้น 3-4 เท่า 
            tracker="bytetrack.yaml" # <--- ใช้ Tracker แบบเบา (ไม่ต้องคำนวณ ReID)
        )
        return results[0]