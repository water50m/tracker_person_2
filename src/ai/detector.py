import cv2
from ultralytics import YOLO
import torch
import numpy as np
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
        self._feature_map = None
        self.last_person_embeddings = []
        self._hook_handle = self._setup_feature_hook()

    def _setup_feature_hook(self):
        """
        Capture an internal YOLO feature map during track()/predict().

        Ultralytics returns bbox/conf/class/track_id from model.track(), but it
        does not expose a per-detection embedding. This hook keeps one feature
        map from the same forward pass so bbox regions can be pooled into
        lightweight person embeddings.
        """
        try:
            pytorch_model = getattr(self.model, "model", None)
            if pytorch_model is not None and hasattr(pytorch_model, "model"):
                layers = list(pytorch_model.model)
            else:
                layers = list(pytorch_model.children()) if pytorch_model is not None else []
            if not layers:
                return None

            # Prefer the penultimate block: it is usually close to the detection
            # head while still carrying spatial appearance information.
            target_layer = layers[-2] if len(layers) >= 2 else layers[-1]

            def hook_fn(module, inputs, output):
                self._feature_map = output

            return target_layer.register_forward_hook(hook_fn)
        except Exception as e:
            print(f"[PersonDetector] Feature hook disabled: {e}")
            return None

    def __del__(self):
        if getattr(self, "_hook_handle", None) is not None:
            self._hook_handle.remove()

    @staticmethod
    def _pick_feature_tensor(feature):
        """Pick a 4D feature tensor from common YOLO hook output shapes."""
        if feature is None:
            return None

        if isinstance(feature, (list, tuple)):
            candidates = []
            for item in feature:
                tensor = PersonDetector._pick_feature_tensor(item)
                if tensor is not None:
                    candidates.append(tensor)
            if not candidates:
                return None
            return candidates[-1]

        if hasattr(feature, "detach"):
            tensor = feature.detach()
            if tensor.ndim == 4:
                return tensor
            if tensor.ndim == 3:
                return tensor.unsqueeze(0)

        return None

    @staticmethod
    def _normalize_vector(vec: np.ndarray, target_dim: int = 384) -> np.ndarray:
        """Pad/truncate and L2-normalize a feature vector."""
        vec = np.asarray(vec, dtype=np.float32).flatten()
        if vec.shape[0] < target_dim:
            vec = np.pad(vec, (0, target_dim - vec.shape[0]), mode="constant")
        elif vec.shape[0] > target_dim:
            vec = vec[:target_dim]

        norm = np.linalg.norm(vec)
        if norm > 0:
            vec = vec / norm
        return vec

    def _pool_person_embeddings(self, result, frame_shape, target_dim: int = 384):
        """
        Convert YOLO's captured feature map into one embedding per bbox.

        The bbox coordinates are mapped from the original frame size to the
        spatial feature map size, then average-pooled over that region.
        """
        boxes = getattr(result, "boxes", None)
        if boxes is None or len(boxes) == 0:
            return []

        feature_tensor = self._pick_feature_tensor(self._feature_map)
        if feature_tensor is None:
            return [None] * len(boxes)

        # Current pipeline processes one frame at a time, so use batch index 0.
        fmap = feature_tensor[0].float()
        channels, fmap_h, fmap_w = fmap.shape
        frame_h, frame_w = frame_shape[:2]
        embeddings = []

        for box in boxes:
            try:
                x1, y1, x2, y2 = map(float, box.xyxy[0])
                fx1 = int(np.floor(max(0.0, x1 / max(frame_w, 1) * fmap_w)))
                fy1 = int(np.floor(max(0.0, y1 / max(frame_h, 1) * fmap_h)))
                fx2 = int(np.ceil(min(float(fmap_w), x2 / max(frame_w, 1) * fmap_w)))
                fy2 = int(np.ceil(min(float(fmap_h), y2 / max(frame_h, 1) * fmap_h)))

                if fx2 <= fx1 or fy2 <= fy1:
                    embeddings.append(None)
                    continue

                roi = fmap[:, fy1:fy2, fx1:fx2]
                if roi.numel() == 0:
                    embeddings.append(None)
                    continue

                pooled = roi.mean(dim=(1, 2)).cpu().numpy()
                embeddings.append(self._normalize_vector(pooled, target_dim=target_dim))
            except Exception:
                embeddings.append(None)

        return embeddings

    def track_people(self, frame):
        self._feature_map = None
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
        result = results[0]
        self.last_person_embeddings = self._pool_person_embeddings(result, frame.shape)
        try:
            result.person_embeddings = self.last_person_embeddings
        except Exception:
            pass
        return result
