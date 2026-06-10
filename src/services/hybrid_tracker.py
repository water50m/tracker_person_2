"""
hybrid_tracker.py - Hybrid Tracking with Re-ID

This module provides the HybridTracker class which combines ByteTrack
with persistent Re-ID tracking for consistent person IDs across frames.

Key Features:
- ByteTrack ID mapping to persistent IDs
- Lost track recovery using Re-ID embeddings
- Track history storage for image path reuse
- Thread-safe operations per camera

Usage:
    from services.hybrid_tracker import HybridTracker
    
    tracker = HybridTracker()
    
    # Process detection
    our_id = tracker.match_or_create_track(
        camera_id="CAM-01",
        byte_id=byte_track_id,
        person_crop=person_image,
        embedder=clothing_embedder,
    )
    
    # Store image path for reuse
    tracker.store_image_path(camera_id, our_id, "image_path", minio_url)
    
    # Cleanup when stream stops
    tracker.cleanup(camera_id)
"""

import time
import threading
from typing import Dict, Optional, List, Any, Tuple
from dataclasses import dataclass, field
from collections import defaultdict

import numpy as np

# Add parent directory for imports
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from services.ai_processing_types import PersonDetection


QUALITY_BUFFER_SIZE = 5    # จำนวน frame สูงสุดที่เก็บใน rolling buffer
QUALITY_MIN_STORE   = 0.5  # quality ต่ำสุดที่จะเพิ่มเข้า buffer


def compute_bbox_quality(
    bbox: Tuple[int, int, int, int],
    all_bboxes: List[Tuple[int, int, int, int]],
    frame_w: int,
    frame_h: int,
    edge_pad: int = 5,
) -> float:
    """คำนวณ quality ของ crop [0,1]: 1=สะอาด/ครบ, 0=แย่มาก"""
    x1, y1, x2, y2 = bbox
    bw, bh = x2 - x1, y2 - y1
    if bw <= 0 or bh <= 0:
        return 0.0

    in_frame = (x1 >= edge_pad and y1 >= edge_pad
                and x2 <= frame_w - edge_pad and y2 <= frame_h - edge_pad)

    max_iou = 0.0
    for ob in all_bboxes:
        if ob == bbox:
            continue
        ox1, oy1, ox2, oy2 = ob
        ix1, iy1 = max(x1, ox1), max(y1, oy1)
        ix2, iy2 = min(x2, ox2), min(y2, oy2)
        inter = max(0, ix2 - ix1) * max(0, iy2 - iy1)
        if inter == 0:
            continue
        union = bw * bh + (ox2 - ox1) * (oy2 - oy1) - inter
        if union > 0:
            max_iou = max(max_iou, inter / union)

    q = 1.0
    if not in_frame:
        q *= 0.6
    q *= max(0.2, 1.0 - max_iou * 1.5)
    return round(min(1.0, q), 3)


def _merge_color_buffer(buffer: List[Tuple[Dict, float]]) -> Dict[str, float]:
    """Weighted average ของ color distributions จาก buffer [(colors, quality), ...]"""
    if not buffer:
        return {}
    merged: Dict[str, float] = {}
    total_w = sum(q for _, q in buffer)
    if total_w == 0:
        return {}
    for colors, q in buffer:
        s = sum(colors.values()) or 1.0
        w = q / total_w
        for k, v in colors.items():
            merged[k] = merged.get(k, 0.0) + (v / s) * w
    return merged


@dataclass
class TrackFeatures:
    """Features for a tracked person."""
    detailed_colors: Dict[str, float] = field(default_factory=dict)
    color_groups: Dict[str, float] = field(default_factory=dict)
    embedding: Optional[List[float]] = None
    clothes: List[str] = field(default_factory=list)
    last_seen: float = field(default_factory=time.time)
    frame_number: int = 0
    last_bbox: Optional[Tuple[int, int, int, int]] = None
    frame_size: Optional[Tuple[int, int]] = None
    feature_quality: float = 1.0  # quality ของ stored feature [0,1]


@dataclass
class HybridTrackState:
    """State for hybrid tracking per camera."""
    id_mapping: Dict[int, int] = field(default_factory=dict)  # {byte_id: our_id}
    lost_tracks: Dict[int, TrackFeatures] = field(default_factory=dict)  # {our_id: features}
    next_our_id: int = 1
    track_history: Dict[int, Dict[str, Any]] = field(default_factory=dict)  # {our_id: metadata}
    lock: threading.Lock = field(default_factory=threading.Lock)
    active_byte_ids: set = field(default_factory=set)  # byte_ids seen last frame


