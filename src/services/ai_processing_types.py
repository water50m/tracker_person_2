"""
ai_processing_types.py - Core data structures for AI processing

This module defines dataclasses used across the refactored AI processing pipeline.
These types are shared between:
- FrameProcessor: Core sync processing logic
- ThreadPoolProcessor: Thread pool orchestration
- VideoProcessor: Video/stream orchestration
- ImageAnalyzer: Image analysis API
"""
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Tuple
from enum import Enum
import numpy as np


class ClothingCategory(str, Enum):
    """Categories of clothing items."""
    TOP = "TOP"
    BOTTOM = "BOTTOM"
    FULL_BODY = "FULL_BODY"
    ACCESSORY = "ACCESSORY"
    UNKNOWN = "UNKNOWN"


class ProcessingStatus(str, Enum):
    """Status of AI processing for a frame or image."""
    PENDING = "pending"
    PROCESSING = "processing"
    SUCCESS = "success"
    PARTIAL = "partial"
    ERROR = "error"
    NO_DETECTIONS = "no_detections"
    SKIPPED = "skipped"
    STOPPED = "stopped"
    TIMEOUT = "timeout"


@dataclass
class BoundingBox:
    """Bounding box coordinates in pixel values."""
    x: int  # top-left x
    y: int  # top-left y
    width: int
    height: int
    
    @property
    def x2(self) -> int:
        """Bottom-right x coordinate."""
        return self.x + self.width
    
    @property
    def y2(self) -> int:
        """Bottom-right y coordinate."""
        return self.y + self.height
    
    @property
    def center(self) -> Tuple[int, int]:
        """Center point of the bounding box."""
        return (self.x + self.width // 2, self.y + self.height // 2)
    
    def to_xyxy(self) -> Tuple[int, int, int, int]:
        """Convert to (x1, y1, x2, y2) format."""
        return (self.x, self.y, self.x2, self.y2)
    
    @classmethod
    def from_xyxy(cls, x1: int, y1: int, x2: int, y2: int) -> "BoundingBox":
        """Create from (x1, y1, x2, y2) format."""
        return cls(x=x1, y=y1, width=x2 - x1, height=y2 - y1)


@dataclass
class ColorData:
    """Color information for a clothing item."""
    color_name: str
    hex_value: Optional[str] = None
    confidence: float = 0.0
    percentage: float = 0.0  # Percentage of item with this color
    rgb: Optional[Tuple[int, int, int]] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "color_name": self.color_name,
            "hex_value": self.hex_value,
            "confidence": self.confidence,
            "percentage": self.percentage,
            "rgb": self.rgb,
        }


@dataclass
class DetectedItem:
    """
    A detected clothing item within a person's bounding box.
    
    This represents one piece of clothing (e.g., a shirt) detected
    and classified on a person.
    """
    # Classification
    class_name: str  # e.g., "Short_Sleeve_Shirt"
    category: ClothingCategory = ClothingCategory.UNKNOWN
    confidence: float = 0.0
    
    # Location within person bounding box (normalized 0-1)
    relative_bbox: Optional[BoundingBox] = None  # bbox relative to person
    
    # Color information
    primary_color: Optional[ColorData] = None
    secondary_colors: List[ColorData] = field(default_factory=list)
    detailed_colors: List[Dict[str, Any]] = field(default_factory=list)
    color_groups: List[str] = field(default_factory=list)
    
    # Top-N predictions (for ambiguous cases)
    top_predictions: List[Tuple[str, float]] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "class_name": self.class_name,
            "category": self.category.value,
            "confidence": self.confidence,
            "relative_bbox": {
                "x": self.relative_bbox.x,
                "y": self.relative_bbox.y,
                "width": self.relative_bbox.width,
                "height": self.relative_bbox.height,
            } if self.relative_bbox else None,
            "primary_color": self.primary_color.to_dict() if self.primary_color else None,
            "secondary_colors": [c.to_dict() for c in self.secondary_colors],
            "detailed_colors": self.detailed_colors,
            "color_groups": self.color_groups,
        }


