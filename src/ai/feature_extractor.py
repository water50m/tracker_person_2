import torch
import numpy as np
import cv2
from ultralytics import YOLO

class ClothingEmbedder:
    """
    Feature Extractor สำหรับโมเดล YOLO person detector และโมเดลเสื้อผ้า
    เพื่อดึง Vector ลายนิ้วมือดิจิทัลที่ normalize แล้ว
    ไว้ใช้กับการทำ Re-ID ใน Tracker
    """
    def __init__(self, model_path: str, device: str = None, person_model_path: str = None):
        self.device = device if device else ("cuda" if torch.cuda.is_available() else "cpu")
        print(f"[ClothingEmbedder] Loading clothing model from {model_path} on {self.device}")
        
        self.model = YOLO(model_path)
        self.model.to(self.device)

        # ตรวจสอบว่าโมเดลรองรับ .embed() หรือไม่ ถ้าไม่รองรับจะ fallback เป็น hook
        # person_model_path เป็น fallback เท่านั้น; path ปกติใช้ embedding ที่ได้จาก
        # PersonDetector.track_people() รอบเดียวกับการตรวจจับ
        self.person_model = None
        self.use_clothing_hook = False
        self.use_person_hook = False
        dummy_img = np.zeros((224, 224, 3), dtype=np.uint8)
        self.use_clothing_hook = not self._supports_native_embed(self.model, dummy_img)

        self.clothing_features = None
        self.person_features = None
        self.clothing_hook_handle = None
        self.person_hook_handle = None

        if person_model_path is not None:
            print(f"[ClothingEmbedder] Loading fallback person embedding model from {person_model_path} on {self.device}")
            self.person_model = YOLO(person_model_path)
            self.person_model.to(self.device)
            self.use_person_hook = not self._supports_native_embed(self.person_model, dummy_img)

        if self.use_clothing_hook:
            print("[ClothingEmbedder] Clothing model .embed() not supported, using Forward Hook")
            self.clothing_hook_handle = self._setup_hook(self.model, "clothing_features")
        else:
            print("[ClothingEmbedder] Clothing model native .embed() is supported")

        if self.person_model is not None:
            if self.use_person_hook:
                print("[ClothingEmbedder] Person model .embed() not supported, using Forward Hook")
                self.person_hook_handle = self._setup_hook(self.person_model, "person_features")
            else:
                print("[ClothingEmbedder] Person model native .embed() is supported")

    def _supports_native_embed(self, model: YOLO, dummy_img: np.ndarray) -> bool:
        try:
            results = model.embed(source=dummy_img, verbose=False)
            model.predictor = None  # Reset predictor to avoid breaking future detections
            return bool(results and len(results) > 0)
        except Exception:
            return False

    def _setup_hook(self, model: YOLO, feature_attr: str):
        def hook_fn(module, input, output):
            setattr(self, feature_attr, output)
            
        pytorch_model = model.model
        if hasattr(pytorch_model, "model"):
            layers = list(pytorch_model.model)
        else:
            layers = list(pytorch_model.children())
        # ส่วนมาก feature จะอยู่ที่ layer ก่อน classification head
        return layers[-2].register_forward_hook(hook_fn)
        
    def __del__(self):
        for handle_name in ("clothing_hook_handle", "person_hook_handle"):
            handle = getattr(self, handle_name, None)
            if handle is not None:
                handle.remove()

    def _feature_to_numpy(self, feature) -> np.ndarray:
        """Convert YOLO embed/hook output to a flat numpy vector."""
        if isinstance(feature, (list, tuple)):
            feature = next((f for f in reversed(feature) if hasattr(f, "detach") or hasattr(f, "cpu")), feature[-1])
        if hasattr(feature, "detach"):
            feature = feature.detach()
        if hasattr(feature, "cpu"):
            feature = feature.cpu()
        arr = feature.numpy() if hasattr(feature, "numpy") else np.array(feature)
        arr = np.asarray(arr)
        if arr.ndim == 4:
            arr = arr.mean(axis=(2, 3))
        return arr.flatten().astype(np.float32)

    def _embed_with_model(
        self,
        model: YOLO,
        crop_img: np.ndarray,
        use_hook: bool,
        feature_attr: str,
    ) -> np.ndarray:
        if crop_img is None or crop_img.size == 0:
            return None

        if not use_hook:
            results = model.embed(source=crop_img, verbose=False)
            model.predictor = None  # Reset state after embed
            if results and len(results) > 0:
                return self._feature_to_numpy(results[0])
            return None

        setattr(self, feature_attr, None)
        img_resized = cv2.resize(crop_img, (224, 224))
        tensor_img = torch.from_numpy(img_resized).permute(2, 0, 1).unsqueeze(0).float() / 255.0
        tensor_img = tensor_img.to(self.device)

        with torch.no_grad():
            _ = model.model(tensor_img)

        feature = getattr(self, feature_attr)
        if feature is None:
            return None
        return self._feature_to_numpy(feature)

    def _embed_single(self, crop_img: np.ndarray) -> np.ndarray:
        """สกัด Vector จากภาพเสื้อผ้า 1 crop ด้วย YOLO เสื้อผ้า"""
        return self._embed_with_model(
            self.model,
            crop_img,
            self.use_clothing_hook,
            "clothing_features",
        )

    def _embed_person(self, person_crop: np.ndarray) -> np.ndarray:
        """สกัด Vector จากภาพคนด้วย fallback YOLO person detector ถ้ามี"""
        if self.person_model is None:
            return None
        return self._embed_with_model(
            self.person_model,
            person_crop,
            self.use_person_hook,
            "person_features",
        )

    def get_embedding(self, person_crop: np.ndarray, person_embedding: np.ndarray = None):
        """
        รับภาพเต็มของคน -> ใช้ Person Vector จาก YOLO detector รอบแรก
        -> หาเสื้อผ้า -> สกัด Clothing Vector -> นำมาต่อหางกัน (Fusion)
        Returns: Tuple[1D numpy array (L2 normalized fused vector) หรือ None, List[str]]
                 The embedding is guaranteed to have a fixed dimension of 768.
        """
        FIXED_DIM = 768  # Fixed target dimension for all embeddings
        HALF_DIM = FIXED_DIM // 2
        
        if person_crop is None or person_crop.size == 0:
            return None, []
            
        # --- 1. ใช้ฟีเจอร์จาก YOLO person detector รอบแรก ถ้ามี ---
        try:
            person_vec = person_embedding
            if person_vec is None:
                person_vec = self._embed_person(person_crop)
            if person_vec is None:
                person_vec = np.zeros(HALF_DIM, dtype=np.float32)
            person_vec = self._normalize_dim(person_vec, HALF_DIM)
            norm_person = np.linalg.norm(person_vec)
            if norm_person > 0:
                person_vec = person_vec / norm_person
        except Exception as e:
            print(f"[ClothingEmbedder] Person detector feature warning: {e}")
            person_vec = np.zeros(HALF_DIM, dtype=np.float32)

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
            final_vec = np.concatenate([person_vec, np.zeros(HALF_DIM, dtype=np.float32)])
            final_norm = np.linalg.norm(final_vec)
            if final_norm > 0:
                final_vec = final_vec / final_norm
            return final_vec, ["Unknown"]
        else:
            # 4. Feature Fusion: หาค่าเฉลี่ยของ Vector เสื้อผ้าทุกชิ้นที่เจอ (Mean Pooling)
            fused_vec = np.mean(cloth_embs, axis=0)
            
        # 5. L2 Normalization ฝั่งเสื้อผ้าก่อน (แยกกัน)
        norm = np.linalg.norm(fused_vec)
        if norm > 0:
            clothing_vec = fused_vec / norm
        else:
            clothing_vec = fused_vec
            
        # 6. รวมพลัง (Concatenate) Person YOLO + Clothing YOLO
        clothing_vec = self._normalize_dim(clothing_vec, HALF_DIM)
        final_vec = np.concatenate([person_vec, clothing_vec])
        
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
        HALF_DIM = FIXED_DIM // 2
        results = []
        
        # Process person embeddings with YOLO person detector
        try:
            person_vectors = []
            for crop in crops:
                person_vec = self._embed_person(crop)
                if person_vec is None:
                    person_vec = np.zeros(HALF_DIM, dtype=np.float32)
                person_vec = self._normalize_dim(person_vec, HALF_DIM)
                norm = np.linalg.norm(person_vec)
                if norm > 0:
                    person_vec = person_vec / norm
                person_vectors.append(person_vec)
        except Exception as e:
            print(f"[ClothingEmbedder] Batch Person YOLO Feature Warning: {e}")
            person_vectors = [np.zeros(HALF_DIM, dtype=np.float32) for _ in crops]
        
        # Process clothing detection per crop (can't easily batch YOLO on different sized crops)
        for i, crop in enumerate(crops):
            person_vec = person_vectors[i]
            
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
                # No clothing detected - use person detector embedding only
                final_vec = np.concatenate([person_vec, np.zeros(HALF_DIM, dtype=np.float32)])
                final_norm = np.linalg.norm(final_vec)
                if final_norm > 0:
                    final_vec = final_vec / final_norm
                results.append((final_vec, ["Unknown"]))
            else:
                # Fuse clothing embeddings
                fused_vec = np.mean(cloth_embs, axis=0)
                norm = np.linalg.norm(fused_vec)
                if norm > 0:
                    clothing_vec = fused_vec / norm
                else:
                    clothing_vec = fused_vec
                
                # Concatenate Person YOLO + Clothing YOLO
                clothing_vec = self._normalize_dim(clothing_vec, HALF_DIM)
                final_vec = np.concatenate([person_vec, clothing_vec])
                
                # Normalize
                final_norm = np.linalg.norm(final_vec)
                if final_norm > 0:
                    final_vec = final_vec / final_norm
                
                results.append((final_vec, cloth_names))
        
        return results
