"""
Re-Identification Utilities for Hybrid Tracking
ฟังก์ชันคำนวณความคล้ายคลึงกันและจัดการ lost tracks
"""
import numpy as np
from collections import Counter


def compare_color_distributions(colors1, colors2):
    """
    เปรียบเทียบ detailed colors ระหว่าง 2 distributions ใช้ cosine similarity
    
    Args:
        colors1: dict ของ detailed colors {color_name: percentage}
        colors2: dict ของ detailed colors {color_name: percentage}
    
    Returns:
        float: similarity score ระหว่าง 0-1 (1 = เหมือนกันทั้งหมด)
    """
    if not colors1 or not colors2:
        return 0.0
    
    # รวบรวมทุก color names ที่มี
    all_colors = set(colors1.keys()) | set(colors2.keys())
    
    if not all_colors:
        return 0.0
    
    # สร้าง vectors
    vec1 = np.array([colors1.get(c, 0.0) for c in all_colors])
    vec2 = np.array([colors2.get(c, 0.0) for c in all_colors])
    
    # คำนวณ cosine similarity
    norm1 = np.linalg.norm(vec1)
    norm2 = np.linalg.norm(vec2)
    
    if norm1 == 0 or norm2 == 0:
        return 0.0
    
    similarity = np.dot(vec1, vec2) / (norm1 * norm2)
    return float(similarity)


def compare_clothes_lists(clothes1, clothes2):
    """
    เปรียบเทียบ clothes ระหว่าง 2 lists ใช้ Jaccard similarity
    
    Args:
        clothes1: list ของ clothes names
        clothes2: list ของ clothes names
    
    Returns:
        float: similarity score ระหว่าง 0-1 (1 = เหมือนกันทั้งหมด)
    """
    if not clothes1 and not clothes2:
        return 1.0
    
    if not clothes1 or not clothes2:
        return 0.0
    
    set1 = set(clothes1)
    set2 = set(clothes2)
    
    # Jaccard similarity = |A ∩ B| / |A ∪ B|
    intersection = len(set1 & set2)
    union = len(set1 | set2)
    
    if union == 0:
        return 0.0
    
    return intersection / union


def compare_embeddings(embedding1, embedding2):
    """
    คำนวณ cosine similarity ระหว่าง 768-dim embeddings
    
    Args:
        embedding1: numpy array ของ embedding (768-dim)
        embedding2: numpy array ของ embedding (768-dim)
    
    Returns:
        float: similarity score ระหว่าง 0-1 (1 = เหมือนกันทั้งหมด)
    """
    if embedding1 is None or embedding2 is None:
        return 0.0
    
    # Convert to numpy arrays if not already
    if not isinstance(embedding1, np.ndarray):
        embedding1 = np.array(embedding1)
    if not isinstance(embedding2, np.ndarray):
        embedding2 = np.array(embedding2)
    
    # Check dimensions match
    if len(embedding1) != len(embedding2):
        return 0.0
    
    # Calculate cosine similarity
    norm1 = np.linalg.norm(embedding1)
    norm2 = np.linalg.norm(embedding2)
    
    if norm1 == 0 or norm2 == 0:
        return 0.0
    
    similarity = np.dot(embedding1, embedding2) / (norm1 * norm2)
    return float(similarity)


def calculate_similarity(features1, features2, embedding_weight=0.5, color_weight=0.3, clothes_weight=0.2):
    """
    คำนวณความคล้ายคลึงกันระหว่าง 2 sets ของ features
    
    Args:
        features1: dict ของ features {detailed_colors, clothes, embedding, ...}
        features2: dict ของ features {detailed_colors, clothes, embedding, ...}
        embedding_weight: น้ำหนักสำหรับ embedding (default: 0.5)
        color_weight: น้ำหนักสำหรับสี (default: 0.3)
        clothes_weight: น้ำหนักสำหรับเสื้อผ้า (default: 0.2)
    
    Returns:
        float: similarity score ระหว่าง 0-1
    """
    # เปรียบเทียบ embeddings (768-dim)
    embedding_score = compare_embeddings(
        features1.get("embedding"),
        features2.get("embedding")
    )
    
    # เปรียบเทียบ detailed colors
    color_score = compare_color_distributions(
        features1.get("detailed_colors", {}),
        features2.get("detailed_colors", {})
    )
    
    # เปรียบเทียบ clothes
    clothes_score = compare_clothes_lists(
        features1.get("clothes", []),
        features2.get("clothes", [])
    )
    
    # Weighted sum (embedding 50%, color 30%, clothes 20%)
    similarity = (embedding_weight * embedding_score + 
                  color_weight * color_score + 
                  clothes_weight * clothes_score)
    return float(similarity)


def match_lost_track(new_features, lost_tracks, threshold=0.7):
    """
    ค้นหา lost track ที่ match กับ features ใหม่
    
    Args:
        new_features: dict ของ features ของ detection ใหม่
        lost_tracks: dict ของ lost tracks {track_id: {features, last_seen}}
        threshold: ค่า threshold สำหรับ matching (default: 0.7)
    
    Returns:
        int or None: track_id ที่ match หรือ None ถ้าไม่มี
    """
    if not lost_tracks:
        return None
    
    best_match = None
    best_score = 0.0
    
    for track_id, track_data in lost_tracks.items():
        stored_features = track_data.get("features", {})
        similarity = calculate_similarity(new_features, stored_features)
        
        if similarity > best_score and similarity >= threshold:
            best_match = track_id
            best_score = similarity
    
    return best_match


def update_lost_tracks(lost_tracks, track_history, current_ids, frame_count, timeout=60):
    """
    อัปเดตรายการ lost tracks
    
    Args:
        lost_tracks: dict ของ lost tracks {track_id: {features, last_seen}}
        track_history: dict ของ track history
        current_ids: list ของ track_ids ที่ปรากฏใน frame ปัจจุบัน
        frame_count: frame number ปัจจุบัน
        timeout: timeout ใน frames (default: 60)
    """
    # เพิ่ม tracks ที่หายไปใหม่
    for track_id, features in track_history.items():
        if track_id not in current_ids and track_id not in lost_tracks:
            lost_tracks[track_id] = {
                "features": features.copy(),
                "last_seen": features.get("last_seen", frame_count)
            }
    
    # อัปเดต last_seen สำหรับ tracks ที่ยังอยู่
    for track_id in current_ids:
        if track_id in lost_tracks:
            del lost_tracks[track_id]
    
    # ลบ tracks ที่หายไปนานเกิน timeout
    to_delete = []
    for track_id, track_data in lost_tracks.items():
        if frame_count - track_data["last_seen"] > timeout:
            to_delete.append(track_id)
    
    for track_id in to_delete:
        del lost_tracks[track_id]
