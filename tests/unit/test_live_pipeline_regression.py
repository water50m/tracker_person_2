"""
Regression tests for LiveStreamPipeline output contract.
All tests mock FrameProcessor and HybridTracker — no real models needed.
"""
import asyncio
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch, AsyncMock
import numpy as np
import pytest

# Add src to path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))


# ── fixtures ──────────────────────────────────────────────────────────────────

def _make_fake_detection(track_id=1, x1=10, y1=10, x2=100, y2=200, conf=0.85,
                          class_name="Short_Sleeve_Shirt"):
    """Build a PersonDetection-like mock."""
    from services.ai_processing_types import PersonDetection, BoundingBox, DetectedItem

    bbox = BoundingBox.from_xyxy(x1, y1, x2, y2)
    item = DetectedItem(class_name=class_name, confidence=0.9)
    det = PersonDetection(track_id=track_id, bbox=bbox, confidence=conf, frame_number=1)
    det.items = [item]
    det.raw_items = [item]
    det.embedding = None
    return det


def _make_ai_result(detections):
    from services.ai_processing_types import AIProcessingResult, ProcessingStatus
    return AIProcessingResult(
        status=ProcessingStatus.SUCCESS,
        detections=detections,
        num_persons=len(detections),
        frame_number=1,
        image_width=640,
        image_height=480,
    )


def _blank_frame(h=480, w=640):
    return np.zeros((h, w, 3), dtype=np.uint8)


def _make_live_state(camera_id="CAM-01", detections=None):
    """
    Build a _LiveState with FrameProcessor and HybridTracker mocked.
    Returns (state, mock_fp, mock_tracker).
    """
    if detections is None:
        detections = [_make_fake_detection()]

    ai_result = _make_ai_result(detections)

    mock_fp = MagicMock()
    mock_fp.process_frame.return_value = ai_result

    mock_tracker = MagicMock()
    mock_tracker.match_or_create_track.return_value = (1, True, False)
    mock_tracker.update_lost_tracks.return_value = None
    mock_tracker.store_track_features.return_value = None

    with patch("src.services.live_pipeline._LiveState.__init__", return_value=None):
        from src.services.live_pipeline import _LiveState
        state = _LiveState.__new__(_LiveState)
        state.camera_id = camera_id
        state.frame_processor = mock_fp
        state.hybrid_tracker = mock_tracker

    return state, mock_fp, mock_tracker


# ── output dict contract ──────────────────────────────────────────────────────

REQUIRED_KEYS = {
    "id", "original_id", "bbox", "confidence", "color",
    "clothing", "raw_clothing", "result_clothing",
    "stable_clothing", "stable_label", "label", "reid_profile",
}

class TestOutputDictContract:

    def test_output_dict_keys(self):
        state, _, _ = _make_live_state()
        with patch("src.ai.color_system.analyze_detailed_colors", return_value={}), \
             patch("src.ai.color_system.get_color_groups", return_value={}):
            _, persons = state.process_frame(_blank_frame(), frame_count=1)
        assert len(persons) == 1
        missing = REQUIRED_KEYS - set(persons[0].keys())
        assert not missing, f"Missing keys: {missing}"

    def test_bbox_format(self):
        state, _, _ = _make_live_state()
        with patch("src.ai.color_system.analyze_detailed_colors", return_value={}), \
             patch("src.ai.color_system.get_color_groups", return_value={}):
            _, persons = state.process_frame(_blank_frame(), frame_count=1)
        bbox = persons[0]["bbox"]
        assert isinstance(bbox, list) and len(bbox) == 4
        x1, y1, x2, y2 = bbox
        assert x2 > x1
        assert y2 > y1

    def test_confidence_range(self):
        state, _, _ = _make_live_state()
        with patch("src.ai.color_system.analyze_detailed_colors", return_value={}), \
             patch("src.ai.color_system.get_color_groups", return_value={}):
            _, persons = state.process_frame(_blank_frame(), frame_count=1)
        conf = persons[0]["confidence"]
        assert 0.0 <= conf <= 1.0

    def test_id_is_positive_int(self):
        state, _, _ = _make_live_state()
        with patch("src.ai.color_system.analyze_detailed_colors", return_value={}), \
             patch("src.ai.color_system.get_color_groups", return_value={}):
            _, persons = state.process_frame(_blank_frame(), frame_count=1)
        assert isinstance(persons[0]["id"], int)
        assert persons[0]["id"] >= 1

    def test_stable_clothing_structure(self):
        state, _, _ = _make_live_state()
        with patch("src.ai.color_system.analyze_detailed_colors", return_value={}), \
             patch("src.ai.color_system.get_color_groups", return_value={}):
            _, persons = state.process_frame(_blank_frame(), frame_count=1)
        sc = persons[0]["stable_clothing"]
        assert isinstance(sc, dict)
        assert "label" in sc
        assert isinstance(sc["label"], str)
        assert "classes" in sc
        assert isinstance(sc["classes"], list)

    def test_color_is_rgb_list(self):
        state, _, _ = _make_live_state()
        with patch("src.ai.color_system.analyze_detailed_colors", return_value={}), \
             patch("src.ai.color_system.get_color_groups", return_value={}):
            _, persons = state.process_frame(_blank_frame(), frame_count=1)
        color = persons[0]["color"]
        assert isinstance(color, list) and len(color) == 3
        assert all(0 <= c <= 255 for c in color)


