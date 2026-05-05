"""
config_loader.py - Global configuration loader
Loads system_settings.json once and caches it for use across the entire system.
"""
import json
from pathlib import Path
from typing import Any, Dict

# Singleton cache
_config_cache: Dict[str, Any] | None = None
_config_path = Path("config/system_settings.json")


def load_config(force_reload: bool = False) -> Dict[str, Any]:
    """
    Load configuration from system_settings.json.
    Caches the result for subsequent calls.
    
    Args:
        force_reload: If True, reload from disk even if cached.
    
    Returns:
        Dictionary containing configuration with sections:
        - paths: upload_dir, output_dir, temp_dir, log_dir
        - models: detector_model, classifier_model, reid_model_path
        - detection: detection_confidence, iou_threshold, detection_enabled
        - tracking: max_tracks, frame_skip, classification_enabled
        - system: device, batch_size, num_workers
    """
    global _config_cache
    
    if _config_cache is not None and not force_reload:
        return _config_cache
    
    if not _config_path.exists():
        raise RuntimeError(f"Config file not found at {_config_path}")
    
    try:
        raw = json.loads(_config_path.read_text())
        # Strip the _comment key — it's documentation only
        _config_cache = {k: v for k, v in raw.items() if not k.startswith("_")}
        return _config_cache
    except Exception as e:
        raise RuntimeError(f"Failed to read system_settings.json: {e}")


def get_detector_model_path() -> str:
    """Get detector model path from config."""
    config = load_config()
    return config["models"]["detector_model"]


def get_classifier_model_path() -> str:
    """Get classifier model path from config."""
    config = load_config()
    return config["models"]["classifier_model"]


def get_reid_model_path() -> str:
    """Get re-identification model path from config."""
    config = load_config()
    return config["models"]["reid_model_path"]


def get_device() -> str:
    """Get device setting from config."""
    config = load_config()
    return config["system"]["device"]


def get_detection_confidence() -> float:
    """Get detection confidence threshold from config."""
    config = load_config()
    return config["detection"]["detection_confidence"]


def get_iou_threshold() -> float:
    """Get IoU threshold from config."""
    config = load_config()
    return config["detection"]["iou_threshold"]


def get_max_tracks() -> int:
    """Get max tracks from config."""
    config = load_config()
    return config["tracking"]["max_tracks"]


def get_frame_skip() -> int:
    """Get frame skip from config."""
    config = load_config()
    return config["tracking"]["frame_skip"]


def get_upload_dir() -> str:
    """Get upload directory from config."""
    config = load_config()
    return config["paths"]["upload_dir"]


def get_output_dir() -> str:
    """Get output directory from config."""
    config = load_config()
    return config["paths"]["output_dir"]


def get_temp_dir() -> str:
    """Get temp directory from config."""
    config = load_config()
    return config["paths"]["temp_dir"]


def get_log_dir() -> str:
    """Get log directory from config."""
    config = load_config()
    return config["paths"]["log_dir"]


def reload_config() -> Dict[str, Any]:
    """Force reload configuration from disk."""
    return load_config(force_reload=True)


# =============================================================================
# Feature Flags for AI Processor Refactoring
# =============================================================================
# These flags control whether to use the refactored (new) or original (old)
# implementations of AI processing components. They can be toggled at runtime
# via environment variables without requiring a redeploy.
#
# Usage:
#   set USE_REFACTORED_IMAGE_ANALYZER=true
#   uv run python main.py
#
# Rollback:
#   set USE_REFACTORED_IMAGE_ANALYZER=false
# =============================================================================

import os


def get_feature_flag(flag_name: str, default: bool = False) -> bool:
    """
    Get a feature flag value from environment variable.
    
    Args:
        flag_name: Name of the environment variable
        default: Default value if not set
    
    Returns:
        True if env var is "true", "1", or "yes" (case insensitive)
        False otherwise
    """
    value = os.getenv(flag_name, "").lower()
    return value in ("true", "1", "yes", "on")


def use_refactored_image_analyzer() -> bool:
    """Check if refactored ImageAnalyzer should be used."""
    return get_feature_flag("USE_REFACTORED_IMAGE_ANALYZER", default=False)


def use_refactored_video_processor() -> bool:
    """Check if refactored VideoProcessor should be used."""
    return get_feature_flag("USE_REFACTORED_VIDEO_PROCESSOR", default=False)


def use_refactored_stream_processor() -> bool:
    """Check if refactored StreamProcessor should be used for realtime streams."""
    return get_feature_flag("USE_REFACTORED_STREAM_PROCESSOR", default=False)


def get_rollout_percentage() -> int:
    """
    Get rollout percentage for gradual feature flag deployment.
    
    Returns:
        Integer 0-100 representing percentage of traffic to route to new code
    """
    try:
        value = int(os.getenv("ROLLOUT_PERCENTAGE", "0"))
        return max(0, min(100, value))
    except ValueError:
        return 0


def should_use_refactored_for_camera(camera_id: str) -> bool:
    """
    Determine whether to use refactored code for a specific camera.
    Uses consistent hashing so the same camera always gets the same path.
    
    Args:
        camera_id: Camera identifier
    
    Returns:
        True if this camera should use refactored code
    """
    rollout_pct = get_rollout_percentage()
    
    if rollout_pct >= 100:
        return True
    if rollout_pct <= 0:
        return False
    
    # Hash camera_id to get consistent 0-99 value
    hash_val = hash(camera_id) % 100
    return hash_val < rollout_pct


def get_feature_flags_status() -> dict:
    """
    Get current status of all feature flags for monitoring/debugging.
    
    Returns:
        Dictionary with all feature flag values
    """
    return {
        "USE_REFACTORED_IMAGE_ANALYZER": use_refactored_image_analyzer(),
        "USE_REFACTORED_VIDEO_PROCESSOR": use_refactored_video_processor(),
        "USE_REFACTORED_STREAM_PROCESSOR": use_refactored_stream_processor(),
        "ROLLOUT_PERCENTAGE": get_rollout_percentage(),
    }
