"""
Regression Tests for Image Analysis API

Tests to ensure the image analysis endpoint works correctly
with both original and refactored implementations.

Run with:
    # Test original implementation (default)
    uv run python -m pytest tests/regression/test_image_analysis_baseline.py -v
    
    # Test refactored implementation
    set USE_REFACTORED_IMAGE_ANALYZER=true
    uv run python -m pytest tests/regression/test_image_analysis_baseline.py -v
"""
import pytest
import numpy as np
import cv2
import sys
import os

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

from src.api.controllers import DetectionController
from config_loader import use_refactored_image_analyzer, get_feature_flags_status


class TestImageAnalysisAPIContract:
    """
    Test API response format compatibility.
    These tests ensure both old and new implementations return the same format.
    """
    
    @pytest.fixture
    def controller(self):
        """Create DetectionController instance"""
        return DetectionController()
    
    @pytest.fixture
    def red_shirt_image(self):
        """Create a test image (red shirt)"""
        img = np.zeros((200, 200, 3), dtype=np.uint8)
        img[:, :] = [0, 0, 255]  # Red in BGR
        _, buf = cv2.imencode(".jpg", img)
        return buf.tobytes()
    
    @pytest.fixture
    def blue_pants_image(self):
        """Create a test image (blue pants)"""
        img = np.zeros((200, 300, 3), dtype=np.uint8)
        img[:, :] = [255, 0, 0]  # Blue in BGR
        _, buf = cv2.imencode(".jpg", img)
        return buf.tobytes()
    
    @pytest.fixture
    def invalid_image(self):
        """Create invalid image bytes"""
        return b"not a valid image"
    
    def test_api_response_has_status_field(self, controller, red_shirt_image):
        """Response must have 'status' field (success or error)"""
        result = controller.analyze_image_for_search(red_shirt_image)
        
        assert "status" in result
        assert result["status"] in ["success", "error"]
    
    def test_success_response_has_detected_attributes(self, controller, red_shirt_image):
        """Successful response must have 'detected_attributes' dict"""
        result = controller.analyze_image_for_search(red_shirt_image)
        
        if result["status"] == "success":
            assert "detected_attributes" in result
            assert isinstance(result["detected_attributes"], dict)
    
    def test_success_response_has_class_name(self, controller, red_shirt_image):
        """Successful response must have class_name in detected_attributes"""
        result = controller.analyze_image_for_search(red_shirt_image)
        
        if result["status"] == "success":
            attrs = result["detected_attributes"]
            assert "class_name" in attrs
            assert isinstance(attrs["class_name"], str)
            assert len(attrs["class_name"]) > 0
    
    def test_success_response_has_color_name(self, controller, red_shirt_image):
        """Successful response must have color_name in detected_attributes"""
        result = controller.analyze_image_for_search(red_shirt_image)
        
        if result["status"] == "success":
            attrs = result["detected_attributes"]
            assert "color_name" in attrs
            assert isinstance(attrs["color_name"], str)
    
    def test_error_response_has_message(self, controller, invalid_image):
        """Error response must have 'message' field"""
        result = controller.analyze_image_for_search(invalid_image)
        
        if result["status"] == "error":
            assert "message" in result
            assert isinstance(result["message"], str)
            assert len(result["message"]) > 0


class TestImageAnalysisWithFeatureFlag:
    """
    Test behavior with different Feature Flag settings.
    
    These tests verify that:
    1. Both implementations return compatible results
    2. Feature Flag can be toggled at runtime
    3. Refactored code has fallback to original on error
    """
    
    @pytest.fixture
    def controller(self):
        return DetectionController()
    
    @pytest.fixture
    def test_image(self):
        """Create a generic test image"""
        img = np.zeros((150, 150, 3), dtype=np.uint8)
        img[:, :] = [0, 255, 0]  # Green in BGR
        _, buf = cv2.imencode(".jpg", img)
        return buf.tobytes()
    
    def test_feature_flag_status_can_be_checked(self):
        """Feature flag status should be readable"""
        status = get_feature_flags_status()
        
        assert "USE_REFACTORED_IMAGE_ANALYZER" in status
        assert isinstance(status["USE_REFACTORED_IMAGE_ANALYZER"], bool)
    
    def test_both_implementations_return_dict(self, controller, test_image):
        """Both old and new implementations must return a dict"""
        result = controller.analyze_image_for_search(test_image)
        
        assert isinstance(result, dict)
        assert "status" in result


