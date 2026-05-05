#!/usr/bin/env python3
"""
Test script to debug color analysis functions
"""
import cv2
import numpy as np
from src.ai.color_system import analyze_detailed_colors, get_color_groups, get_primary_detailed_color, get_primary_color_group

def create_test_image():
    """Create a simple test image with known colors"""
    # Create a 200x200 image with different color regions
    img = np.zeros((200, 200, 3), dtype=np.uint8)
    
    # Red region (top-left)
    img[0:100, 0:100] = [0, 0, 255]  # Red in BGR
    
    # Blue region (top-right) 
    img[0:100, 100:200] = [255, 0, 0]  # Blue in BGR
    
    # Green region (bottom-left)
    img[100:200, 0:100] = [0, 255, 0]  # Green in BGR
    
    # White region (bottom-right)
    img[100:200, 100:200] = [255, 255, 255]  # White in BGR
    
    return img

def test_color_analysis():
    """Test the color analysis pipeline"""
    print("🧪 Testing Color Analysis Functions...")
    
    # Create test image
    test_img = create_test_image()
    print(f"✅ Created test image: {test_img.shape}")
    
    # Test analyze_detailed_colors
    print("\n🎨 Testing analyze_detailed_colors...")
    try:
        detailed_colors = analyze_detailed_colors(test_img)
        print(f"✅ analyze_detailed_colors result: {detailed_colors}")
        print(f"   - Number of colors detected: {len(detailed_colors)}")
        
        if detailed_colors:
            print("   - Top colors:")
            for color, pct in sorted(detailed_colors.items(), key=lambda x: x[1], reverse=True)[:5]:
                print(f"     * {color}: {pct}%")
        else:
            print("   ⚠️ No colors detected!")
            
    except Exception as e:
        print(f"❌ analyze_detailed_colors error: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    # Test get_color_groups
    print("\n🎯 Testing get_color_groups...")
    try:
        color_groups = get_color_groups(detailed_colors)
        print(f"✅ get_color_groups result: {color_groups}")
        print(f"   - Number of groups: {len(color_groups)}")
        
        if color_groups:
            print("   - Groups:")
            for group, pct in color_groups.items():
                print(f"     * {group}: {pct}%")
        else:
            print("   ⚠️ No color groups created!")
            
    except Exception as e:
        print(f"❌ get_color_groups error: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    # Test get_primary_detailed_color
    print("\n🏆 Testing get_primary_detailed_color...")
    try:
        primary_color = get_primary_detailed_color(detailed_colors)
        print(f"✅ Primary detailed color: {primary_color}")
        
        if primary_color == "unknown":
            print("   ⚠️ Primary color is 'unknown'!")
            
    except Exception as e:
        print(f"❌ get_primary_detailed_color error: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    # Test get_primary_color_group
    print("\n👑 Testing get_primary_color_group...")
    try:
        primary_group = get_primary_color_group(color_groups)
        print(f"✅ Primary color group: {primary_group}")
        
        if primary_group == "unknown":
            print("   ⚠️ Primary color group is 'unknown'!")
            
    except Exception as e:
        print(f"❌ get_primary_color_group error: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    print("\n✅ All color analysis tests completed!")
    return True

if __name__ == "__main__":
    test_color_analysis()
