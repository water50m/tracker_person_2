#!/usr/bin/env python3
"""
Test for color categories overlapping grouping.

This test verifies that calculate_category_groups() and get_color_categories()
populate all 5 categories (tone, brightness, vibrancy, temperature, clothing)
for every image using overlapping grouping (not competitive).
"""

import sys
import importlib.util

# Direct import to avoid package __init__.py dependencies
spec = importlib.util.spec_from_file_location("color_system", "e:\\ALL_CODE\\my-project\\src\\ai\\color_system.py")
color_system = importlib.util.module_from_spec(spec)
spec.loader.exec_module(color_system)

calculate_category_groups = color_system.calculate_category_groups
get_color_categories = color_system.get_color_categories


def test_overlapping_grouping_all_categories_populated():
    """
    Test that overlapping grouping populates all 5 categories.
    
    Example from plan: "scarlet" should appear in multiple categories:
    - tone: red_tones (scarlet is in red_tones group)
    - brightness: medium_colors (scarlet is in medium_colors group)
    - vibrancy: vibrant_colors (scarlet is in vibrant_colors group)
    - temperature: warm_colors (scarlet is in warm_colors group)
    - clothing: casual_colors (scarlet is in casual_colors group)
    """
    # Test with scarlet (the example from the plan)
    detailed_colors = {
        "scarlet": 100.0
    }
    
    result = calculate_category_groups(detailed_colors)
    
    # Verify all 5 categories exist
    assert "tone_groups" in result, "tone_groups missing"
    assert "brightness_groups" in result, "brightness_groups missing"
    assert "vibrancy_groups" in result, "vibrancy_groups missing"
    assert "temperature_groups" in result, "temperature_groups missing"
    assert "clothing_groups" in result, "clothing_groups missing"
    
    # Verify scarlet appears in multiple categories (overlapping)
    tone_groups = result["tone_groups"]
    brightness_groups = result["brightness_groups"]
    vibrancy_groups = result["vibrancy_groups"]
    temperature_groups = result["temperature_groups"]
    clothing_groups = result["clothing_groups"]
    
    print("Test 1: Single color (scarlet)")
    print(f"  tone_groups: {tone_groups}")
    print(f"  brightness_groups: {brightness_groups}")
    print(f"  vibrancy_groups: {vibrancy_groups}")
    print(f"  temperature_groups: {temperature_groups}")
    print(f"  clothing_groups: {clothing_groups}")
    
    # scarlet should be in red_tones
    assert "red_tones" in tone_groups, "scarlet should be in red_tones"
    assert tone_groups["red_tones"] == 100.0
    
    # scarlet should be in vibrant_colors
    assert "vibrant_colors" in vibrancy_groups, "scarlet should be in vibrant_colors"
    assert vibrancy_groups["vibrant_colors"] == 100.0
    
    # scarlet should be in warm_colors
    assert "warm_colors" in temperature_groups, "scarlet should be in warm_colors"
    assert temperature_groups["warm_colors"] == 100.0
    
    print("✓ Test 1 passed: scarlet appears in multiple categories\n")


def test_multiple_colors_overlapping():
    """
    Test with multiple colors to verify overlapping works correctly.
    """
    detailed_colors = {
        "scarlet": 30.0,
        "navy": 40.0,
        "white": 30.0
    }
    
    result = calculate_category_groups(detailed_colors)
    
    print("Test 2: Multiple colors (scarlet, navy, white)")
    print(f"  tone_groups: {result['tone_groups']}")
    print(f"  brightness_groups: {result['brightness_groups']}")
    print(f"  vibrancy_groups: {result['vibrancy_groups']}")
    print(f"  temperature_groups: {result['temperature_groups']}")
    print(f"  clothing_groups: {result['clothing_groups']}")
    
    # Verify tone groups have multiple entries
    assert len(result["tone_groups"]) >= 2, "Should have multiple tone groups"
    assert "red_tones" in result["tone_groups"], "Should have red_tones"
    assert "blue_tones" in result["tone_groups"], "Should have blue_tones"
    
    # Verify brightness groups
    assert len(result["brightness_groups"]) >= 1, "Should have brightness groups"
    
    # Verify temperature groups
    assert "warm_colors" in result["temperature_groups"], "Should have warm_colors"
    assert "cool_colors" in result["temperature_groups"], "Should have cool_colors"
    
    # Verify clothing groups
    assert len(result["clothing_groups"]) >= 1, "Should have clothing groups"
    
    print("✓ Test 2 passed: multiple colors overlap correctly\n")


def test_get_color_categories_wrapper():
    """
    Test that get_color_categories() correctly wraps calculate_category_groups().
    """
    detailed_colors = {
        "scarlet": 50.0,
        "navy": 50.0
    }
    
    result = get_color_categories(detailed_colors)
    
    print("Test 3: get_color_categories() wrapper")
    print(f"  Result keys: {list(result.keys())}")
    
    # Verify all 5 categories exist
    assert "tone_groups" in result
    assert "brightness_groups" in result
    assert "vibrancy_groups" in result
    assert "temperature_groups" in result
    assert "clothing_groups" in result
    
    # Verify it matches calculate_category_groups
    direct_result = calculate_category_groups(detailed_colors)
    assert result == direct_result, "get_color_categories should match calculate_category_groups"
    
    print("✓ Test 3 passed: get_color_categories() wrapper works correctly\n")


def test_empty_detailed_colors():
    """
    Test with empty detailed_colors.
    """
    detailed_colors = {}
    
    result = calculate_category_groups(detailed_colors)
    
    print("Test 4: Empty detailed_colors")
    print(f"  Result: {result}")
    
    # All categories should exist but be empty
    assert result["tone_groups"] == {}
    assert result["brightness_groups"] == {}
    assert result["vibrancy_groups"] == {}
    assert result["temperature_groups"] == {}
    assert result["clothing_groups"] == {}
    
    print("✓ Test 4 passed: empty colors handled correctly\n")


if __name__ == "__main__":
    print("=" * 60)
    print("Testing Color Categories Overlapping Grouping")
    print("=" * 60)
    print()
    
    try:
        test_overlapping_grouping_all_categories_populated()
        test_multiple_colors_overlapping()
        test_get_color_categories_wrapper()
        test_empty_detailed_colors()
        
        print("=" * 60)
        print("✓ All tests passed!")
        print("=" * 60)
        
    except AssertionError as e:
        print(f"\n✗ Test failed: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n✗ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
