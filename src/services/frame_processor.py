"""
frame_processor.py - Core synchronous frame processing logic

This module contains the FrameProcessor class which performs synchronous
AI processing on a single frame or image. It extracts the core logic from
the legacy video processing monolith into a reusable, testable component.

The FrameProcessor is designed to:
- Run synchronously (no async/await) for use in ThreadPoolExecutor
- Be thread-safe (uses ModelManager singleton for model access)
- Be reusable for both video processing and image analysis
- Support both person detection and clothing classification

Usage:
    from services.frame_processor import FrameProcessor
    from services.ai_processing_types import AIProcessingResult
    
    processor = FrameProcessor()
    result = processor.process_frame(frame, frame_number=1)
"""
import time
import sys
from pathlib import Path
from typing import Optional, List, Tuple, Dict, Any
from collections import defaultdict

import numpy as np
import cv2

# Add parent directory for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from services.ai_processing_types import (
    AIProcessingResult,
    PersonDetection,
    DetectedItem,
    BoundingBox,
    ColorData,
    ClothingCategory,
    ProcessingStatus,
)
from services.model_manager import get_model_manager
from config_loader import get_detection_confidence


class FrameProcessor:
    """
    Synchronous frame processor for AI inference.
    
    This class encapsulates the core AI processing logic:
    1. Person detection (via PersonDetector)
    2. Clothing classification (via ClothingClassifier)
    3. Color analysis
    4. Re-ID embedding extraction (via ClothingEmbedder)
    
    The processor is thread-safe and designed to run inside a ThreadPoolExecutor.
    """
    
    def __init__(
        self,
        enable_classification: bool = True,
        enable_color_analysis: bool = True,
        enable_embedding: bool = True,
        classifier_top_n: int = 1,
    ):
        """
        Initialize the FrameProcessor.
        
        Args:
            enable_classification: Whether to run clothing classification
            enable_color_analysis: Whether to analyze colors
            enable_embedding: Whether to extract Re-ID embeddings
            classifier_top_n: Number of top predictions to return (1 or 'all')
        """
        self.enable_classification = enable_classification
        self.enable_color_analysis = enable_color_analysis
        self.enable_embedding = enable_embedding
        self.classifier_top_n = classifier_top_n
        
        # Get model manager (singleton)
        self._model_manager = get_model_manager()
        
        # Cache for model instances (loaded on first use)
        self._detector = None
        self._classifier = None
        self._embedder = None
        
        # Detection confidence threshold
        self._confidence_threshold = get_detection_confidence()
    
    def _get_detector(self):
        """Lazy load detector model."""
        if self._detector is None:
            self._detector = self._model_manager.get_detector()
        return self._detector
    
    def _get_classifier(self):
        """Lazy load classifier model."""
        if self._classifier is None:
            self._classifier = self._model_manager.get_classifier()
        return self._classifier
    
    def _get_embedder(self):
        """Lazy load embedder model."""
        if self._embedder is None:
            self._embedder = self._model_manager.get_embedder()
        return self._embedder
    
    def process_frame(
        self,
        frame: np.ndarray,
        frame_number: int = 0,
        timestamp: Optional[float] = None,
    ) -> AIProcessingResult:
        """
        Process a single frame synchronously.
        
        This is the main entry point for frame processing. It performs:
        1. Person detection
        2. For each detected person:
           - Crop the person region
           - Run clothing classification
           - Analyze colors
           - Extract embedding (if enabled)
        
        Args:
            frame: Input image/frame (BGR format, numpy array)
            frame_number: Frame number for tracking
            timestamp: Optional timestamp
        
        Returns:
            AIProcessingResult containing all detections and metadata
        """
        start_time = time.perf_counter()
        
        if frame is None or frame.size == 0:
            return AIProcessingResult(
                status=ProcessingStatus.ERROR,
                error_message="Empty or invalid frame",
                frame_number=frame_number,
            )
        
        height, width = frame.shape[:2]
        
        try:
            # Step 1: Person Detection
            detections = self._detect_persons(frame)
            
            if not detections:
                return AIProcessingResult(
                    status=ProcessingStatus.NO_DETECTIONS,
                    frame_number=frame_number,
                    image_width=width,
                    image_height=height,
                    processing_time_ms=(time.perf_counter() - start_time) * 1000,
                )
            
            # Step 2: Process each detected person
            person_detections = []
            for track_id, bbox, confidence in detections:
                person = self._process_person(
                    frame,
                    track_id,
                    bbox,
                    confidence,
                    frame_number,
                )
                person_detections.append(person)
            
            # Calculate processing time
            processing_time_ms = (time.perf_counter() - start_time) * 1000
            
            return AIProcessingResult(
                status=ProcessingStatus.SUCCESS,
                detections=person_detections,
                num_persons=len(person_detections),
                frame_number=frame_number,
                timestamp=timestamp,
                processing_time_ms=processing_time_ms,
                image_width=width,
                image_height=height,
            )
            
        except Exception as e:
            return AIProcessingResult(
                status=ProcessingStatus.ERROR,
                error_message=str(e),
                frame_number=frame_number,
                image_width=width,
                image_height=height,
                processing_time_ms=(time.perf_counter() - start_time) * 1000,
            )
    
    def _detect_persons(
        self,
        frame: np.ndarray,
    ) -> List[Tuple[int, BoundingBox, float]]:
        """
        Detect persons in the frame.
        
        Returns:
            List of tuples: (track_id, bbox, confidence)
        """
        detector = self._get_detector()
        result = detector.track_people(frame)
        
        detections = []
        
        if result.boxes is None or len(result.boxes) == 0:
            print("[FRAME_PROC] YOLO detected: 0 persons")
            return detections
        
        print(f"[FRAME_PROC] YOLO detected: {len(result.boxes)} persons")
        
        for box in result.boxes:
            # Get confidence
            confidence = box.conf.item() if hasattr(box, 'conf') else 0.0
            
            # Skip low confidence detections
            if confidence < self._confidence_threshold:
                continue
            
            # Get track ID (from ByteTrack)
            track_id = -1
            if hasattr(box, 'id') and box.id is not None:
                track_id = int(box.id.item())
            
            # Get bounding box
            x1, y1, x2, y2 = map(int, box.xyxy[0])
            bbox = BoundingBox.from_xyxy(x1, y1, x2, y2)
            
            detections.append((track_id, bbox, confidence))
        
        return detections
    
    def _process_person(
        self,
        frame: np.ndarray,
        track_id: int,
        bbox: BoundingBox,
        confidence: float,
        frame_number: int,
    ) -> PersonDetection:
        """
        Process a single detected person.
        
        Performs:
        - Crop person region
        - Classify clothing items
        - Analyze colors
        - Extract embedding (if enabled)
        """
        # Crop person region
        x1, y1, x2, y2 = bbox.to_xyxy()
        
        # Ensure bounds
        x1 = max(0, x1)
        y1 = max(0, y1)
        x2 = min(frame.shape[1], x2)
        y2 = min(frame.shape[0], y2)
        
        person_crop = frame[y1:y2, x1:x2]
        
        # Initialize person detection
        person = PersonDetection(
            track_id=track_id,
            bbox=bbox,
            confidence=confidence,
            frame_number=frame_number,
        )
        
        # Extract embedding (if enabled)
        if self.enable_embedding:
            try:
                embedding, cloth_names = self._get_embedder().get_embedding(person_crop)
                person.embedding = embedding
            except Exception as e:
                # Embedding failure is not fatal
                pass
        
        # Classify clothing (if enabled)
        if self.enable_classification and person_crop.size > 0:
            items = self._classify_clothing(person_crop)
            person.items = items
        
        return person
    
    def _select_items_by_rules(
        self,
        predictions: List[tuple]
    ) -> List[DetectedItem]:
        """
        Select up to 2 clothing items based on category rules.
        
        Rules:
        - Max 1 TOP item (long_sleeve, short_sleeve)
        - Max 1 BOTTOM item (everything else)
        - Dress exception: if dress is in top-2, pair it with highest conf non-dress item
        
        Args:
            predictions: List of (class_name, confidence, bbox) tuples, sorted by confidence desc
        
        Returns:
            List of DetectedItem objects (max 2 items)
        """
        selected = []
        has_top = False
        has_bottom = False
        
        # TOP item keywords
        top_keywords = ["long_sleeve", "short_sleeve"]
        
        for idx, pred in enumerate(predictions[:3]):  # Check top-3 for better matching
            if len(pred) < 2:
                continue
                
            class_name = pred[0]
            conf = pred[1] if len(pred) > 1 else 0.0
            bbox = pred[2] if len(pred) > 2 else None
            
            # Skip unknown predictions
            if class_name == "Unknown":
                continue
            
            # Determine category
            is_top = class_name in top_keywords
            category = ClothingCategory.TOP if is_top else ClothingCategory.BOTTOM
            
            if class_name == "Dress":
                # Dress can pair with anything, add it as BOTTOM
                item = DetectedItem(
                    class_name=class_name,
                    category=ClothingCategory.FULL_BODY,
                    confidence=conf,
                )
                if bbox is not None:
                    item.relative_bbox = BoundingBox.from_xyxy(*bbox)
                selected.append(item)
                has_bottom = True
            elif is_top and not has_top:
                item = DetectedItem(
                    class_name=class_name,
                    category=ClothingCategory.TOP,
                    confidence=conf,
                )
                if bbox is not None:
                    item.relative_bbox = BoundingBox.from_xyxy(*bbox)
                selected.append(item)
                has_top = True
            elif not is_top and not has_bottom:
                item = DetectedItem(
                    class_name=class_name,
                    category=ClothingCategory.BOTTOM,
                    confidence=conf,
                )
                if bbox is not None:
                    item.relative_bbox = BoundingBox.from_xyxy(*bbox)
                selected.append(item)
                has_bottom = True
            
            # Stop when we have 2 items
            if len(selected) >= 2:
                break
        
        selected_items_log = [{"class": s.class_name, "category": s.category.value} for s in selected]
        print(f"[FRAME_PROC] select_items_by_rules applied")
        print(f"[FRAME_PROC] Selected items: {selected_items_log}")
        
        return selected[:2]  # Max 2 items

    def _classify_clothing(
        self,
        person_crop: np.ndarray,
    ) -> List[DetectedItem]:
        """
        Classify clothing items in the person crop.
        
        Returns:
            List of DetectedItem objects (max 2 items based on rules)
        """
        classifier = self._get_classifier()
        
        try:
            # Get top-N predictions (get more to apply rules)
            if isinstance(self.classifier_top_n, str) and self.classifier_top_n.lower() == "all":
                predictions = classifier.predict_top_n(person_crop, top_n=5)
            elif isinstance(self.classifier_top_n, int):
                # Get at least 3 to apply selection rules
                predictions = classifier.predict_top_n(person_crop, top_n=max(3, self.classifier_top_n))
            else:
                predictions = classifier.predict_top_n(person_crop, top_n=3)
            
            # Apply selection rules (1 TOP + 1 BOTTOM max)
            selected_items = self._select_items_by_rules(predictions)
            
            # Analyze colors for selected items
            if self.enable_color_analysis:
                for item in selected_items:
                    bbox = item.relative_bbox.to_xyxy() if item.relative_bbox else None
                    item = self._analyze_item_color(item, person_crop, bbox)
                    # Log color analysis result
                    color_str = item.primary_color.color_name if item.primary_color else (item.color_groups[0] if item.color_groups else "Unknown")
                    print(f"[FRAME_PROC] Color analysis for {item.class_name}: primary_color={color_str}, color_groups={item.color_groups}")

            return selected_items
        
        except Exception as e:
            # Classification failure - return empty list
            print(f"[FrameProcessor] Classification error: {e}")
            return []
    
    def _infer_category(self, class_name: str) -> ClothingCategory:
        """
        Infer clothing category from class name.
        
        This is a simple heuristic based on common class names.
        """
        class_lower = class_name.lower()
        
        # Bottom items
        bottom_keywords = ['pants', 'shorts', 'skirt', 'jeans', 'trousers', 'leggings']
        if any(kw in class_lower for kw in bottom_keywords):
            return ClothingCategory.BOTTOM
        
        # Full body items
        full_body_keywords = ['dress', 'suit', 'jumpsuit', 'overalls', 'coat_long']
        if any(kw in class_lower for kw in full_body_keywords):
            return ClothingCategory.FULL_BODY
        
        # Accessories
        accessory_keywords = ['hat', 'cap', 'scarf', 'tie', 'belt', 'bag', 'glasses']
        if any(kw in class_lower for kw in accessory_keywords):
            return ClothingCategory.ACCESSORY
        
        # Default to TOP (shirts, jackets, etc.)
        return ClothingCategory.TOP
    
    def _analyze_item_color(
        self,
        item: DetectedItem,
        person_crop: np.ndarray,
        item_bbox: Optional[Tuple[int, int, int, int]],
    ) -> DetectedItem:
        """
        Analyze colors for a clothing item.
        
        Args:
            item: The detected item to analyze
            person_crop: Full person crop
            item_bbox: Optional bbox of the item within person_crop
        
        Returns:
            Updated DetectedItem with color information
        """
        try:
            # Import color analysis functions
            from ai.color_system import analyze_detailed_colors, get_color_groups, get_color_categories

            # Get crop for this item
            if item_bbox is not None:
                x1, y1, x2, y2 = item_bbox
                x1 = max(0, x1)
                y1 = max(0, y1)
                x2 = min(person_crop.shape[1], x2)
                y2 = min(person_crop.shape[0], y2)
                item_crop = person_crop[y1:y2, x1:x2]
            else:
                item_crop = person_crop

            if item_crop.size == 0:
                return item

            # Analyze detailed colors
            detailed_colors_dict = analyze_detailed_colors(item_crop)

            # Convert dict to list format expected by code
            detailed_colors = [
                {"color_name": k, "percentage": v}
                for k, v in sorted(detailed_colors_dict.items(), key=lambda x: x[1], reverse=True)
            ]
            item.detailed_colors = detailed_colors_dict

            # Get color groups
            color_groups = get_color_groups(detailed_colors_dict)
            item.color_groups = list(color_groups.keys())

            # Get color categories (brightness, vibrancy, temperature, clothing)
            color_categories = get_color_categories(detailed_colors_dict)
            item.color_categories = color_categories

            # Set primary color (highest percentage)
            if detailed_colors:
                primary = detailed_colors[0]
                item.primary_color = ColorData(
                    color_name=primary['color_name'],
                    percentage=primary['percentage'],
                    rgb=None,
                )

            # Set secondary colors
            if len(detailed_colors) > 1:
                for color_info in detailed_colors[1:]:
                    item.secondary_colors.append(ColorData(
                        color_name=color_info['color_name'],
                        percentage=color_info['percentage'],
                        rgb=None,
                    ))

        except Exception as e:
            # Color analysis failure is not fatal
            print(f"[FRAME_PROC] Color analysis error: {e}")
            import traceback
            traceback.print_exc()

        return item
    
    def process_image(
        self,
        image: np.ndarray,
    ) -> AIProcessingResult:
        """
        Process a single image (convenience method).
        
        This is an alias for process_frame with frame_number=0.
        
        Args:
            image: Input image (BGR format)
        
        Returns:
            AIProcessingResult
        """
        print("[FRAME_PROC] process_image() called")
        result = self.process_frame(image, frame_number=0, timestamp=time.time())
        print(f"[FRAME_PROC] process_image() complete - persons: {result.num_persons}, status: {result.status}")
        return result


