"""
image_analyzer.py - Image Analysis API for Search Auto-fill

This module provides the ImageAnalyzer class which analyzes a single image
and returns clothing class and color information for search auto-fill.

It uses the ThreadPoolProcessor internally for consistent processing
and is designed to be a drop-in replacement for the existing
analyze_image_for_search method in controllers.py.

Usage:
    from services.image_analyzer import ImageAnalyzer
    
    analyzer = ImageAnalyzer()
    result = analyzer.analyze(image_bytes)
    
    # result is compatible with existing API:
    # {
    #     "status": "success",
    #     "detected_attributes": {
    #         "class_name": "Short_Sleeve_Shirt",
    #         "color_name": "Red"
    #     }
    # }
"""
import asyncio
import time
import sys
from pathlib import Path
from typing import Optional, List, Dict, Any, Union
import io

import numpy as np
import cv2

# Add parent directory for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from services.ai_processing_types import (
    AIProcessingResult,
    ImageAnalysisResult,
    ProcessingStatus,
    DetectedItem,
)
from services.frame_processor import FrameProcessor
from services.thread_pool_processor import ThreadPoolProcessor


class ImageAnalyzer:
    """
    Image analysis API for search auto-fill.
    
    This class provides a synchronous interface for analyzing images
    to extract clothing attributes. It uses ThreadPoolProcessor internally
    to maintain consistency with the video processing pipeline.
    
    The API response format is compatible with the existing
    analyze_image_for_search method in controllers.py.
    """
    
    def __init__(
        self,
        thread_pool: Optional[ThreadPoolProcessor] = None,
        enable_color_analysis: bool = True,
        classifier_top_n: int = 1,
        timeout: float = 10.0,
    ):
        """
        Initialize the ImageAnalyzer.
        
        Args:
            thread_pool: Optional ThreadPoolProcessor to use (creates new if None)
            enable_color_analysis: Whether to analyze colors
            classifier_top_n: Number of top predictions to consider
            timeout: Timeout for processing (seconds)
        """
        self.enable_color_analysis = enable_color_analysis
        self.classifier_top_n = classifier_top_n
        self.timeout = timeout
        
        # Use provided thread pool or create frame processor directly
        self._thread_pool = thread_pool
        self._owns_thread_pool = thread_pool is None
        
        if thread_pool is None:
            # Create frame processor for direct sync processing
            self._frame_processor = FrameProcessor(
                enable_classification=True,
                enable_color_analysis=enable_color_analysis,
                enable_embedding=False,  # Not needed for image analysis
                classifier_top_n=classifier_top_n,
            )
        else:
            self._frame_processor = None
    
    def analyze(self, image_bytes: bytes) -> Dict[str, Any]:
        """
        Analyze an image and return clothing attributes.

        This is the main entry point and is compatible with the
        existing analyze_image_for_search API.

        Args:
            image_bytes: Raw image bytes (JPEG, PNG, etc.)

        Returns:
            Dictionary with status and detected_attributes
            {
                "status": "success" | "error",
                "detected_attributes": {
                    "class_name": str,
                    "color_name": str
                },
                "message": str (if error)
            }
        """
        print(f"[ANALYZER] analyze() called, enable_color_analysis={self.enable_color_analysis}")

        try:
            # Decode image
            image = self._decode_image(image_bytes)
            if image is None:
                print("[ANALYZER] ERROR: Could not decode image")
                return self._error_response("Could not decode image")

            h, w = image.shape[:2]
            print(f"[ANALYZER] Image decoded: {w}x{h}")

            # Process image
            if self._thread_pool is not None:
                print("[ANALYZER] Using thread pool for processing")
                result = self._analyze_with_thread_pool(image)
            else:
                print("[ANALYZER] Using frame processor directly (sync)")
                result = self._analyze_sync(image)

            print(f"[ANALYZER] Processing complete, status: {result.status}")

            # Convert to API response
            response = self._to_api_response(result)
            print(f"[ANALYZER] Response: {response}")
            return response

        except Exception as e:
            print(f"[ANALYZER] ERROR during analysis: {e}")
            import traceback
            traceback.print_exc()
            return self._error_response(str(e))
    
    def _decode_image(self, image_bytes: bytes) -> Optional[np.ndarray]:
        """
        Decode image bytes to OpenCV image.
        
        Args:
            image_bytes: Raw image bytes
        
        Returns:
            OpenCV image (BGR format) or None if decoding fails
        """
        try:
            nparr = np.frombuffer(image_bytes, np.uint8)
            img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
            return img
        except Exception:
            return None
    
    def _analyze_sync(self, image: np.ndarray) -> AIProcessingResult:
        """
        Analyze image synchronously using FrameProcessor.
        
        Args:
            image: OpenCV image
        
        Returns:
            AIProcessingResult
        """
        return self._frame_processor.process_image(image)
    
    def _analyze_with_thread_pool(self, image: np.ndarray) -> AIProcessingResult:
        """
        Analyze image using ThreadPoolProcessor.
        
        This runs the async thread pool in a sync context using asyncio.run().
        
        Args:
            image: OpenCV image
        
        Returns:
            AIProcessingResult
        """
        try:
            # Use asyncio.run to execute async code in sync context
            result = asyncio.run(
                self._async_analyze(image)
            )
            return result
        except Exception as e:
            return AIProcessingResult(
                status=ProcessingStatus.ERROR,
                error_message=str(e),
            )
    
    async def _async_analyze(self, image: np.ndarray) -> AIProcessingResult:
        """
        Async version of analyze using ThreadPoolProcessor.
        
        Args:
            image: OpenCV image
        
        Returns:
            AIProcessingResult
        """
        # Ensure thread pool is initialized
        if not self._thread_pool.is_initialized():
            await self._thread_pool.initialize()
        
        # Process image
        result = await self._thread_pool.process_image(
            image,
            timeout=self.timeout,
        )
        
        return result
    
    def _to_api_response(self, result: AIProcessingResult) -> Dict[str, Any]:
        """
        Convert AIProcessingResult to API response format.
        
        Args:
            result: AIProcessingResult from processing
        
        Returns:
            API response dictionary
        """
        if result.status == ProcessingStatus.ERROR:
            return self._error_response(result.error_message or "Unknown error")
        
        if result.status == ProcessingStatus.TIMEOUT:
            return self._error_response("Processing timed out")
        
        # Extract primary detection (first person's first item)
        class_name = None
        color_name = None
        category = None
        confidence = 0.0
        all_items = []
        
        if result.detections:
            # Get first person
            person = result.detections[0]
            
            if person.items:
                # Get first item
                item = person.items[0]
                class_name = item.class_name
                category = item.category.value if item.category else None
                confidence = item.confidence
                
                # Get color
                if item.primary_color:
                    color_name = item.primary_color.color_name
                elif item.color_groups:
                    color_name = item.color_groups[0]
                
                # Collect all items for extended response
                all_items = [
                    {
                        "class_name": i.class_name,
                        "category": i.category.value if i.category else None,
                        "confidence": i.confidence,
                        "color": i.primary_color.color_name if i.primary_color else None,
                        "detailed_colors": i.detailed_colors if i.detailed_colors else {},
                        "color_categories": i.color_categories if i.color_categories else {},
                    }
                    for i in person.items
                ]
        
        # If no detections
        if class_name is None:
            print("[ANALYZER] No clothing items detected")
            return self._error_response("No clothing items detected")

        # Log detection results
        print(f"[ANALYZER] Person detection count: {result.num_persons}")
        if result.detections:
            person = result.detections[0]
            print(f"[ANALYZER] Person 0 items: {len(person.items)}")
            for idx, item in enumerate(person.items):
                color_str = item.primary_color.color_name if item.primary_color else (item.color_groups[0] if item.color_groups else "Unknown")
                print(f"[ANALYZER]   Item {idx}: {item.class_name} ({item.category.value if item.category else 'Unknown'}) - color: {color_str}")

        # Build response
        response = {
            "status": "success",
            "detected_attributes": {
                "class_name": class_name,
                "color_name": color_name or "Unknown",
            },
        }

        # Add extended fields
        if category:
            response["detected_attributes"]["category"] = category
        if confidence > 0:
            response["detected_attributes"]["confidence"] = round(confidence, 3)

        # Add metadata
        response["processing_time_ms"] = round(result.processing_time_ms, 2)
        response["num_persons_detected"] = result.num_persons

        # Add all items (for detailed view)
        if len(all_items) > 1:
            response["all_items"] = all_items
            print(f"[ANALYZER] Building response, all_items count: {len(all_items)}")

        return response
    
    def _error_response(self, message: str) -> Dict[str, Any]:
        """
        Create error response.
        
        Args:
            message: Error message
        
        Returns:
            Error response dictionary
        """
        return {
            "status": "error",
            "message": message,
        }
    
    def close(self):
        """
        Clean up resources.
        
        Call this when done using the analyzer.
        """
        if self._owns_thread_pool and self._thread_pool is not None:
            # Shutdown the thread pool we created
            try:
                asyncio.run(self._thread_pool.shutdown())
            except Exception:
                pass
    
    def __enter__(self):
        """Context manager entry."""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()
        return False
    
    def __del__(self):
        """Destructor."""
        try:
            self.close()
        except:
            pass


# ==============================================================================
# Convenience Functions
# ==============================================================================

def analyze_image(
    image_bytes: bytes,
    enable_color_analysis: bool = True,
    classifier_top_n: int = 1,
    timeout: float = 10.0,
) -> Dict[str, Any]:
    """
    Convenience function for one-off image analysis.
    
    Creates an ImageAnalyzer, processes the image, and returns the result.
    
    Args:
        image_bytes: Raw image bytes
        enable_color_analysis: Whether to analyze colors
        classifier_top_n: Number of top predictions
        timeout: Processing timeout
    
    Returns:
        API response dictionary
    """
    analyzer = ImageAnalyzer(
        enable_color_analysis=enable_color_analysis,
        classifier_top_n=classifier_top_n,
        timeout=timeout,
    )
    
    try:
        result = analyzer.analyze(image_bytes)
        return result
    finally:
        analyzer.close()
