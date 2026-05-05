"""
tracker.py — Unified Tracker Wrappers
รองรับ 4 algorithms: DeepSORT | ByteTrack | BoT-SORT | BoxMOT

Interface มาตรฐาน (ทุก class):
    tracker.update(frame, yolo_model, device, conf, classes)
    → list of {"track_id": int, "bbox": (x1,y1,x2,y2), "conf": float}

👕 CLOTHING SELECTION FEATURE (BoxMOT เท่านั้น):
    - สนับสนุนการเลือก tracking เฉพาะส่วนเสื้อผ้า (upper/lower body)
    - clothing_mode: "full" (คนเต็ม), "upper" (เสื้อ/ช่วงบน), "lower" (กางเกง/ช่วงล่าง)
    - ใช้ร่วมกับ person_crops parameter เพื่อแยกส่วนต่างๆ ของร่างกาย

📝 ตัวอย่างการใช้งาน:
    # 1. Full body tracking (default)
    tracker = create_tracker("boxmot")
    
    # 2. Upper body tracking (เฉพาะเสื้อ)
    tracker = create_tracker("boxmot", clothing_mode="upper")
    
    # 3. Lower body tracking (เฉพาะกางเกง)
    tracker = create_tracker("boxmot", clothing_mode="lower")
    
    # 4. การใช้งานกับ person_crops
    tracks = tracker.update(
        frame=frame,
        yolo_model=yolo_model,
        device="cuda",
        conf=0.5,
        classes=[0],  # person class
        person_crops=person_crops  # list of cropped person images
    )
"""


# ============================================================
# DeepSORT (ใช้ Re-ID appearance feature — เสถียรที่สุดเมื่อคนซ้อนทับ)
# ต้องติดตั้ง: pip install deep-sort-realtime
# ============================================================
class DeepSortTracker:
    def __init__(self, max_age: int = 90, n_init: int = 3, max_iou_distance: float = 0.9):
        from deep_sort_realtime.deepsort_tracker import DeepSort
        self.tracker = DeepSort(
            max_age=max_age,
            n_init=n_init,
            max_iou_distance=max_iou_distance,
            embedder="mobilenet",
            half=True,
            embedder_gpu=True,
        )

    def update(self, frame, yolo_model, device: str, conf: float, classes: list) -> list:
        results = yolo_model(frame, classes=classes, conf=conf, verbose=False, device=device)
        detections = self._parse(results[0])
        if not detections:
            self.tracker.update_tracks([], frame=frame)
            return []
        raw = self.tracker.update_tracks(detections, frame=frame)
        return [
            {
                "track_id": t.track_id,
                "bbox": tuple(map(int, t.to_ltrb())),
                "conf": t.det_conf or 0.0,
            }
            for t in raw if t.is_confirmed()
        ]

    @staticmethod
    def _parse(r):
        if r is None or r.boxes is None:
            return []
        out = []
        for box in r.boxes:
            x1, y1, x2, y2 = map(float, box.xyxy[0])
            out.append(([x1, y1, x2 - x1, y2 - y1], float(box.conf[0]), "person"))
        return out


# ============================================================
# ByteTrack (built-in YOLO — เร็ว เบา เหมาะ real-time)
# ไม่ต้องติดตั้งอะไรเพิ่ม
# ============================================================
class ByteTrackTracker:
    def update(self, frame, yolo_model, device: str, conf: float, classes: list) -> list:
        results = yolo_model.track(
            frame,
            classes=classes,
            conf=conf,
            tracker="bytetrack.yaml",
            persist=True,
            verbose=False,
            device=device,
        )
        return self._parse(results[0])

    @staticmethod
    def _parse(r):
        if r is None or r.boxes is None or r.boxes.id is None:
            return []
        out = []
        for box in r.boxes:
            if box.id is None:
                continue
            x1, y1, x2, y2 = map(int, box.xyxy[0])
            out.append({
                "track_id": int(box.id[0]),
                "bbox": (x1, y1, x2, y2),
                "conf": float(box.conf[0]),
            })
        return out


