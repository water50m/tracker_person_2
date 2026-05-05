import os
import torch  
from ultralytics import YOLO
import sys
from pathlib import Path

# Add parent directory to path for config_loader import
sys.path.insert(0, str(Path(__file__).parent.parent))
from config_loader import get_classifier_model_path, get_device

class ClothingClassifier:
    def __init__(self, model_path=None):
        self.model = None
        
        # Load model path from config if not provided
        if model_path is None:
            model_path = get_classifier_model_path()
        
        # Get device from config
        config_device = get_device()
        self.device = config_device if config_device in ['cuda', 'cpu'] else ('cuda' if torch.cuda.is_available() else 'cpu')
        print(f"👕 Clothing Classifier using device: {self.device.upper()}")

        if not os.path.exists(model_path):
            print(f"⚠️ Warning: Model file not found at '{model_path}'")
            return

        try:
            self.model = YOLO(model_path)
            self.model.to(self.device)
            print(f"✅ Clothing Classifier Loaded! ({model_path})")
        except Exception as e:
            print(f"❌ Error loading model: {e}")
            self.model = None

    def predict(self, image_crop):
        if self.model is None or image_crop is None or image_crop.size == 0:
            return "Unknown", 0.0, None

        try:
            # 4. ส่ง device เข้าไปตอน predict
            results = self.model(image_crop, verbose=False, device=self.device)
            
            # ... (โค้ดส่วนอ่านผลลัพธ์เหมือนเดิม) ...
            if not results: return "Unknown", 0.0, None
            result = results[0]
            
            if hasattr(result, 'probs') and result.probs is not None:
                top1_index = result.probs.top1
                class_name = result.names[top1_index]
                conf = result.probs.top1conf.item()
                return class_name, conf, None
            
            elif hasattr(result, 'boxes') and result.boxes is not None and len(result.boxes) > 0:
                best_box = sorted(result.boxes, key=lambda x: x.conf.item(), reverse=True)[0]
                class_id = int(best_box.cls.item())
                class_name = result.names[class_id]
                conf = best_box.conf.item()
                bbox = tuple(map(int, best_box.xyxy[0].tolist()))  # (x1, y1, x2, y2)
                return class_name, conf, bbox

            return "Unknown", 0.0, None

        except Exception as e:
            print(f"⚠️ Prediction Error: {e}")
            return "Unknown", 0.0, None

    def predict_top_n(self, image_crop, top_n=5):
        """
        Return top N predictions with confidence scores.
        
        Args:
            image_crop: Cropped image of clothing
            top_n: Number of top predictions to return (default 5, use -1 or 'all' for all)
        
        Returns:
            List of tuples: [(class_name, confidence, bbox), ...] sorted by confidence desc
        """
        if self.model is None or image_crop is None or image_crop.size == 0:
            return [("Unknown", 0.0, None)]

        try:
            results = self.model(image_crop, verbose=False, device=self.device)
            
            if not results:
                return [("Unknown", 0.0, None)]
            result = results[0]
            
            predictions = []
            
            # For classification model (probs)
            if hasattr(result, 'probs') and result.probs is not None:
                # Get top N indices and confidences
                probs_tensor = result.probs.data
                num_classes = len(probs_tensor)
                
                # Determine how many to return
                if top_n == -1 or top_n == "all":
                    n = num_classes
                else:
                    n = min(top_n, num_classes)
                
                # Get top N
                top_indices = torch.topk(probs_tensor, n).indices.tolist()
                
                for idx in top_indices:
                    class_name = result.names[idx]
                    conf = probs_tensor[idx].item()
                    predictions.append((class_name, conf, None))
                
                return predictions if predictions else [("Unknown", 0.0, None)]
            
            # For detection model (boxes)
            elif hasattr(result, 'boxes') and result.boxes is not None and len(result.boxes) > 0:
                # Sort all boxes by confidence
                sorted_boxes = sorted(result.boxes, key=lambda x: x.conf.item(), reverse=True)
                
                # Determine how many to return
                if top_n == -1 or top_n == "all":
                    n = len(sorted_boxes)
                else:
                    n = min(top_n, len(sorted_boxes))
                
                for box in sorted_boxes[:n]:
                    class_id = int(box.cls.item())
                    class_name = result.names[class_id]
                    conf = box.conf.item()
                    bbox = tuple(map(int, box.xyxy[0].tolist()))
                    predictions.append((class_name, conf, bbox))
                
                return predictions if predictions else [("Unknown", 0.0, None)]

            return [("Unknown", 0.0, None)]

        except Exception as e:
            print(f"⚠️ Prediction Top-N Error: {e}")
            return [("Unknown", 0.0, None)]