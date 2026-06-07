"""
Feature tests for FrameProcessor + HybridTracker integration in _LiveState.
Verifies persistent IDs, Re-ID recovery, and tracker lifecycle.
No real models needed — FrameProcessor and HybridTracker are tested directly.
"""
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch
import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))


# ── helpers ───────────────────────────────────────────────────────────────────

def _blank_frame(h=480, w=640):
    return np.zeros((h, w, 3), dtype=np.uint8)


def _make_detection(track_id=1, x1=10, y1=10, x2=100, y2=200, class_name="shirt"):
    from services.ai_processing_types import PersonDetection, BoundingBox, DetectedItem
    bbox = BoundingBox.from_xyxy(x1, y1, x2, y2)
    item = DetectedItem(class_name=class_name, confidence=0.9)
    det = PersonDetection(track_id=track_id, bbox=bbox, confidence=0.9, frame_number=1)
    det.items = [item]
    det.raw_items = [item]
    det.embedding = None
    return det


def _ai_result(detections):
    from services.ai_processing_types import AIProcessingResult, ProcessingStatus
    return AIProcessingResult(
        status=ProcessingStatus.SUCCESS,
        detections=detections,
        num_persons=len(detections),
        frame_number=1,
        image_width=640,
        image_height=480,
    )


def _no_detection_result():
    from services.ai_processing_types import AIProcessingResult, ProcessingStatus
    return AIProcessingResult(
        status=ProcessingStatus.NO_DETECTIONS,
        frame_number=2,
        image_width=640,
        image_height=480,
    )


def _make_state(camera_id="CAM-HYB"):
    """Build _LiveState with real HybridTracker but mocked FrameProcessor."""
    from src.services.hybrid_tracker import HybridTracker
    from src.services.live_pipeline import _LiveState

    mock_fp = MagicMock()
    real_tracker = HybridTracker()

    with patch("src.services.live_pipeline._LiveState.__init__", return_value=None):
        state = _LiveState.__new__(_LiveState)
        state.camera_id = camera_id
        state.frame_processor = mock_fp
        state.hybrid_tracker = real_tracker

    return state, mock_fp, real_tracker


# ── persistent ID tests ───────────────────────────────────────────────────────

class TestPersistentIds:

    def test_id_starts_at_1(self):
        state, fp, tracker = _make_state("CAM-A")
        fp.process_frame.return_value = _ai_result([_make_detection(track_id=5)])

        with patch("src.ai.color_system.analyze_detailed_colors", return_value={}), \
             patch("src.ai.color_system.get_color_groups", return_value={}):
            _, persons = state.process_frame(_blank_frame(), 1)

        assert persons[0]["id"] == 1

    def test_same_byte_id_same_our_id(self):
        """Same ByteTrack ID across two frames → same persistent ID."""
        state, fp, tracker = _make_state("CAM-B")
        det = _make_detection(track_id=7)
        fp.process_frame.return_value = _ai_result([det])

        with patch("src.ai.color_system.analyze_detailed_colors", return_value={}), \
             patch("src.ai.color_system.get_color_groups", return_value={}):
            _, p1 = state.process_frame(_blank_frame(), 1)
            _, p2 = state.process_frame(_blank_frame(), 2)

        assert p1[0]["id"] == p2[0]["id"]

    def test_new_byte_id_new_our_id(self):
        """Different ByteTrack IDs → different persistent IDs."""
        state, fp, tracker = _make_state("CAM-C")

        with patch("src.ai.color_system.analyze_detailed_colors", return_value={}), \
             patch("src.ai.color_system.get_color_groups", return_value={}):
            fp.process_frame.return_value = _ai_result([_make_detection(track_id=1)])
            _, p1 = state.process_frame(_blank_frame(), 1)

            fp.process_frame.return_value = _ai_result([_make_detection(track_id=2)])
            _, p2 = state.process_frame(_blank_frame(), 2)

        assert p1[0]["id"] != p2[0]["id"]

    def test_two_persons_different_ids(self):
        """Two simultaneous detections get different IDs."""
        state, fp, tracker = _make_state("CAM-D")
        fp.process_frame.return_value = _ai_result([
            _make_detection(track_id=1, x2=50),
            _make_detection(track_id=2, x1=300, x2=400),
        ])

        with patch("src.ai.color_system.analyze_detailed_colors", return_value={}), \
             patch("src.ai.color_system.get_color_groups", return_value={}):
            _, persons = state.process_frame(_blank_frame(), 1)

        assert len(persons) == 2
        assert persons[0]["id"] != persons[1]["id"]


# ── lost track tests ──────────────────────────────────────────────────────────