# ============================================================
# BoT-SORT (built-in YOLO — แม่นกว่า ByteTrack, ใช้ camera motion compensation)
# ไม่ต้องติดตั้งอะไรเพิ่ม
# ============================================================
class BotSortTracker:
    def update(self, frame, yolo_model, device: str, conf: float, classes: list) -> list:
        results = yolo_model.track(
            frame,
            classes=classes,
            conf=conf,
            tracker="botsort.yaml",
            persist=True,
            verbose=False,
            device=device,
        )
        return self._parse(results[0])

    @staticmethod
    def _parse(r):
        if r is None or r.boxes is None or r.boxes.id is None:
            return []
        out = []
        for box in r.boxes:
            if box.id is None:
                continue
            x1, y1, x2, y2 = map(int, box.xyxy[0])
            out.append({
                "track_id": int(box.id[0]),
                "bbox": (x1, y1, x2, y2),
                "conf": float(box.conf[0]),
            })
        return out


# ============================================================
# BoxMOT (BoT-SORT standalone — รองรับ Custom Embeddings นอกโมเดล)
# ต้องติดตั้ง: pip install boxmot
# ============================================================
class BoxMotTracker:
    def __init__(self, track_buffer: int = 90, match_thresh: float = 0.9, proximity_thresh: float = 0.6, clothing_mode: str = "full"):
        from boxmot import BotSort
        from pathlib import Path
        import torch
        import sys
        from config_loader import get_reid_model_path, get_device
        
        # Clothing selection mode: "full", "upper", "lower"
        self.clothing_mode = clothing_mode.lower()
        if self.clothing_mode not in ["full", "upper", "lower"]:
            raise ValueError(f"Invalid clothing_mode '{clothing_mode}'. Use 'full', 'upper', or 'lower'")
        
        # Get reid model path from config
        reid_model_path = get_reid_model_path()
        
        # Get device from config
        config_device = get_device()
        device = config_device if config_device in ['cuda', 'cpu'] else ('cuda' if torch.cuda.is_available() and torch.cuda.device_count() > 0 else 'cpu')
        # BoxMOT expects GPU index like '0', not 'cuda'
        boxmot_device = '0' if device == 'cuda' else device
        self.tracker = BotSort(
            model_weights=Path(reid_model_path),
            reid_weights=Path(reid_model_path),
            device=boxmot_device,
            fp16=False,
            half=False,
            track_buffer=track_buffer,
            match_thresh=match_thresh,
            proximity_thresh=proximity_thresh
        )

    def update(self, frame, yolo_model, device: str, conf: float, classes: list, embeds: list = None, boxes_list: list = None, person_crops: list = None) -> list:
        import numpy as np
        import cv2
        
        # ถ้าไม่มีการผ่าน boxes เข้ามา ให้ detect เอง
        if boxes_list is None:
            results = yolo_model(frame, classes=classes, conf=conf, verbose=False, device=device)
            if not results or results[0].boxes is None:
                return []
            
            dets = []
            for box in results[0].boxes:
                x1, y1, x2, y2 = map(float, box.xyxy[0])
                c = float(box.conf[0])
                cls_id = int(box.cls[0])
                dets.append([x1, y1, x2, y2, c, cls_id])
            dets = np.array(dets)
        else:
            # แปลงรับ external bbs
            if not boxes_list:
                return []
            dets = np.array(boxes_list)
            
        if len(dets) == 0:
            return []
            
        # Handle clothing selection mode
        if self.clothing_mode != "full" and person_crops is not None:
            # Process body part crops for upper/lower body tracking
            processed_embeds = []
            for i, person_crop in enumerate(person_crops):
                if person_crop is None or person_crop.size == 0:
                    processed_embeds.append(None)
                    continue
                    
                # Split person crop into upper and lower body
                ph, pw, _ = person_crop.shape
                
                if self.clothing_mode == "upper":
                    # Upper body: 15% to 50% of person height
                    body_crop = person_crop[int(ph*0.15):int(ph*0.50), :].copy()
                elif self.clothing_mode == "lower":
                    # Lower body: 50% to 90% of person height
                    body_crop = person_crop[int(ph*0.50):int(ph*0.90), :].copy()
                else:
                    body_crop = person_crop
                
                # Use provided embedding if available, otherwise use None
                if i < len(embeds) and embeds[i] is not None:
                    processed_embeds.append(embeds[i])
                else:
                    processed_embeds.append(None)
            
            embeds = processed_embeds
            
        embs_arr = None
        if embeds and len(embeds) == len(dets):
            # Filter out None embeddings to avoid numpy inhomogeneous shape error
            valid_embeds = [e for e in embeds if e is not None]
            if len(valid_embeds) == len(dets):
                # Check for inhomogeneous shapes - all embeddings must have same dimension
                shapes = [np.array(e).shape for e in valid_embeds]
                if len(set(shapes)) == 1:
                    # All same shape - safe to convert
                    embs_arr = np.array(valid_embeds)
                else:
                    # Find most common shape and pad others
                    from collections import Counter
                    most_common_shape = Counter(shapes).most_common(1)[0][0]
                    target_dim = most_common_shape[0] if most_common_shape else 128
                    
                    padded = []
                    for e in embeds:
                        if e is not None:
                            e_arr = np.array(e)
                            if e_arr.shape[0] != target_dim:
                                if e_arr.shape[0] < target_dim:
                                    # Pad with zeros
                                    e_arr = np.pad(e_arr, (0, target_dim - e_arr.shape[0]), mode='constant')
                                else:
                                    # Truncate
                                    e_arr = e_arr[:target_dim]
                            padded.append(e_arr)
                        else:
                            padded.append(np.zeros(target_dim, dtype=np.float32))
                    embs_arr = np.array(padded)
            elif valid_embeds:
                # Some embeddings are None - pad them
                shapes = [np.array(e).shape for e in valid_embeds]
                embed_dim = shapes[0][0] if shapes else 128
                padded = []
                for e in embeds:
                    if e is not None:
                        padded.append(np.array(e))
                    else:
                        padded.append(np.zeros(embed_dim, dtype=np.float32))
                embs_arr = np.array(padded)
            
        # BoxMot signature: update(dets: ndarray, img: ndarray, embs: ndarray = None)
        # return: ndarray [x1, y1, x2, y2, track_id, conf, cls, ind]
        try:
           tracks = self.tracker.update(dets, frame, embs=embs_arr)
        except TypeError:
           # Fallback in case old version or different signature
           tracks = self.tracker.update(dets, frame)

        out = []
        for t in tracks:
            out.append({
                "track_id": int(t[4]),
                "bbox": (int(t[0]), int(t[1]), int(t[2]), int(t[3])),
                "conf": float(t[5]) if len(t) > 5 else 1.0,
                "clothing_mode": self.clothing_mode,  # Add mode info to output
            })
        return out


