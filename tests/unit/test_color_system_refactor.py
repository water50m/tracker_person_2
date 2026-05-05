"""
Unit tests for color system refactor - tone group calculation from detailed colors
Tests the new 10-tone system and ambiguous color handling

Note: These tests require the full Python environment with ultralytics installed.
Run with: python -m pytest tests/unit/test_color_system_refactor.py -v
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

try:
    from src.ai.color_system import calculate_tone_groups_from_detailed, COLOR_TO_TONE_GROUPS
    IMPORTS_AVAILABLE = True
except ImportError as e:
    print(f"Warning: Could not import color_system module: {e}")
    print("Tests will be skipped. Run in an environment with all dependencies installed.")
    IMPORTS_AVAILABLE = False

import pytest


@pytest.mark.skipif(not IMPORTS_AVAILABLE, reason="color_system module not available")
def test_single_color_to_tone_group():
    """Test that a single color maps to its correct tone group"""
    detailed_colors = {"red": 100.0}
    result = calculate_tone_groups_from_detailed(detailed_colors)
    
    assert "red_tones" in result
    assert result["red_tones"] == 100.0
    assert len(result) == 1


@pytest.mark.skipif(not IMPORTS_AVAILABLE, reason="color_system module not available")
def test_ambiguous_color_split():
    """Test that ambiguous colors split percentage across multiple tone groups"""
    detailed_colors = {"gold": 100.0}
    result = calculate_tone_groups_from_detailed(detailed_colors)
    
    assert "orange_tones" in result
    assert "yellow_tones" in result
    assert result["orange_tones"] == 50.0
    assert result["yellow_tones"] == 50.0
    assert len(result) == 2


@pytest.mark.skipif(not IMPORTS_AVAILABLE, reason="color_system module not available")
def test_normalization_to_100_percent():
    """Test that percentages are normalized to sum to 100%"""
    detailed_colors = {"red": 50.0, "blue": 30.0, "green": 40.0}
    result = calculate_tone_groups_from_detailed(detailed_colors)
    
    total = sum(result.values())
    assert abs(total - 100.0) < 0.1


@pytest.mark.skipif(not IMPORTS_AVAILABLE, reason="color_system module not available")
def test_empty_detailed_colors():
    """Test that empty detailed colors returns empty dict"""
    detailed_colors = {}
    result = calculate_tone_groups_from_detailed(detailed_colors)
    
    assert result == {}


@pytest.mark.skipif(not IMPORTS_AVAILABLE, reason="color_system module not available")
def test_white_and_black_tones():
    """Test the new white_tones and black_tones groups"""
    detailed_colors = {"white": 50.0, "black": 50.0}
    result = calculate_tone_groups_from_detailed(detailed_colors)
    
    assert "white_tones" in result
    assert "black_tones" in result
    assert result["white_tones"] == 50.0
    assert result["black_tones"] == 50.0
