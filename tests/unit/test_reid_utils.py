"""
Unit Tests for Re-ID Utilities
Testing similarity calculations, lost track matching, and embeddings
"""
import unittest
import sys
import os
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

from ai.reid_utils import (
    compare_color_distributions, compare_clothes_lists,
    calculate_similarity, match_lost_track, update_lost_tracks,
    compare_embeddings
)


class TestSimilarityCalculation(unittest.TestCase):
    """ทดสอบฟังก์ชันคำนวณความคล้ายคลึงกัน"""
    
    def test_compare_color_distributions_identical(self):
        """ทดสอบการเปรียบเทียบสีที่เหมือนกันทั้งหมด"""
        colors1 = {"red": 50.0, "blue": 30.0, "black": 20.0}
        colors2 = {"red": 50.0, "blue": 30.0, "black": 20.0}
        similarity = compare_color_distributions(colors1, colors2)
        self.assertAlmostEqual(similarity, 1.0, places=2)
        print(f"✅ Identical colors: similarity = {similarity}")
    
    def test_compare_color_distributions_different(self):
        """ทดสอบการเปรียบเทียบสีที่ต่างกัน"""
        colors1 = {"red": 100.0}
        colors2 = {"blue": 100.0}
        similarity = compare_color_distributions(colors1, colors2)
        self.assertLess(similarity, 0.5)
        print(f"✅ Different colors: similarity = {similarity}")
    
    def test_compare_color_distributions_empty(self):
        """ทดสอบการเปรียบเทียบสีที่ว่าง"""
        similarity = compare_color_distributions({}, {})
        self.assertEqual(similarity, 0.0)
        print(f"✅ Empty colors: similarity = {similarity}")
    
    def test_compare_clothes_lists_identical(self):
        """ทดสอบการเปรียบเทียบเสื้อผ้าที่เหมือนกันทั้งหมด"""
        clothes1 = ["t-shirt", "jeans", "shoes"]
        clothes2 = ["t-shirt", "jeans", "shoes"]
        similarity = compare_clothes_lists(clothes1, clothes2)
        self.assertEqual(similarity, 1.0)
        print(f"✅ Identical clothes: similarity = {similarity}")
    
    def test_compare_clothes_lists_partial(self):
        """ทดสอบการเปรียบเทียบเสื้อผ้าที่บางส่วนเหมือน"""
        clothes1 = ["t-shirt", "jeans", "shoes"]
        clothes2 = ["t-shirt", "jeans"]
        similarity = compare_clothes_lists(clothes1, clothes2)
        self.assertGreater(similarity, 0.5)
        self.assertLess(similarity, 1.0)
        print(f"✅ Partial clothes match: similarity = {similarity}")
    
    def test_compare_clothes_lists_different(self):
        """ทดสอบการเปรียบเทียบเสื้อผ้าที่ต่างกัน"""
        clothes1 = ["t-shirt", "jeans"]
        clothes2 = ["dress", "skirt"]
        similarity = compare_clothes_lists(clothes1, clothes2)
        self.assertEqual(similarity, 0.0)
        print(f"✅ Different clothes: similarity = {similarity}")
    
    def test_compare_clothes_lists_empty(self):
        """ทดสอบการเปรียบเทียบเสื้อผ้าที่ว่าง"""
        similarity = compare_clothes_lists([], [])
        self.assertEqual(similarity, 1.0)
        print(f"✅ Empty clothes: similarity = {similarity}")
    
    def test_calculate_similarity(self):
        """ทดสอบการคำนวณ similarity แบบรวม"""
        features1 = {
            "detailed_colors": {"red": 50.0, "blue": 30.0, "black": 20.0},
            "clothes": ["t-shirt", "jeans"],
            "embedding": None
        }
        features2 = {
            "detailed_colors": {"red": 50.0, "blue": 30.0, "black": 20.0},
            "clothes": ["t-shirt", "jeans"],
            "embedding": None
        }
        similarity = calculate_similarity(features1, features2)
        self.assertGreater(similarity, 0.8)
        print(f"✅ Combined similarity: {similarity}")

    def test_compare_embeddings_identical(self):
        """ทดสอบการเปรียบเทียบ embeddings ที่เหมือนกัน"""
        embedding1 = np.ones(768) / np.sqrt(768)
        embedding2 = np.ones(768) / np.sqrt(768)
        similarity = compare_embeddings(embedding1, embedding2)
        self.assertAlmostEqual(similarity, 1.0, places=2)
        print(f"✅ Identical embeddings: similarity = {similarity}")

    def test_compare_embeddings_different(self):
        """ทดสอบการเปรียบเทียบ embeddings ที่ต่างกัน"""
        embedding1 = np.ones(768)
        embedding1[:384] = 0
        embedding1 = embedding1 / np.linalg.norm(embedding1)
        embedding2 = np.zeros(768)
        embedding2[384:] = 1
        embedding2 = embedding2 / np.linalg.norm(embedding2)
        similarity = compare_embeddings(embedding1, embedding2)
        self.assertLess(similarity, 0.1)
        print(f"✅ Different embeddings: similarity = {similarity}")

    def test_compare_embeddings_none(self):
        """ทดสอบการเปรียบเทียบ embeddings ที่เป็น None"""
        similarity = compare_embeddings(None, None)
        self.assertEqual(similarity, 0.0)
        print(f"✅ None embeddings: similarity = {similarity}")


