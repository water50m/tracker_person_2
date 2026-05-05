import cv2
import os

class VideoLoader:
    def __init__(self, source, camera_id="TEST-CAM"):
        """
        source: 
          - int (0, 1) -> Webcam
          - str ("path/to/file.mp4") -> Video File
          - str ("rtsp://...") -> IP Camera Stream
        """
        self.camera_id = camera_id
        self.source = source
        self.is_file = False
        
        # เช็คว่าเป็น Webcam (ตัวเลข) หรือไม่
        if isinstance(source, int) or (isinstance(source, str) and source.isdigit()):
            self.cap = cv2.VideoCapture(int(source))
        else:
            # เช็คว่าเป็นไฟล์หรือ Link
            self.cap = cv2.VideoCapture(source)
            if os.path.isfile(source):
                self.is_file = True

        if not self.cap.isOpened():
            raise ValueError(f"❌ Cannot open video source: {source}")

    def get_frame(self):
        ret, frame = self.cap.read()
        if not ret:
            # ถ้าเป็นไฟล์วิดีโอ จบแล้วให้วนลูป (Loop) หรือส่ง None เพื่อจบ
            if self.is_file: 
                # self.cap.set(cv2.CAP_PROP_POS_FRAMES, 0) # ถ้าอยากให้วน Loop เปิดบรรทัดนี้
                return None 
            return None
        return frame

    def get_info(self):
        width = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        fps = self.cap.get(cv2.CAP_PROP_FPS)
        return {"width": width, "height": height, "fps": fps, "cam_id": self.camera_id}

    def release(self):
        self.cap.release()