class HybridTracker:
    """
    Hybrid tracking manager combining ByteTrack with Re-ID.
    
    This class provides persistent person IDs across frames by:
    1. Mapping ByteTrack IDs to our persistent IDs
    2. Recovering lost tracks using Re-ID similarity
    3. Storing track metadata for image path reuse
    
    Thread-safe for use across multiple cameras.
    """
    
    def __init__(self, recovery_threshold: float = 0.65):
        """
        Initialize the HybridTracker.
        
        Args:
            recovery_threshold: Similarity threshold for track recovery (0-1)
        """
        self._states: Dict[str, HybridTrackState] = {}
        self._recovery_threshold = recovery_threshold
        self._global_lock = threading.Lock()
    
    def _get_or_create_state(self, camera_id: str) -> HybridTrackState:
        """Get or create tracking state for a camera."""
        if camera_id not in self._states:
            with self._global_lock:
                if camera_id not in self._states:
                    self._states[camera_id] = HybridTrackState()
        return self._states[camera_id]
    
    def update_frame_byte_ids(self, camera_id: str, byte_ids: set):
        """
        Call after ALL detections in a frame are processed.
        Updates which byte_ids were active this frame (used next frame to
        detect ByteTrack recoveries).
        """
        state = self._get_or_create_state(camera_id)
        with state.lock:
            state.active_byte_ids = set(byte_ids)

    def match_or_create_track(
        self,
        camera_id: str,
        byte_id: Optional[int],
        person_crop: Optional[np.ndarray] = None,
        embedder = None,
        detailed_colors: Optional[Dict[str, float]] = None,
        color_groups: Optional[Dict[str, float]] = None,
        precomputed_embedding: Optional[np.ndarray] = None,
    ) -> Tuple[int, bool, bool, Optional[bool]]:
        """
        Match ByteTrack ID to our persistent ID or create new track.

        Args:
            camera_id: Camera identifier
            byte_id: ByteTrack ID (can be None)
            person_crop: Person crop image for Re-ID
            embedder: ClothingEmbedder for feature extraction
            detailed_colors: Color features (if already computed)
            color_groups: Color group features (if already computed)

        Returns:
            Tuple of (our_id, is_new_track, is_recovered_track, bytetrack_verified)
            bytetrack_verified:
              None  — ไม่ใช่ ByteTrack recovery (tracking ปกติหรือ new track)
              True  — ByteTrack recover แล้ว HybridTracker ยืนยัน (score ≥ threshold)
              False — ByteTrack recover แต่ HybridTracker ปฏิเสธ (score < threshold → new ID)
        """
        state = self._get_or_create_state(camera_id)

        with state.lock:
            if byte_id is None:
                our_id = state.next_our_id
                state.next_our_id += 1
                return our_id, True, False, None

            if byte_id in state.id_mapping:
                our_id = state.id_mapping[byte_id]

                # ── ByteTrack recovery detection ──────────────────────────────
                # byte_id รู้จักแต่ไม่ได้อยู่ใน frame ที่แล้ว → ByteTrack recover เอง
                if byte_id not in state.active_byte_ids and detailed_colors is not None:
                    hist = state.track_history.get(our_id, {})
                    stored = TrackFeatures(
                        detailed_colors=hist.get("detailed_colors", {}),
                        color_groups=hist.get("color_groups", {}),
                        embedding=hist.get("embedding"),
                        clothes=hist.get("clothes", []),
                    )
                    current = TrackFeatures(
                        detailed_colors=detailed_colors,
                        color_groups=color_groups or {},
                        embedding=precomputed_embedding.tolist() if precomputed_embedding is not None else None,
                        clothes=[],
                    )
                    score = self._calculate_similarity(current, stored)

                    if score >= self._recovery_threshold:
                        print(f"✅ [HybridTracker] ByteTrack recovery CONFIRMED: our_id={our_id} "
                              f"byte_id={byte_id} score={score:.3f}")
                        return our_id, False, False, True
                    else:
                        # ByteTrack ผิด — สร้าง our_id ใหม่ แต่ยังเก็บ byte_id mapping เดิมไว้
                        # (ลบ mapping เดิมก่อน แล้ว remap ไปยัง id ใหม่)
                        del state.id_mapping[byte_id]
                        new_id = state.next_our_id
                        state.id_mapping[byte_id] = new_id
                        state.next_our_id += 1
                        print(f"❌ [HybridTracker] ByteTrack recovery REJECTED: our_id={our_id}→{new_id} "
                              f"byte_id={byte_id} score={score:.3f}")
                        return new_id, True, False, False

                # tracking ปกติ (ต่อเนื่องทุก frame)
                return our_id, False, False, None
            
            # New ByteTrack ID - try to recover from lost tracks.
            # Recovery is attempted when:
            #   a) embedder is available (full feature extraction), OR
            #   b) detailed_colors are pre-computed (color-only recovery)
            has_features = (
                (person_crop is not None and person_crop.size > 0 and embedder is not None)
                or (detailed_colors is not None)
            )
            if has_features:
                try:
                    embedding = None
                    clothes = []

                    if embedder is not None and person_crop is not None and person_crop.size > 0:
                        if precomputed_embedding is not None:
                            embedding = precomputed_embedding
                        else:
                            embedding, clothes = embedder.get_embedding(person_crop)

                    # Use pre-computed colors if provided; recompute only when needed
                    if (detailed_colors is None or color_groups is None) and state.lost_tracks:
                        if person_crop is not None and person_crop.size > 0:
                            from src.ai.color_system import analyze_detailed_colors, get_color_groups
                            detailed_colors = analyze_detailed_colors(person_crop)
                            color_groups = get_color_groups(detailed_colors)

                    new_features = TrackFeatures(
                        detailed_colors=detailed_colors or {},
                        color_groups=color_groups or {},
                        embedding=embedding.tolist() if embedding is not None else None,
                        clothes=clothes if clothes else [],
                        last_seen=time.time(),
                    )

                    # Try to match with lost tracks
                    recovered_id = self._match_lost_track(state, new_features)

                    if recovered_id is not None:
                        # Recovered track
                        state.id_mapping[byte_id] = recovered_id
                        del state.lost_tracks[recovered_id]
                        print(f"🔄 [HybridTracker] Track recovered: {recovered_id} (byte_id: {byte_id})")
                        return recovered_id, False, True, None

                    # New track
                    our_id = state.next_our_id
                    state.id_mapping[byte_id] = our_id
                    state.next_our_id += 1
                    print(f"🆕 [HybridTracker] New track: {our_id} (byte_id: {byte_id})")
                    return our_id, True, False, None

                except Exception as e:
                    print(f"⚠️ [HybridTracker] Re-ID matching error: {e}")
                    our_id = state.next_our_id
                    state.id_mapping[byte_id] = our_id
                    state.next_our_id += 1
                    return our_id, True, False, None
            else:
                # No features available: create new track
                our_id = state.next_our_id
                state.id_mapping[byte_id] = our_id
                state.next_our_id += 1
                return our_id, True, False, None
    
    def _match_lost_track(
        self,
        state: HybridTrackState,
        new_features: TrackFeatures,
    ) -> Optional[int]:
        """
        Try to match new features with lost tracks.
        
        Args:
            state: Camera tracking state
            new_features: Features of the new detection
        
        Returns:
            Recovered track ID or None
        """
        if not state.lost_tracks:
            return None
        
        best_match = None
        best_score = 0.0
        
        for our_id, lost_features in list(state.lost_tracks.items()):
            # Calculate similarity
            score = self._calculate_similarity(new_features, lost_features)
            
            if score > best_score and score >= self._recovery_threshold:
                best_score = score
                best_match = our_id
        
        return best_match
    
    def _calculate_similarity(
        self,
        features1: TrackFeatures,
        features2: TrackFeatures,
    ) -> float:
        """
        Calculate similarity using weighted color + clothes (+ optional embedding).
        Weights come from reid config: color_weight, clothes_weight.
        """
        try:
            from src.config_loader import get_reid_config
            cfg = get_reid_config()
        except Exception:
            cfg = {"use_embedding": False, "color_weight": 0.6, "clothes_weight": 0.4}

        use_embedding = cfg.get("use_embedding", False)
        color_w = float(cfg.get("color_weight", 0.6))
        clothes_w = float(cfg.get("clothes_weight", 0.4))

        weighted_sum = 0.0
        total_weight = 0.0

        # ── Color similarity (quality-weighted L1) ──
        # ถ้า stored=0% สำหรับสีใด → อาจเป็นเพราะ crop แย่ ไม่ใช่ว่าไม่มีสีนั้นจริง
        # ปรับ penalty ด้วย stored_quality: Δ_effective = Δ × stored_quality
        c1 = features1.detailed_colors or {}  # new detection (try recover)
        c2 = features2.detailed_colors or {}  # stored / lost track
        stored_quality = max(0.1, features2.feature_quality)
        if c1 and c2:
            s1_total = sum(c1.values()) or 1.0
            s2_total = sum(c2.values()) or 1.0
            all_colors = set(c1) | set(c2)
            l1 = 0.0
            for k in all_colors:
                p1 = c1.get(k, 0.0) / s1_total
                p2 = c2.get(k, 0.0) / s2_total
                delta = abs(p1 - p2)
                # stored=0 และ quality ต่ำ → ลด penalty (ไม่แน่ใจว่าไม่มีสีจริง)
                if p2 == 0.0:
                    delta = delta * stored_quality
                l1 += delta
            color_sim = float(max(0.0, 1.0 - l1 / 2.0))
            weighted_sum += color_w * color_sim
            total_weight += color_w

        # ── Clothes similarity (Jaccard of class name sets) ──
        s1 = set(features1.clothes or [])
        s2 = set(features2.clothes or [])
        if s1 and s2:
            inter = len(s1 & s2)
            union = len(s1 | s2)
            clothes_sim = inter / union if union > 0 else 0.0
            weighted_sum += clothes_w * clothes_sim
            total_weight += clothes_w

        # ── Embedding similarity (cosine) ──
        emb_w = total_weight if total_weight > 0 else 1.0
        if use_embedding and features1.embedding and features2.embedding:
            try:
                emb1 = np.array(features1.embedding)
                emb2 = np.array(features2.embedding)
                dot = np.dot(emb1, emb2)
                norm1 = np.linalg.norm(emb1)
                norm2 = np.linalg.norm(emb2)
                if norm1 > 0 and norm2 > 0:
                    emb_sim = float(dot / (norm1 * norm2))
                    weighted_sum += emb_w * emb_sim
                    total_weight += emb_w
            except Exception:
                pass

        # ── Position similarity (center distance, normalized by frame diagonal) ──
        # ใช้เป็น tiebreaker weight เล็กน้อย ไม่ใช่ตัวตัดสินหลัก
        pos_w = float(cfg.get("position_weight", 0.1))
        b1 = features1.last_bbox
        b2 = features2.last_bbox
        fs = features1.frame_size or features2.frame_size
        if b1 and b2 and fs:
            cx1 = (b1[0] + b1[2]) / 2.0; cy1 = (b1[1] + b1[3]) / 2.0
            cx2 = (b2[0] + b2[2]) / 2.0; cy2 = (b2[1] + b2[3]) / 2.0
            dist = ((cx1 - cx2) ** 2 + (cy1 - cy2) ** 2) ** 0.5
            diag = (fs[0] ** 2 + fs[1] ** 2) ** 0.5
            dist_norm = dist / diag if diag > 0 else 1.0
            pos_sim = max(0.0, 1.0 - dist_norm * 3.0)  # =0 เมื่อ dist > 33% ของ diagonal
            weighted_sum += pos_w * pos_sim
            total_weight += pos_w

        return weighted_sum / total_weight if total_weight > 0 else 0.0
    
    def update_lost_tracks(self, camera_id: str, current_ids: List[int], max_age: float = 2.0):
        """
        Update lost tracks - mark tracks not seen recently as lost.
        
        Args:
            camera_id: Camera identifier
            current_ids: List of currently active our_ids
            max_age: Maximum age in seconds before marking as lost
        """
        state = self._get_or_create_state(camera_id)
        
        with state.lock:
            current_time = time.time()
            active_ids = set(current_ids)

            # Move inactive tracks to lost_tracks and remove from active mapping
            for byte_id, our_id in list(state.id_mapping.items()):
                if our_id not in active_ids:
                    if our_id not in state.lost_tracks and our_id in state.track_history:
                        history = state.track_history[our_id]
                        state.lost_tracks[our_id] = TrackFeatures(
                            detailed_colors=history.get("detailed_colors", {}),
                            color_groups=history.get("color_groups", {}),
                            embedding=history.get("embedding"),
                            clothes=history.get("clothes", []),
                            last_seen=current_time,
                            last_bbox=history.get("last_bbox"),
                            frame_size=history.get("frame_size"),
                            feature_quality=history.get("color_quality", history.get("last_quality", 1.0)),
                        )
                        print(f"💨 [HybridTracker] Track {our_id} marked as lost")
                    del state.id_mapping[byte_id]

            # Remove lost tracks that exceeded max_age (seconds)
            for our_id, lost_features in list(state.lost_tracks.items()):
                age = current_time - lost_features.last_seen
                if age > max_age:
                    del state.lost_tracks[our_id]
                    print(f"🗑️ [HybridTracker] Track {our_id} expired after {age:.1f}s")
    
    def store_track_features(
        self,
        camera_id: str,
        our_id: int,
        detailed_colors: Optional[Dict[str, float]] = None,
        color_groups: Optional[Dict[str, float]] = None,
        embedding: Optional[List[float]] = None,
        clothes: Optional[List[str]] = None,
        bbox: Optional[Tuple[int, int, int, int]] = None,
        frame_size: Optional[Tuple[int, int]] = None,
        quality: float = 1.0,
    ):
        """Store features for a track. Updates rolling color buffer if quality is high enough."""
        state = self._get_or_create_state(camera_id)

        with state.lock:
            hist = state.track_history.setdefault(our_id, {})

            if embedding is not None:
                hist["embedding"] = embedding
            if clothes is not None:
                hist["clothes"] = clothes
            if bbox is not None:
                hist["last_bbox"] = bbox
            if frame_size is not None:
                hist["frame_size"] = frame_size
            hist["last_quality"] = quality

            # Rolling color buffer — เก็บเฉพาะ frame ที่ quality สูงพอ
            if detailed_colors is not None and quality >= QUALITY_MIN_STORE:
                buf: List = hist.setdefault("color_buffer", [])
                buf.append((dict(detailed_colors), quality))
                if len(buf) > QUALITY_BUFFER_SIZE:
                    buf.pop(0)
                # Merged colors เป็น weighted average ของ buffer
                hist["detailed_colors"] = _merge_color_buffer(buf)
                hist["color_quality"]   = sum(q for _, q in buf) / len(buf)
            elif detailed_colors is not None and "detailed_colors" not in hist:
                # ถ้า quality ต่ำแต่ยังไม่มีข้อมูลเลย — เก็บไว้ก่อนด้วย quality ต่ำ
                hist["detailed_colors"] = detailed_colors
                hist["color_quality"]   = quality

            if color_groups is not None:
                hist["color_groups"] = color_groups
    
    def store_image_path(
        self,
        camera_id: str,
        our_id: int,
        path_type: str,
        path_value: str,
    ):
        """
        Store uploaded image path for track reuse.
        
        Args:
            camera_id: Camera identifier
            our_id: Track ID
            path_type: "image_path" or "bbox_image_path"
            path_value: URL/path to store
        """
        state = self._get_or_create_state(camera_id)
        
        with state.lock:
            if our_id not in state.track_history:
                state.track_history[our_id] = {}
            
            state.track_history[our_id][path_type] = path_value
            print(f"💾 [HybridTracker] Stored {path_type} for ID:{our_id}: {path_value}")
    
    def get_image_path(
        self,
        camera_id: str,
        our_id: int,
        path_type: str,
    ) -> Optional[str]:
        """Get stored image path for a track."""
        state = self._get_or_create_state(camera_id)
        
        with state.lock:
            if our_id in state.track_history:
                return state.track_history[our_id].get(path_type)
            return None
    
    def get_track_history(
        self,
        camera_id: str,
        our_id: int,
    ) -> Optional[Dict[str, Any]]:
        """Get full track history."""
        state = self._get_or_create_state(camera_id)
        
        with state.lock:
            return state.track_history.get(our_id)
    
    def cleanup(self, camera_id: str):
        """Clean up tracking state for a camera."""
        with self._global_lock:
            if camera_id in self._states:
                del self._states[camera_id]
                print(f"🧹 [HybridTracker] Cleaned up state for {camera_id}")
    
    def get_stats(self, camera_id: str) -> Dict[str, int]:
        """Get tracking statistics for a camera."""
        state = self._get_or_create_state(camera_id)
        
        with state.lock:
            return {
                "active_tracks": len(state.id_mapping),
                "lost_tracks": len(state.lost_tracks),
                "total_tracks": state.next_our_id - 1,
                "next_id": state.next_our_id,
            }


# Global singleton instance
_hybrid_tracker_instance: Optional[HybridTracker] = None
_hybrid_tracker_lock = threading.Lock()


def get_hybrid_tracker() -> HybridTracker:
    """Get global hybrid tracker instance."""
    global _hybrid_tracker_instance
    
    with _hybrid_tracker_lock:
        if _hybrid_tracker_instance is None:
            _hybrid_tracker_instance = HybridTracker()
        return _hybrid_tracker_instance


def cleanup_hybrid_tracker(camera_id: str):
    """Clean up hybrid tracker for a camera."""
    tracker = get_hybrid_tracker()
    tracker.cleanup(camera_id)
