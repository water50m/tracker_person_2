"""
pytest fixtures for the test suite
"""
import pytest
import sys
import os
import numpy as np

# Add src to path for all tests
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))


@pytest.fixture(scope="session")
def test_image():
    """Fixture for a simple test image (red square)"""
    img = np.zeros((100, 100, 3), dtype=np.uint8)
    img[:, :] = [0, 0, 255]  # Red in BGR
    return img


@pytest.fixture(scope="session")
def test_image_blue():
    """Fixture for a blue test image"""
    img = np.zeros((100, 100, 3), dtype=np.uint8)
    img[:, :] = [255, 0, 0]  # Blue in BGR
    return img


@pytest.fixture(scope="session")
def sample_detailed_colors():
    """Sample detailed colors dict for testing"""
    return {
        "crimson_red": 35.5,
        "bright_red": 25.0,
        "dark_blue": 15.0,
        "navy_blue": 10.0,
        "pure_black": 14.5
    }


@pytest.fixture(scope="session")
def sample_color_groups():
    """Sample color groups dict for testing"""
    return {
        "red": 60.5,
        "blue": 25.0,
        "neutral": 14.5
    }


@pytest.fixture(scope="session")
def sample_embedding():
    """Sample 768-dim embedding vector for testing"""
    np.random.seed(42)
    return np.random.randn(768).tolist()
