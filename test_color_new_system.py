#!/usr/bin/env python3
"""
Test script for the new unified color system (63 colors + 22 groups)
Shows example output format that gets saved to database
"""

import sys
import os

# Add src to path
project_root = os.path.dirname(os.path.abspath(__file__))
src_path = os.path.join(project_root, 'src')
sys.path.insert(0, src_path)

import cv2
import numpy as np
import json

# Import directly from module file to avoid __init__.py dependency
import importlib.util
spec = importlib.util.spec_from_file_location("color_system", os.path.join(src_path, "ai", "color_system.py"))
color_system = importlib.util.module_from_spec(spec)
spec.loader.exec_module(color_system)

analyze_detailed_colors = color_system.analyze_detailed_colors
get_color_groups = color_system.get_color_groups
get_primary_detailed_color = color_system.get_primary_detailed_color
get_primary_color_group = color_system.get_primary_color_group
get_primary_tone_group = color_system.get_primary_tone_group
get_top_colors = color_system.get_top_colors
get_color_categories = color_system.get_color_categories
get_color_tone_group = color_system.get_color_tone_group
get_all_detailed_colors = color_system.get_all_detailed_colors
get_all_color_groups = color_system.get_all_color_groups

def create_test_image(color_bgr, size=(200, 300)):
    """Create a solid color test image"""
    img = np.full((size[1], size[0], 3), color_bgr, dtype=np.uint8)
    return img

def print_section(title):
    """Print a formatted section header"""
    print("\n" + "=" * 70)
    print(f"  {title}")
    print("=" * 70)

def main():
    print_section("COLOR SYSTEM OVERVIEW")
    
    # Show available colors and groups
    print(f"\n📊 Total Detailed Colors: {len(get_all_detailed_colors())}")
    print(f"📊 Total Color Groups: {len(get_all_color_groups())}")
    
    print("\n🎨 Sample Color -> Tone Group Mapping:")
    sample_colors = ["peach", "light_blue", "dark_gray", "navy", "coral", "mint"]
    for color in sample_colors:
        tone_group = get_color_tone_group(color)
        print(f"   {color:15s} -> {tone_group}")
    
    print("\n🎨 Sample Detailed Colors (first 20):")
    for color in get_all_detailed_colors()[:20]:
        print(f"   - {color}")
    
    print("\n🎨 Sample Color Groups:")
    for group in get_all_color_groups()[:15]:
        print(f"   - {group}")
    
    print_section("TESTING COLOR ANALYSIS")
    
    # Test with different colored images
    test_cases = [
        ("Red Shirt", (0, 0, 255), "Shirt"),
        ("Blue Jeans", (255, 0, 0), "Jeans"),
        ("Black Dress", (0, 0, 0), "Dress"),
        ("White T-Shirt", (255, 255, 255), "Shirt"),
        ("Green Jacket", (0, 255, 0), "Jacket"),
    ]
    
    for name, color_bgr, clothing_type in test_cases:
        print(f"\n{'─' * 70}")
        print(f"🧪 Testing: {name} (BGR: {color_bgr})")
        print(f"{'─' * 70}")
        
        # Create test image
        test_img = create_test_image(color_bgr)
        
        # Analyze colors using the core color system
        detailed_colors = analyze_detailed_colors(test_img)
        color_groups = get_color_groups(detailed_colors)
        primary_detailed = get_primary_detailed_color(detailed_colors)
        primary_group = get_primary_color_group(color_groups)
        primary_tone = get_primary_tone_group(color_groups)
        top_colors = get_top_colors(detailed_colors, n=3, include_group=True)
        categorized = get_color_categories(color_groups)
        
        # Build result structure similar to analyze_person_colors
        result = {
            "category": "TOP" if clothing_type in ["Shirt", "Jacket"] else "FULL" if clothing_type == "Dress" else "BOTTOM",
            "clothing_type": clothing_type,
            "detailed_colors": detailed_colors,
            "color_groups": color_groups,
            "primary_detailed_color": primary_detailed,
            "primary_color_group": primary_group,
            "primary_tone_group": primary_tone,
            "top_colors": top_colors,
            "tone_groups": categorized.get("tone_groups", {}),
            "brightness_groups": categorized.get("brightness_groups", {}),
            "vibrancy_groups": categorized.get("vibrancy_groups", {}),
            "temperature_groups": categorized.get("temperature_groups", {}),
            "clothing_color_groups": categorized.get("clothing_groups", {}),
        }
        
        # Print results in a format similar to what goes to DB
        print(f"\n📦 Result Structure (Database Format):")
        print(json.dumps({
            "category": result.get("category"),
            "clothing_type": result.get("clothing_type"),
            "primary_detailed_color": result.get("primary_detailed_color"),
            "primary_color_group": result.get("primary_color_group"),
            "primary_tone_group": result.get("primary_tone_group"),
        }, indent=2))
        
        print(f"\n🎨 Detailed Colors (Top 10):")
        detailed = result.get("detailed_colors", {})
        for color, pct in sorted(detailed.items(), key=lambda x: x[1], reverse=True)[:10]:
            print(f"   {color:20s}: {pct:6.1f}%")
        
        print(f"\n🎯 Color Groups:")
        groups = result.get("color_groups", {})
        for group, pct in sorted(groups.items(), key=lambda x: x[1], reverse=True):
            print(f"   {group:25s}: {pct:6.1f}%")
        
        print(f"\n📊 Categorized Groups (for detection_colors table):")
        print(f"   Tone Groups: {result.get('tone_groups', {})}")
        print(f"   Brightness Groups: {result.get('brightness_groups', {})}")
        print(f"   Vibrancy Groups: {result.get('vibrancy_groups', {})}")
        print(f"   Temperature Groups: {result.get('temperature_groups', {})}")
        print(f"   Clothing Groups: {result.get('clothing_color_groups', {})}")
        
        print(f"\n🏆 Top 3 Colors:")
        for color_info in result.get("top_colors", []):
            print(f"   {color_info}")
    
    print_section("DATABASE SCHEMA EXAMPLE")
    
    print("""
The color data is stored in two tables:

1. detections table (legacy fields):
   - detailed_colors: JSONB (63 colors with percentages)
   - color_groups: JSONB (22 groups with percentages)
   - primary_detailed_color: VARCHAR
   - primary_color_group: VARCHAR
   - primary_tone_group: VARCHAR

2. detection_colors table (new structured fields):
   - top_colors: JSONB [{"name": "red", "percentage": 45.5}, ...]
   - tone_groups: JSONB {"red_tones": 45.5, "blue_tones": 30.0, ...}
   - brightness_groups: JSONB {"light_colors": 20.0, "dark_colors": 80.0, ...}
   - vibrancy_groups: JSONB {"vibrant_colors": 60.0, "muted_colors": 40.0, ...}
   - temperature_groups: JSONB {"warm_colors": 70.0, "cool_colors": 30.0, ...}
   - clothing_groups: JSONB {"common_shirt_colors": 50.0, "formal_colors": 50.0, ...}
   - primary_color: VARCHAR (same as primary_detailed_color)
    """)
    
    print_section("SUMMARY")
    print("""
✅ The new color system provides:
   - 63 detailed colors for precise tracking
   - 22 color groups for flexible searching
   - 5 categorized group types (tone, brightness, vibrancy, temperature, clothing)
   - Consistent output format for both batch and real-time processing
   - Better color accuracy with HSV-based competitive grouping
    """)

if __name__ == "__main__":
    main()