@dataclass
class PersonDetection:
    """
    A detected person with tracking information and clothing items.
    
    This represents one person detected in a frame, including:
    - Tracking ID (from ByteTrack)
    - Persistent ID (from Re-ID)
    - Bounding box
    - Detected clothing items
    - Appearance embedding (for Re-ID)
    """
    # Detection & Tracking
    track_id: int  # ByteTrack ID (temporary, per-stream)
    persistent_id: Optional[int] = None  # Re-ID (persistent across cameras/time)
    bbox: BoundingBox = field(default_factory=lambda: BoundingBox(0, 0, 0, 0))
    confidence: float = 0.0
    
    # Clothing items detected on this person
    items: List[DetectedItem] = field(default_factory=list)
    
    # Re-ID embedding vector
    embedding: Optional[np.ndarray] = None
    
    # Metadata
    frame_number: int = 0
    timestamp: Optional[float] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "track_id": self.track_id,
            "persistent_id": self.persistent_id,
            "bbox": {
                "x": self.bbox.x,
                "y": self.bbox.y,
                "width": self.bbox.width,
                "height": self.bbox.height,
            },
            "confidence": self.confidence,
            "items": [item.to_dict() for item in self.items],
            "frame_number": self.frame_number,
            "timestamp": self.timestamp,
        }


@dataclass
class AIProcessingResult:
    """
    Complete result from processing a single frame or image.
    
    This is the main output type from FrameProcessor and the
    input type for downstream processing (database storage, etc.).
    """
    # Status
    status: ProcessingStatus = ProcessingStatus.SUCCESS
    error_message: Optional[str] = None
    
    # Detections
    detections: List[PersonDetection] = field(default_factory=list)
    num_persons: int = 0
    
    # Processing metadata
    frame_number: int = 0
    timestamp: Optional[float] = None
    processing_time_ms: float = 0.0
    
    # Original image info (for debugging/storage)
    image_width: int = 0
    image_height: int = 0
    
    # Optional: raw frame data (for display/streaming)
    annotated_frame: Optional[np.ndarray] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "status": self.status.value,
            "error_message": self.error_message,
            "detections": [d.to_dict() for d in self.detections],
            "num_persons": len(self.detections),
            "frame_number": self.frame_number,
            "timestamp": self.timestamp,
            "processing_time_ms": self.processing_time_ms,
            "image_width": self.image_width,
            "image_height": self.image_height,
        }


@dataclass
class VideoProcessingStats:
    """
    Statistics from processing an entire video or stream.
    
    This is returned by VideoProcessor after processing completes.
    """
    # Identity
    video_id: Optional[str] = None
    camera_id: Optional[str] = None
    
    # Basic stats
    total_frames: int = 0
    processed_frames: int = 0
    skipped_frames: int = 0
    
    # Video info
    fps: float = 0.0
    image_width: int = 0
    image_height: int = 0
    
    # Detections
    total_detections: int = 0
    num_persons_detected: int = 0  # Total persons found
    num_detections_saved: int = 0  # Saved to database
    unique_persons: int = 0  # Number of unique persistent IDs
    
    # Status
    status: ProcessingStatus = ProcessingStatus.PENDING
    error_message: Optional[str] = None
    completed: bool = False  # Whether processing completed fully
    
    # Timing
    start_time: Optional[float] = None
    end_time: Optional[float] = None
    processing_time_ms: float = 0.0
    
    # Error tracking
    num_errors: int = 0
    
    @property
    def duration_seconds(self) -> float:
        """Total processing duration."""
        if self.start_time and self.end_time:
            return self.end_time - self.start_time
        return 0.0
    
    @property
    def effective_fps(self) -> float:
        """Effective processing FPS (calculated from duration)."""
        if self.duration_seconds > 0:
            return self.processed_frames / self.duration_seconds
        return 0.0
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "video_id": self.video_id,
            "camera_id": self.camera_id,
            "total_frames": self.total_frames,
            "processed_frames": self.processed_frames,
            "skipped_frames": self.skipped_frames,
            "fps": self.fps,
            "image_width": self.image_width,
            "image_height": self.image_height,
            "total_detections": self.total_detections,
            "num_persons_detected": self.num_persons_detected,
            "num_detections_saved": self.num_detections_saved,
            "unique_persons": self.unique_persons,
            "status": self.status.value if self.status else None,
            "error_message": self.error_message,
            "completed": self.completed,
            "duration_seconds": self.duration_seconds,
            "effective_fps": self.effective_fps,
            "processing_time_ms": self.processing_time_ms,
            "num_errors": self.num_errors,
        }


