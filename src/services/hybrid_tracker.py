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


@dataclass
class TrackFeatures:
    """Features for a tracked person."""
    detailed_colors: Dict[str, float] = field(default_factory=dict)
    color_groups: Dict[str, float] = field(default_factory=dict)
    embedding: Optional[List[float]] = None
    clothes: List[str] = field(default_factory=list)
    last_seen: float = field(default_factory=time.time)
    frame_number: int = 0


@dataclass
class HybridTrackState:
    """State for hybrid tracking per camera."""
    id_mapping: Dict[int, int] = field(default_factory=dict)  # {byte_id: our_id}
    lost_tracks: Dict[int, TrackFeatures] = field(default_factory=dict)  # {our_id: features}
    next_our_id: int = 1
    track_history: Dict[int, Dict[str, Any]] = field(default_factory=dict)  # {our_id: metadata}
    lock: threading.Lock = field(default_factory=threading.Lock)


class HybridTracker:
    """
    Hybrid tracking manager combining ByteTrack with Re-ID.
    
    This class provides persistent person IDs across frames by:
    1. Mapping ByteTrack IDs to our persistent IDs
    2. Recovering lost tracks using Re-ID similarity
    3. Storing track metadata for image path reuse
    
    Thread-safe for use across multiple cameras.
    """
    
    def __init__(self, recovery_threshold: float = 0.7):
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
    
    def match_or_create_track(
        self,
        camera_id: str,
        byte_id: Optional[int],
        person_crop: Optional[np.ndarray] = None,
        embedder = None,
        detailed_colors: Optional[Dict[str, float]] = None,
        color_groups: Optional[Dict[str, float]] = None,
    ) -> Tuple[int, bool, bool]:
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
            Tuple of (our_id, is_new_track, is_recovered_track)
        """
        state = self._get_or_create_state(camera_id)
        
        with state.lock:
            if byte_id is None:
                # No tracking ID, create new
                our_id = state.next_our_id
                state.next_our_id += 1
                return our_id, True, False
            
            if byte_id in state.id_mapping:
                # Known track
                return state.id_mapping[byte_id], False, False
            
            # New ByteTrack ID - try to recover from lost tracks
            if person_crop is not None and person_crop.size > 0 and embedder is not None:
                try:
                    # Extract features
                    embedding, clothes = embedder.get_embedding(person_crop)
                    
                    if detailed_colors is None or color_groups is None:
                        # Compute color features
                        from src.ai.color_system import analyze_detailed_colors, get_color_groups
                        detailed_colors = analyze_detailed_colors(person_crop)
                        color_groups = get_color_groups(detailed_colors)
                    
                    new_features = TrackFeatures(
                        detailed_colors=detailed_colors,
                        color_groups=color_groups,
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
                        return recovered_id, False, True
                    
                    # New track
                    our_id = state.next_our_id
                    state.id_mapping[byte_id] = our_id
                    state.next_our_id += 1
                    print(f"🆕 [HybridTracker] New track: {our_id} (byte_id: {byte_id})")
                    return our_id, True, False
                    
                except Exception as e:
                    print(f"⚠️ [HybridTracker] Re-ID matching error: {e}")
                    # Fallback: create new track
                    our_id = state.next_our_id
                    state.id_mapping[byte_id] = our_id
                    state.next_our_id += 1
                    return our_id, True, False
            else:
                # No embedder or empty crop: create new track
                our_id = state.next_our_id
                state.id_mapping[byte_id] = our_id
                state.next_our_id += 1
                return our_id, True, False
    
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
        Calculate similarity between two feature sets.
        
        Returns:
            Similarity score (0-1, higher is more similar)
        """
        scores = []
        
        # Embedding similarity (cosine)
        if features1.embedding and features2.embedding:
            try:
                emb1 = np.array(features1.embedding)
                emb2 = np.array(features2.embedding)
                
                # Cosine similarity
                dot_product = np.dot(emb1, emb2)
                norm1 = np.linalg.norm(emb1)
                norm2 = np.linalg.norm(emb2)
                
                if norm1 > 0 and norm2 > 0:
                    emb_sim = dot_product / (norm1 * norm2)
                    scores.append(emb_sim)
            except Exception:
                pass
        
        # Color similarity (IoU of color groups)
        if features1.color_groups and features2.color_groups:
            try:
                set1 = set(features1.color_groups.keys())
                set2 = set(features2.color_groups.keys())
                
                if set1 and set2:
                    intersection = len(set1 & set2)
                    union = len(set1 | set2)
                    color_sim = intersection / union if union > 0 else 0.0
                    scores.append(color_sim)
            except Exception:
                pass
        
        # Average scores
        if scores:
            return sum(scores) / len(scores)
        
        return 0.0
    
    def update_lost_tracks(self, camera_id: str, current_ids: List[int], max_age: int = 30):
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
            
            # Find tracks that are no longer active
            active_ids = set(current_ids)
            
            # Move inactive tracks to lost_tracks
            for byte_id, our_id in list(state.id_mapping.items()):
                if our_id not in active_ids:
                    # Track is lost, store features if available
                    if our_id in state.track_history:
                        history = state.track_history[our_id]
                        lost_features = TrackFeatures(
                            detailed_colors=history.get("detailed_colors", {}),
                            color_groups=history.get("color_groups", {}),
                            embedding=history.get("embedding"),
                            clothes=history.get("clothes", []),
                            last_seen=current_time,
                        )
                        state.lost_tracks[our_id] = lost_features
                        print(f"💨 [HybridTracker] Track {our_id} marked as lost")
    
    def store_track_features(
        self,
        camera_id: str,
        our_id: int,
        detailed_colors: Optional[Dict[str, float]] = None,
        color_groups: Optional[Dict[str, float]] = None,
        embedding: Optional[List[float]] = None,
        clothes: Optional[List[str]] = None,
    ):
        """Store features for a track."""
        state = self._get_or_create_state(camera_id)
        
        with state.lock:
            if our_id not in state.track_history:
                state.track_history[our_id] = {}
            
            if detailed_colors is not None:
                state.track_history[our_id]["detailed_colors"] = detailed_colors
            if color_groups is not None:
                state.track_history[our_id]["color_groups"] = color_groups
            if embedding is not None:
                state.track_history[our_id]["embedding"] = embedding
            if clothes is not None:
                state.track_history[our_id]["clothes"] = clothes
    
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