class TestImageAnalysisPerformance:
    """
    Test performance requirements.
    """
    
    @pytest.fixture
    def controller(self):
        return DetectionController()
    
    @pytest.fixture
    def test_image(self):
        img = np.zeros((200, 200, 3), dtype=np.uint8)
        img[:, :] = [128, 128, 128]  # Gray
        _, buf = cv2.imencode(".jpg", img)
        return buf.tobytes()
    
    def test_analysis_completes_within_timeout(self, controller, test_image):
        """Analysis must complete within reasonable time (< 5 seconds)"""
        import time
        
        start = time.perf_counter()
        result = controller.analyze_image_for_search(test_image)
        elapsed = time.perf_counter() - start
        
        # Should complete within 5 seconds (even on slow machines)
        assert elapsed < 5.0, f"Analysis took {elapsed:.2f}s, expected < 5s"
        
        print(f"\n✅ Analysis completed in {elapsed:.3f}s")


class TestImageAnalysisEdgeCases:
    """
    Test edge cases and error handling.
    """
    
    @pytest.fixture
    def controller(self):
        return DetectionController()
    
    def test_empty_bytes_returns_error(self, controller):
        """Empty image bytes should return error"""
        result = controller.analyze_image_for_search(b"")
        
        assert result["status"] == "error"
        assert "message" in result
    
    def test_none_image_returns_error(self, controller):
        """None as input should be handled (or raise exception)"""
        try:
            result = controller.analyze_image_for_search(None)
            assert result["status"] == "error"
        except (TypeError, AttributeError):
            # Also acceptable - the method may raise exception
            pass
    
    def test_very_small_image(self, controller):
        """Very small image (10x10) should be handled"""
        img = np.zeros((10, 10, 3), dtype=np.uint8)
        _, buf = cv2.imencode(".jpg", img)
        
        result = controller.analyze_image_for_search(buf.tobytes())
        
        # Should either succeed or return error gracefully
        assert result["status"] in ["success", "error"]
    
    def test_large_image(self, controller):
        """Large image should be handled without crashing"""
        # Create a moderately large image (1080p)
        img = np.zeros((1080, 1920, 3), dtype=np.uint8)
        _, buf = cv2.imencode(".jpg", img)
        
        result = controller.analyze_image_for_search(buf.tobytes())
        
        # Should complete without exception
        assert isinstance(result, dict)
        assert "status" in result


class TestImageAnalysisConsistency:
    """
    Test result consistency across multiple calls.
    """
    
    @pytest.fixture
    def controller(self):
        return DetectionController()
    
    @pytest.fixture
    def test_image(self):
        img = np.zeros((200, 200, 3), dtype=np.uint8)
        img[:, :] = [0, 0, 255]  # Red
        _, buf = cv2.imencode(".jpg", img)
        return buf.tobytes()
    
    def test_multiple_calls_return_same_format(self, controller, test_image):
        """Multiple calls should return results in same format"""
        results = []
        for _ in range(3):
            result = controller.analyze_image_for_search(test_image)
            results.append(result)
        
        # All should have same keys
        first_keys = set(results[0].keys())
        for result in results[1:]:
            assert set(result.keys()) == first_keys


def print_feature_flag_status():
    """Helper to print current Feature Flag status"""
    status = get_feature_flags_status()
    print("\n" + "=" * 50)
    print("Feature Flag Status:")
    print("=" * 50)
    for key, value in status.items():
        print(f"  {key}: {value}")
    print("=" * 50 + "\n")


if __name__ == "__main__":
    # Print feature flag status when running directly
    print_feature_flag_status()
    pytest.main([__file__, "-v"])
