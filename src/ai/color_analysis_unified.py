"""
Unified Color Analysis Module

This module provides a single, reusable color analysis function that can be used
by both the main video processing pipeline and real-time streaming endpoints.

This ensures both flows produce identical color data structures.
"""

from typing import Dict, Any, List, Optional, Tuple
import numpy as np

# Import existing color system functions
from src.ai.color_system import (
    analyze_detailed_colors,
    get_color_groups,
    get_primary_detailed_color,
    get_primary_color_group,
    get_primary_tone_group,
    get_top_colors,
    get_color_categories,
    get_color_tone_group,
    calculate_tone_groups_from_detailed,
)

# Import embedder
from src.ai.feature_extractor import ClothingEmbedder


def get_region_crop(person_crop: np.ndarray, clothing_type: str) -> Tuple[np.ndarray, str]:
    """
    Extract the relevant region of the person based on clothing type.
    
    Args:
        person_crop: Full person crop image
        clothing_type: Type of clothing detected
        
    Returns:
        Tuple of (cropped_region, category)
    """
    if person_crop is None or person_crop.size == 0:
        return person_crop, "UNKNOWN"
    
    h, w = person_crop.shape[:2]
    
    # Dress/Robe - analyze full body
    if clothing_type in ["Dress", "Robe"]:
        return person_crop, "FULL"
    
    # Bottom clothing - analyze lower half
    elif clothing_type in ["Jeans", "Shorts", "Skirt"]:
        region = person_crop[int(h*0.50):int(h*0.90), :]
        return region, "BOTTOM"
    
    # Default/Tops - analyze upper body
    else:
        region = person_crop[int(h*0.15):int(h*0.50), :]
        return region, "TOP"




def build_db_detection_data(
    track_id: int,
    clothing_type: str,
    confidence: float,
    color_results: Dict[str, Any],
    bbox: List[int],
    camera_id: str,
    video_id: Optional[str] = None,
    video_time_offset: int = 0,
    image_path: str = "",
    bbox_image_path: str = "",
) -> Dict[str, Any]:
    """
    Build standardized detection data dictionary for database insertion.

    This ensures both real-time and batch processing produce identical DB records.

    Args:
        track_id: Person track ID
        clothing_type: Detected clothing type
        confidence: Detection confidence (0-1)
        color_results: Output from analyze_person_colors()
        bbox: Bounding box [x1, y1, x2, y2]
        camera_id: Camera identifier
        video_id: Optional video identifier
        video_time_offset: Time offset in video (seconds)
        image_path: Path to stored person image
        bbox_image_path: Path to stored bbox image

    Returns:
        Dictionary ready for DatabaseService.insert_detection() and insert_detection_colors()
    """
    return {
        # Core detection fields
        "track_id": track_id,
        "class_name": clothing_type,
        "category": color_results.get("category", "UNKNOWN"),
        "confidence": confidence,
        "bbox": bbox,
        "camera_id": camera_id,
        "video_id": video_id,
        "video_time_offset": video_time_offset,
        "image_path": image_path,
        "bbox_image_path": bbox_image_path,

        # Primary color data (for detections table)
        "detailed_colors": color_results.get("detailed_colors", {}),
        "color_groups": color_results.get("color_groups", {}),
        "primary_detailed_color": color_results.get("primary_detailed_color", "unknown"),
        "primary_color_group": color_results.get("primary_color_group", "unknown"),

        # Secondary color groups (for detection_colors table)
        "top_colors": color_results.get("top_colors", []),
        "brightness_groups": color_results.get("brightness_groups", {}),
        "vibrancy_groups": color_results.get("vibrancy_groups", {}),
        "temperature_groups": color_results.get("temperature_groups", {}),
        "clothing_color_groups": color_results.get("clothing_color_groups", {}),

        # Re-ID data
        "embedding": color_results.get("embedding"),
        "clothes": color_results.get("clothes_list", [clothing_type]),
    }


def analyze_clothing_colors(
    clothing_crop: np.ndarray
) -> Dict[str, Any]:
    """
    Analyze colors from a pre-cropped clothing image.
    
    PURE COLOR ANALYSIS - No embedding processing here.
    Embedding should be handled in the detection pipeline separately.
    
    Args:
        clothing_crop: The cropped clothing image (numpy array)
        
    Returns:
        Dictionary containing color analysis data ONLY:
        {
            "category": "CLOTHING_CROP",
            "clothing_type": "Unknown",
            
            # Detailed color analysis (63 colors)
            "detailed_colors": Dict[str, float],
            "top_colors": List[Dict],
            "primary_detailed_color": str,
            
            # Secondary groups (calculated from detailed_colors)
            "brightness_groups": Dict[str, float],
            "vibrancy_groups": Dict[str, float],
            "temperature_groups": Dict[str, float],
            "clothing_color_groups": Dict[str, float],
        }
    """
    # Default return structure
    default_result = {
        "category": "CLOTHING_CROP",
        "clothing_type": "Unknown",
        "detailed_colors": {},
        "top_colors": [],
        "primary_detailed_color": "unknown",
        "brightness_groups": {},
        "vibrancy_groups": {},
        "temperature_groups": {},
        "clothing_color_groups": {},
    }

    if clothing_crop is None or clothing_crop.size == 0:
        return default_result

    try:
        print(f"[COLOR] Analyzing clothing crop directly")

        # Step 1: Analyze detailed colors (63-color system) on the entire crop
        detailed_colors = analyze_detailed_colors(clothing_crop)

        # Log dominant colors
        dominant_colors = sorted(detailed_colors.items(), key=lambda x: x[1], reverse=True)[:3]
        dominant_color_names = [f"{name}({pct:.1f}%)" for name, pct in dominant_colors]
        print(f"[COLOR] Dominant colors: {dominant_color_names}")

        # Step 2: Get primary detailed color
        primary_detailed_color = get_primary_detailed_color(detailed_colors)

        # Step 3: Get top 3 colors with tone group information
        top_colors = get_top_colors(detailed_colors, n=3, include_group=True)

        # Step 4: Categorize groups into 4 columns (excluding tone_groups)
        categorized = get_color_categories(detailed_colors)

        return {
            "category": "CLOTHING_CROP",
            "clothing_type": "Unknown",
            "detailed_colors": detailed_colors,
            "top_colors": top_colors,
            "primary_detailed_color": primary_detailed_color,
            "brightness_groups": categorized.get("brightness_groups", {}),
            "vibrancy_groups": categorized.get("vibrancy_groups", {}),
            "temperature_groups": categorized.get("temperature_groups", {}),
            "clothing_color_groups": categorized.get("clothing_groups", {}),
        }

    except Exception as e:
        print(f"❌ Clothing color analysis error: {e}")
        import traceback
        traceback.print_exc()
        return default_result


# Convenience function for quick color analysis without full setup
def quick_color_analysis(image: np.ndarray, clothing_type: str = "Unknown") -> Dict[str, Any]:
    """
    Quick color analysis without embedding extraction.
    Useful for simple use cases or testing.
    """
    return analyze_person_colors(image, clothing_type, embedder=None)