# ==============================================================================
# Convenience Functions
# ==============================================================================

def process_frame_sync(
    frame: np.ndarray,
    frame_number: int = 0,
    enable_classification: bool = True,
    enable_color_analysis: bool = True,
    classifier_top_n: int = 1,
) -> AIProcessingResult:
    """
    Convenience function for one-off frame processing.
    
    Creates a FrameProcessor, processes the frame, and returns the result.
    Useful for simple use cases where you don't need to reuse the processor.
    
    Args:
        frame: Input frame/image
        frame_number: Frame number
        enable_classification: Enable clothing classification
        enable_color_analysis: Enable color analysis
        classifier_top_n: Number of top predictions
    
    Returns:
        AIProcessingResult
    """
    processor = FrameProcessor(
        enable_classification=enable_classification,
        enable_color_analysis=enable_color_analysis,
        classifier_top_n=classifier_top_n,
    )
    return processor.process_frame(frame, frame_number)


def process_image_sync(
    image: np.ndarray,
    enable_classification: bool = True,
    enable_color_analysis: bool = True,
    classifier_top_n: int = 1,
) -> AIProcessingResult:
    """
    Convenience function for one-off image processing.
    
    Args:
        image: Input image
        enable_classification: Enable clothing classification
        enable_color_analysis: Enable color analysis
        classifier_top_n: Number of top predictions
    
    Returns:
        AIProcessingResult
    """
    return process_frame_sync(
        image,
        frame_number=0,
        enable_classification=enable_classification,
        enable_color_analysis=enable_color_analysis,
        classifier_top_n=classifier_top_n,
    )