class TestLostTrackMatching(unittest.TestCase):
    """ทดสอบฟังก์ชันจัดการ lost tracks"""
    
    def test_match_lost_track_perfect_match(self):
        """ทดสอบการ match lost track ที่สมบูรณ์"""
        new_features = {
            "detailed_colors": {"red": 50.0, "blue": 30.0, "black": 20.0},
            "clothes": ["t-shirt", "jeans"],
            "embedding": None
        }
        lost_tracks = {
            1: {
                "features": {
                    "detailed_colors": {"red": 50.0, "blue": 30.0, "black": 20.0},
                    "clothes": ["t-shirt", "jeans"],
                    "embedding": None
                },
                "last_seen": 10
            }
        }
        matched_id = match_lost_track(new_features, lost_tracks, threshold=0.7)
        self.assertEqual(matched_id, 1)
        print(f"✅ Perfect match: track_id = {matched_id}")
    
    def test_match_lost_track_no_match(self):
        """ทดสอบการ match lost track ที่ไม่มี"""
        new_features = {
            "detailed_colors": {"red": 100.0},
            "clothes": ["dress"],
            "embedding": None
        }
        lost_tracks = {
            1: {
                "features": {
                    "detailed_colors": {"blue": 100.0},
                    "clothes": ["t-shirt"],
                    "embedding": None
                },
                "last_seen": 10
            }
        }
        matched_id = match_lost_track(new_features, lost_tracks, threshold=0.7)
        self.assertIsNone(matched_id)
        print(f"✅ No match: track_id = {matched_id}")
    
    def test_match_lost_track_below_threshold(self):
        """ทดสอบการ match lost track ที่ similarity ต่ำกว่า threshold"""
        new_features = {
            "detailed_colors": {"red": 60.0, "blue": 40.0},
            "clothes": ["t-shirt"],
            "embedding": None
        }
        lost_tracks = {
            1: {
                "features": {
                    "detailed_colors": {"red": 50.0, "green": 50.0},
                    "clothes": ["t-shirt"],
                    "embedding": None
                },
                "last_seen": 10
            }
        }
        matched_id = match_lost_track(new_features, lost_tracks, threshold=0.9)
        self.assertIsNone(matched_id)
        print(f"✅ Below threshold: track_id = {matched_id}")
    
    def test_match_lost_track_empty(self):
        """ทดสอบการ match lost track เมื่อ lost_tracks ว่าง"""
        new_features = {
            "detailed_colors": {"red": 50.0},
            "clothes": ["t-shirt"],
            "embedding": None
        }
        lost_tracks = {}
        matched_id = match_lost_track(new_features, lost_tracks, threshold=0.7)
        self.assertIsNone(matched_id)
        print(f"✅ Empty lost_tracks: track_id = {matched_id}")
    
    def test_update_lost_tracks_add(self):
        """ทดสอบการเพิ่ม track ใหม่เมื่อหายไป"""
        lost_tracks = {}
        track_history = {
            1: {"clothes": ["t-shirt"], "detailed_colors": {"red": 50.0}}
        }
        current_ids = []  # ID 1 is not present
        update_lost_tracks(lost_tracks, track_history, current_ids, frame_count=10, timeout=60)
        self.assertIn(1, lost_tracks)
        self.assertEqual(lost_tracks[1]["last_seen"], 10)
        print(f"✅ Added to lost_tracks: {list(lost_tracks.keys())}")
    
    def test_update_lost_tracks_remove(self):
        """ทดสอบการลบ track เมื่อกลับมาปรากฏ"""
        lost_tracks = {
            1: {
                "features": {"clothes": ["t-shirt"]},
                "last_seen": 10
            }
        }
        track_history = {
            1: {"clothes": ["t-shirt"], "detailed_colors": {"red": 50.0}}
        }
        current_ids = [1]  # ID 1 is back
        update_lost_tracks(lost_tracks, track_history, current_ids, frame_count=20, timeout=60)
        self.assertNotIn(1, lost_tracks)
        print(f"✅ Removed from lost_tracks: {list(lost_tracks.keys())}")
    
    def test_update_lost_tracks_timeout(self):
        """ทดสอบการลบ track เมื่อหายไปนานเกิน timeout"""
        lost_tracks = {
            1: {
                "features": {"clothes": ["t-shirt"]},
                "last_seen": 10
            }
        }
        track_history = {
            1: {"clothes": ["t-shirt"], "detailed_colors": {"red": 50.0}}
        }
        current_ids = []  # ID 1 still not present
        # Timeout = 5 frames, current frame = 20, last seen = 10, diff = 10 > 5
        update_lost_tracks(lost_tracks, track_history, current_ids, frame_count=20, timeout=5)
        self.assertNotIn(1, lost_tracks)
        print(f"✅ Timeout cleanup: {list(lost_tracks.keys())}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
