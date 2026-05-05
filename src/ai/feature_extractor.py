import torch
import numpy as np
import cv2
import torchvision.models as models
import torchvision.transforms as T
from ultralytics import YOLO

class ClothingEmbedder:
    """
    Feature Extractor สำหรับโมเดลเสื้อผ้า best.pt 
    เพื่อดึง Vector ลายนิ้วมือดิจิทัลที่ normalize แล้ว 
    ไว้ใช้กับการทำ Re-ID ใน Tracker
    """
    def __init__(self, model_path: str, device: str = None):
        self.device = device if device else ("cuda" if torch.cuda.is_available() else "cpu")
        print(f"[ClothingEmbedder] Loading model from {model_path} on {self.device}")
        
        self.model = YOLO(model_path)
        self.model.to(self.device)
        
        # Load Re-ID (ResNet18) 
        print(f"[ClothingEmbedder] Loading Re-ID (ResNet18) model on {self.device}")
        self.reid_model = models.resnet18(weights=models.ResNet18_Weights.IMAGENET1K_V1)
        self.reid_model = torch.nn.Sequential(*(list(self.reid_model.children())[:-1]))
        self.reid_model.to(self.device)
        self.reid_model.eval()
        
        self.reid_transforms = T.Compose([
            T.ToPILImage(),
            T.Resize((256, 128)),
            T.ToTensor(),
            T.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225])
        ])

        # ตรวจสอบว่าโมเดลรองรับ .embed() หรือไม่
        self.use_hook = False
        dummy_img = np.zeros((224, 224, 3), dtype=np.uint8)
        try:
            results = self.model.embed(source=dummy_img, verbose=False)
            self.model.predictor = None  # Reset predictor to avoid breaking future detections
            if not results or len(results) == 0:
                self.use_hook = True
        except Exception:
            self.use_hook = True
            
        if self.use_hook:
            print("[ClothingEmbedder] Native .embed() not supported, falling back to Forward Hook")
            self._setup_hook()
        else:
            print("[ClothingEmbedder] Native .embed() is supported")

    def _setup_hook(self):
        self.features = None
        def hook_fn(module, input, output):
            self.features = output.clone().detach()
            
        pytorch_model = self.model.model
        # ส่วนมาก feature จะอยู่ที่ layer ก่อน classification head
        self.hook_handle = list(pytorch_model.children())[-2].register_forward_hook(hook_fn)
        
    def __del__(self):
        if hasattr(self, 'hook_handle'):
            self.hook_handle.remove()

    def _embed_single(self, crop_img: np.ndarray) -> np.ndarray:
        """ สกัด Vector จากภาพ Crop เดี่ยวๆ 1 ภาพ """
        if crop_img is None or crop_img.size == 0:
            return None
            
        if not self.use_hook:
            # ใช้ .embed() ปกติ
            results = self.model.embed(source=crop_img, verbose=False)
            self.model.predictor = None  # Reset state after embed
            if results and len(results) > 0:
                vec = results[0]
                return vec.cpu().numpy().flatten() if hasattr(vec, 'cpu') else np.array(vec).flatten()
            else:
                return None
        else:
            # ใช้ Forward Hook
            img_resized = cv2.resize(crop_img, (224, 224))
            tensor_img = torch.from_numpy(img_resized).permute(2, 0, 1).unsqueeze(0).float() / 255.0
            tensor_img = tensor_img.to(self.device)
            
            with torch.no_grad():
                _ = self.model.model(tensor_img)
                
            if self.features is None: 
                return None
            return self.features.cpu().numpy().flatten()

    def get_embedding(self, person_crop: np.ndarray):
        """
        รับภาพเต็มของคน -> สกัด Re-ID Vector -> หาเสื้อผ้า -> สกัด Clothing Vector -> นำมาต่อหางกัน (Fusion)
        Returns: Tuple[1D numpy array (L2 normalized fused vector) หรือ None, List[str]]
                 The embedding is guaranteed to have a fixed dimension of 768.
        """
        FIXED_DIM = 768  # Fixed target dimension for all embeddings
        
        if person_crop is None or person_crop.size == 0:
            return None, []
            
        # --- 1. สกัดฟีเจอร์ Re-ID (จำหน้าตา บุคลิกทั้งหมด) ---
        try:
            rgb_crop = cv2.cvtColor(person_crop, cv2.COLOR_BGR2RGB)
            input_tensor = self.reid_transforms(rgb_crop).unsqueeze(0).to(self.device)
            with torch.no_grad():
                reid_vec = self.reid_model(input_tensor).cpu().numpy().flatten()
            norm_reid = np.linalg.norm(reid_vec)
            if norm_reid > 0:
                reid_vec = reid_vec / norm_reid
        except Exception as e:
            print(f"[ClothingEmbedder] Re-ID Feature Warning: {e}")
            reid_vec = np.zeros(512, dtype=np.float32)

        # --- 2. รัน Object Detection เพื่อหาตำแหน่งเสื้อผ้าในตัวคน ---
        results = self.model(person_crop, verbose=False)
        boxes = results[0].boxes
        names = self.model.names
        
        cloth_embs = []
        cloth_names = []
        
        # 2. ถ้าหาเจอ ตัดภาพทีละชิ้นมาสกัด Vector
        if boxes is not None and len(boxes) > 0:
            for box in boxes:
                x1, y1, x2, y2 = map(int, box.xyxy[0])
                cloth_crop = person_crop[max(y1,0):y2, max(x1,0):x2]
                
                if cloth_crop.size > 0:
                    emb = self._embed_single(cloth_crop)
                    if emb is not None:
                        cloth_embs.append(emb)
                        cls_val = int(box.cls[0])
                        cloth_names.append(names[cls_val])
                        
        # 3. ถ้าหากไม่เจอเสื้อผ้าย่อยเลย ให้วิเคราะห์รูปคนเต็มๆ แทน (Fallback)
        if len(cloth_embs) == 0:
            fused_vec = self._embed_single(person_crop)
            if fused_vec is None:
                return None, []
            # Ensure fixed dimension
            fused_vec = self._normalize_dim(fused_vec, FIXED_DIM)
            return fused_vec, ["Unknown"]
        else:
            # 4. Feature Fusion: หาค่าเฉลี่ยของ Vector เสื้อผ้าทุกชิ้นที่เจอ (Mean Pooling)
            fused_vec = np.mean(cloth_embs, axis=0)
            
        # 5. L2 Normalization ฝั่งเสื้อผ้าก่อน (แยกกัน)
        norm = np.linalg.norm(fused_vec)
        if norm > 0:
            clothing_vec = fused_vec / norm
        else:
            clothing_vec = fused_vec
            
        # 6. รวมพลัง (Concatenate) Re-ID + Clothing
        final_vec = np.concatenate([reid_vec, clothing_vec])
        
        # 7. Ensure fixed dimension (pad or truncate to FIXED_DIM)
        final_vec = self._normalize_dim(final_vec, FIXED_DIM)
        
        final_norm = np.linalg.norm(final_vec)
        if final_norm > 0:
            final_vec = final_vec / final_norm
            
        return final_vec, cloth_names

    def _normalize_dim(self, vec: np.ndarray, target_dim: int) -> np.ndarray:
        """Pad or truncate vector to target dimension"""
        if vec.shape[0] == target_dim:
            return vec
        elif vec.shape[0] < target_dim:
            # Pad with zeros
            return np.pad(vec, (0, target_dim - vec.shape[0]), mode='constant')
        else:
            # Truncate
            return vec[:target_dim]

    def get_embeddings_batch(self, crops: list) -> list:
        """
        Process multiple crops in batch for better GPU utilization
        Returns: List of tuples (embedding, labels)
        """
        if not crops:
            return []
        
        FIXED_DIM = 768
        results = []
        
        # Process in batch for Re-ID (more efficient)
        try:
            import torch
            reid_vectors = []
            for crop in crops:
                rgb_crop = cv2.cvtColor(crop, cv2.COLOR_BGR2RGB)
                input_tensor = self.reid_transforms(rgb_crop).unsqueeze(0).to(self.device)
                with torch.no_grad():
                    reid_vec = self.reid_model(input_tensor).cpu().numpy().flatten()
                norm = np.linalg.norm(reid_vec)
                if norm > 0:
                    reid_vec = reid_vec / norm
                reid_vectors.append(reid_vec)
        except Exception as e:
            print(f"[ClothingEmbedder] Batch Re-ID Warning: {e}")
            reid_vectors = [np.zeros(512, dtype=np.float32) for _ in crops]
        
        # Process clothing detection per crop (can't easily batch YOLO on different sized crops)
        for i, crop in enumerate(crops):
            reid_vec = reid_vectors[i]
            
            # Run clothing detection
            det_results = self.model(crop, verbose=False)
            boxes = det_results[0].boxes
            names = self.model.names
            
            cloth_embs = []
            cloth_names = []
            
            if boxes is not None and len(boxes) > 0:
                for box in boxes:
                    x1, y1, x2, y2 = map(int, box.xyxy[0])
                    cloth_crop = crop[max(y1,0):y2, max(x1,0):x2]
                    
                    if cloth_crop.size > 0:
                        emb = self._embed_single(cloth_crop)
                        if emb is not None:
                            cloth_embs.append(emb)
                            cls_val = int(box.cls[0])
                            cloth_names.append(names[cls_val])
            
            # Create final embedding
            if len(cloth_embs) == 0:
                # No clothing detected - use full crop embedding
                fused_vec = self._embed_single(crop)
                if fused_vec is None:
                    results.append((None, ["Unknown"]))
                    continue
                fused_vec = self._normalize_dim(fused_vec, FIXED_DIM)
                results.append((fused_vec, ["Unknown"]))
            else:
                # Fuse clothing embeddings
                fused_vec = np.mean(cloth_embs, axis=0)
                norm = np.linalg.norm(fused_vec)
                if norm > 0:
                    clothing_vec = fused_vec / norm
                else:
                    clothing_vec = fused_vec
                
                # Concatenate Re-ID + Clothing
                final_vec = np.concatenate([reid_vec, clothing_vec])
                final_vec = self._normalize_dim(final_vec, FIXED_DIM)
                
                # Normalize
                final_norm = np.linalg.norm(final_vec)
                if final_norm > 0:
                    final_vec = final_vec / final_norm
                
                results.append((final_vec, cloth_names))
        
        return results