# ============================================================
# Factory — สร้าง tracker จากชื่อ string
# ============================================================
TRACKERS = {
    "deepsort":  DeepSortTracker,
    "bytetrack": ByteTrackTracker,
    "botsort":   BotSortTracker,
    "boxmot":    BoxMotTracker,
}

def create_tracker(name: str = "deepsort", **kwargs):
    """
    สร้าง tracker จากชื่อ
    Args:
        name: "deepsort" | "bytetrack" | "botsort" | "boxmot"
        **kwargs: 
            - สำหรับ DeepSortTracker: max_age, n_init, max_iou_distance
            - สำหรับ BoxMotTracker: track_buffer, match_thresh, proximity_thresh, clothing_mode
    """
    name = name.lower()
    if name not in TRACKERS:
        raise ValueError(f"Unknown tracker '{name}'. Choose from: {list(TRACKERS.keys())}")
    cls = TRACKERS[name]
    
    if name == "deepsort":
        return cls(**kwargs)
    elif name == "boxmot":
        # Extract BoxMot-specific parameters
        boxmot_kwargs = {
            'track_buffer': kwargs.get('track_buffer', 90),
            'match_thresh': kwargs.get('match_thresh', 0.9),
            'proximity_thresh': kwargs.get('proximity_thresh', 0.6),
            'clothing_mode': kwargs.get('clothing_mode', 'full')
        }
        return cls(**boxmot_kwargs)
    else:
        return cls()
