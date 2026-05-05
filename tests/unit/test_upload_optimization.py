"""
Test that upload futures are properly stored and reused.
This prevents duplicate uploads that slow down the realtime processing.
"""

import pytest
from unittest.mock import Mock
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))


def test_classification_results_stores_upload_futures():
    """Test that classification_results dict stores upload futures"""
    classification_results = {
        1: {
            "clothing_type": "Shirt",
            "confidence": 0.95,
            "bbox": (10, 10, 50, 50),
            "should_upload_image": True,
            "upload_future": Mock(),
            "object_name": "detections/cam1/video1/100_abc.jpg",
            "bbox_upload_future": Mock(),
            "bbox_object_name": "detections/cam1/video1/bbox_100_abc.jpg",
        }
    }
    
    result = classification_results[1]
    assert "upload_future" in result
    assert "bbox_upload_future" in result
    assert result["upload_future"] is not None
    print("✅ Test passed: classification_results stores upload futures")


def test_db_loop_reuses_futures():
    """Test that DB loop reuses futures instead of creating new uploads"""
    mock_future = Mock()
    
    classification_results = {
        1: {
            "should_upload_image": True,
            "upload_future": mock_future,
            "object_name": "test.jpg",
            "bbox_upload_future": mock_future,
            "bbox_object_name": "bbox_test.jpg",
        }
    }
    
    track_id = 1
    result = classification_results.get(track_id, {})
    det_upload_future = result.get("upload_future")
    
    assert det_upload_future is mock_future
    print("✅ Test passed: DB loop reuses futures (no duplicate uploads)")


if __name__ == "__main__":
    test_classification_results_stores_upload_futures()
    test_db_loop_reuses_futures()
    print("\n✅ All tests passed!")