# ── annotated frame ───────────────────────────────────────────────────────────

class TestAnnotatedFrame:

    def test_annotated_frame_shape(self):
        frame = _blank_frame(480, 640)
        state, _, _ = _make_live_state()
        with patch("src.ai.color_system.analyze_detailed_colors", return_value={}), \
             patch("src.ai.color_system.get_color_groups", return_value={}):
            annotated, _ = state.process_frame(frame, frame_count=1)
        assert annotated.shape == frame.shape

    def test_annotated_frame_dtype(self):
        state, _, _ = _make_live_state()
        with patch("src.ai.color_system.analyze_detailed_colors", return_value={}), \
             patch("src.ai.color_system.get_color_groups", return_value={}):
            annotated, _ = state.process_frame(_blank_frame(), frame_count=1)
        assert annotated.dtype == np.uint8

    def test_empty_frame_returns_empty_persons(self):
        from services.ai_processing_types import AIProcessingResult, ProcessingStatus
        empty_result = AIProcessingResult(
            status=ProcessingStatus.NO_DETECTIONS,
            frame_number=1,
            image_width=640,
            image_height=480,
        )
        state, mock_fp, _ = _make_live_state(detections=[])
        mock_fp.process_frame.return_value = empty_result

        _, persons = state.process_frame(_blank_frame(), frame_count=1)
        assert persons == []


# ── callback behavior ─────────────────────────────────────────────────────────

class TestCallbackBehavior:

    def test_on_detection_callback_called(self):
        """on_detection should be called once per person per AI frame."""
        from src.services.live_pipeline import LiveStreamPipeline

        called_with = []

        async def _run():
            import cv2

            pipeline = LiveStreamPipeline(
                source="fake",
                camera_id="CAM-TEST",
                frame_skip=1,
                on_detection=lambda p, fc: called_with.append((p, fc)),
            )

            with patch("src.services.live_pipeline._LiveState") as MockState:
                mock_state = MagicMock()
                blank = _blank_frame()
                ok, jpeg = cv2.imencode(".jpg", blank)
                persons = [{"id": 1, "bbox": [10,10,100,200], "stable_label": "shirt",
                            "confidence": 0.9, "color": [255,0,0], "clothing": [],
                            "raw_clothing": [], "result_clothing": [],
                            "stable_clothing": {"label":"shirt","classes":[],"items":[]},
                            "label":"shirt","reid_profile":{},"original_id":1}]
                mock_state.process_frame.return_value = (blank, persons)
                mock_state.cleanup.return_value = None
                MockState.return_value = mock_state

                with patch("cv2.VideoCapture") as MockCap:
                    mock_cap = MagicMock()
                    mock_cap.isOpened.return_value = True
                    frame_calls = [0]

                    def _read():
                        frame_calls[0] += 1
                        if frame_calls[0] <= 2:
                            return True, blank
                        pipeline.stop_event.set()
                        return False, None

                    mock_cap.read.side_effect = _read
                    MockCap.return_value = mock_cap

                    await pipeline.run()

            return called_with

        result = asyncio.run(_run())
        assert len(result) >= 1
        assert result[0][0]["id"] == 1

    def test_stop_event_terminates_pipeline(self):
        """Setting stop_event should cause run() to return within 5s."""
        from src.services.live_pipeline import LiveStreamPipeline
        import cv2

        async def _run():
            pipeline = LiveStreamPipeline(source="fake", camera_id="CAM-STOP")

            with patch("src.services.live_pipeline._LiveState") as MockState:
                mock_state = MagicMock()
                mock_state.process_frame.return_value = (_blank_frame(), [])
                mock_state.cleanup.return_value = None
                MockState.return_value = mock_state

                with patch("cv2.VideoCapture") as MockCap:
                    mock_cap = MagicMock()
                    mock_cap.isOpened.return_value = True

                    def _read():
                        pipeline.stop_event.set()
                        return False, None

                    mock_cap.read.side_effect = _read
                    MockCap.return_value = mock_cap

                    await asyncio.wait_for(pipeline.run(), timeout=5.0)

        asyncio.run(_run())  # must not raise TimeoutError