@dataclass
class ImageAnalysisResult:
    """
    Result from analyzing a single image (for auto-fill search).
    
    This is the output from ImageAnalyzer and matches the
    API contract expected by the frontend.
    """
    # API Response format
    status: str = "success"  # "success" or "error"
    message: Optional[str] = None
    
    # Detected attributes (for backward compatibility)
    class_name: Optional[str] = None
    color_name: Optional[str] = None
    
    # Extended information
    category: Optional[str] = None
    confidence: float = 0.0
    
    # All detected items (for detailed view)
    all_items: List[DetectedItem] = field(default_factory=list)


@dataclass
class StreamProcessingStats:
    """
    Statistics from processing a real-time stream.
    
    This is returned by StreamProcessor when stream stops.
    Unlike VideoProcessingStats, this doesn't have total_frames
    because streams are continuous/infinite.
    """
    # Identity
    camera_id: Optional[str] = None
    
    # Basic stats
    processed_frames: int = 0
    
    # Video info
    fps: float = 0.0
    image_width: int = 0
    image_height: int = 0
    
    # Detections
    total_detections: int = 0
    num_persons_detected: int = 0
    num_detections_saved: int = 0
    
    # Status
    status: ProcessingStatus = ProcessingStatus.PENDING
    error_message: Optional[str] = None
    
    # Timing
    start_time: Optional[float] = None
    end_time: Optional[float] = None
    
    # Error tracking
    num_errors: int = 0
    
    @property
    def duration_seconds(self) -> float:
        """Total stream duration."""
        if self.start_time and self.end_time:
            return self.end_time - self.start_time
        if self.start_time:
            return time.time() - self.start_time
        return 0.0
    
    @property
    def effective_fps(self) -> float:
        """Effective processing FPS."""
        if self.duration_seconds > 0:
            return self.processed_frames / self.duration_seconds
        return 0.0
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "camera_id": self.camera_id,
            "processed_frames": self.processed_frames,
            "fps": self.fps,
            "image_width": self.image_width,
            "image_height": self.image_height,
            "total_detections": self.total_detections,
            "num_persons_detected": self.num_persons_detected,
            "num_detections_saved": self.num_detections_saved,
            "status": self.status.value if self.status else None,
            "error_message": self.error_message,
            "duration_seconds": self.duration_seconds,
            "effective_fps": self.effective_fps,
            "num_errors": self.num_errors,
        }
    
    # Processing metadata
    processing_time_ms: float = 0.0
    num_persons_detected: int = 0
    
    def to_api_response(self) -> Dict[str, Any]:
        """
        Convert to API response format expected by frontend.
        
        Matches the original analyze_image_for_search response:
        {
            "status": "success",
            "detected_attributes": {
                "class_name": "...",
                "color_name": "..."
            }
        }
        """
        if self.status == "error":
            return {
                "status": "error",
                "message": self.message or "Unknown error",
            }
        
        response = {
            "status": "success",
            "detected_attributes": {},
        }
        
        # Primary detection (first person's first item, or first item overall)
        if self.class_name:
            response["detected_attributes"]["class_name"] = self.class_name
        if self.color_name:
            response["detected_attributes"]["color_name"] = self.color_name
        
        # Extended fields (for frontend enhancements)
        if self.category:
            response["detected_attributes"]["category"] = self.category
        if self.confidence > 0:
            response["detected_attributes"]["confidence"] = round(self.confidence, 3)
        
        # Metadata
        response["processing_time_ms"] = round(self.processing_time_ms, 2)
        response["num_persons_detected"] = self.num_persons_detected
        
        # All items (if requested)
        if self.all_items:
            response["all_items"] = [item.to_dict() for item in self.all_items]
        
        return response


# Type aliases for clarity
FrameNumber = int
TrackID = int
PersistentID = int