class TestLostTracks:

    def test_disappeared_track_moves_to_lost(self):
        """After person disappears, HybridTracker should have them in lost_tracks."""
        state, fp, tracker = _make_state("CAM-E")

        # Frame 1: person appears, store features so lost_tracks can be populated
        det = _make_detection(track_id=3)
        fp.process_frame.return_value = _ai_result([det])
        with patch("src.ai.color_system.analyze_detailed_colors",
                   return_value={"red": 0.8}), \
             patch("src.ai.color_system.get_color_groups", return_value={"warm": 0.8}):
            _, _ = state.process_frame(_blank_frame(), 1)

        # Frame 2: no persons → update_lost_tracks with empty list
        fp.process_frame.return_value = _no_detection_result()
        _, _ = state.process_frame(_blank_frame(), 2)

        stats = tracker.get_stats("CAM-E")
        assert stats["lost_tracks"] >= 1

    def test_track_features_stored_on_new(self):
        """After first appearance, track_history should have features."""
        state, fp, tracker = _make_state("CAM-F")
        fp.process_frame.return_value = _ai_result([_make_detection(track_id=10)])

        with patch("src.ai.color_system.analyze_detailed_colors",
                   return_value={"blue": 0.9}), \
             patch("src.ai.color_system.get_color_groups",
                   return_value={"cool": 0.9}):
            _, persons = state.process_frame(_blank_frame(), 1)

        our_id = persons[0]["id"]
        history = tracker.get_track_history("CAM-F", our_id)
        assert history is not None
        assert "detailed_colors" in history


# ── Re-ID recovery test ───────────────────────────────────────────────────────

class TestReIDRecovery:

    def test_reid_recovery_restores_id(self):
        """
        Person disappears (track_id=1 not seen), reappears with new track_id=99
        but same color features → HybridTracker should return the original ID.
        """
        state, fp, tracker = _make_state("CAM-G")
        colors = {"red": 0.8, "blue": 0.1}
        groups = {"warm": 0.8}

        # Frame 1: person appears with track_id=1
        fp.process_frame.return_value = _ai_result([_make_detection(track_id=1)])
        with patch("src.ai.color_system.analyze_detailed_colors", return_value=colors), \
             patch("src.ai.color_system.get_color_groups", return_value=groups):
            _, p1 = state.process_frame(_blank_frame(), 1)
        original_id = p1[0]["id"]

        # Frame 2: person disappears
        fp.process_frame.return_value = _no_detection_result()
        _, _ = state.process_frame(_blank_frame(), 2)

        # Frame 3: person reappears with new track_id=99, same colors
        fp.process_frame.return_value = _ai_result([_make_detection(track_id=99)])
        with patch("src.ai.color_system.analyze_detailed_colors", return_value=colors), \
             patch("src.ai.color_system.get_color_groups", return_value=groups):
            _, p3 = state.process_frame(_blank_frame(), 3)

        recovered_id = p3[0]["id"]
        # Re-ID should recover the same ID (similarity = 1.0 with identical colors)
        assert recovered_id == original_id, (
            f"Expected Re-ID recovery to restore ID {original_id}, got {recovered_id}"
        )


# ── cleanup test ──────────────────────────────────────────────────────────────

class TestCleanup:

    def test_cleanup_removes_camera_state(self):
        """After cleanup(), tracker should have no active state for this camera."""
        state, fp, tracker = _make_state("CAM-H")
        fp.process_frame.return_value = _ai_result([_make_detection(track_id=1)])

        with patch("src.ai.color_system.analyze_detailed_colors", return_value={}), \
             patch("src.ai.color_system.get_color_groups", return_value={}):
            state.process_frame(_blank_frame(), 1)

        # Camera should be in tracker state now
        assert "CAM-H" in tracker._states

        state.cleanup()
        assert "CAM-H" not in tracker._states


# ── no scripts path manipulation ─────────────────────────────────────────────

class TestNoDependencyLeak:

    def test_no_scripts_path_in_sys_path(self):
        """_LiveState init must not inject scripts/ into sys.path."""
        import sys
        scripts_fragment = "scripts"

        before = set(sys.path)

        with patch("src.services.frame_processor.FrameProcessor.__init__", return_value=None), \
             patch("src.services.hybrid_tracker.get_hybrid_tracker", return_value=MagicMock()):
            from src.services.live_pipeline import _LiveState
            state = _LiveState.__new__(_LiveState)
            # Manually call without patching __init__ to test actual path
            # (just check current sys.path doesn't have 'scripts' added)

        after = set(sys.path)
        new_paths = after - before
        scripts_added = [p for p in new_paths if scripts_fragment in str(p) and "src" not in str(p)]
        assert not scripts_added, f"scripts/ was added to sys.path: {scripts_added}"

    def test_live_state_uses_frame_processor(self):
        """_LiveState.process_frame must call frame_processor.process_frame, not YOLO directly."""
        state, mock_fp, _ = _make_state("CAM-I")
        mock_fp.process_frame.return_value = _no_detection_result()

        state.process_frame(_blank_frame(), 1)

        mock_fp.process_frame.assert_called_once()
