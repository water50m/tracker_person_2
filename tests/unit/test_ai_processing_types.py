"""
Tests for ai_processing_types.py
TDD: Write tests before implementing dependent modules

Run with:
    uv run python -m pytest tests/unit/test_ai_processing_types.py -v
"""
import pytest
import numpy as np
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

from services.ai_processing_types import (
    BoundingBox,
    ColorData,
    DetectedItem,
    PersonDetection,
    AIProcessingResult,
    VideoProcessingStats,
    ImageAnalysisResult,
    ClothingCategory,
    ProcessingStatus,
)


class TestBoundingBox:
    """Test BoundingBox dataclass"""
    
    def test_create_basic(self):
        """Test: สร้าง BoundingBox ด้วยค่าพื้นฐาน"""
        bbox = BoundingBox(x=10, y=20, width=100, height=50)
        
        assert bbox.x == 10
        assert bbox.y == 20
        assert bbox.width == 100
        assert bbox.height == 50
    
    def test_x2_property(self):
        """Test: x2 property ต้องคำนวณถูกต้อง"""
        bbox = BoundingBox(x=10, y=20, width=100, height=50)
        
        assert bbox.x2 == 110  # 10 + 100
        assert bbox.y2 == 70   # 20 + 50
    
    def test_center_property(self):
        """Test: center property ต้องคำนวณถูกต้อง"""
        bbox = BoundingBox(x=10, y=20, width=100, height=50)
        
        center = bbox.center
        assert center == (60, 45)  # (10+50, 20+25)
    
    def test_to_xyxy(self):
        """Test: to_xyxy() ต้อง return (x1, y1, x2, y2)"""
        bbox = BoundingBox(x=10, y=20, width=100, height=50)
        
        xyxy = bbox.to_xyxy()
        assert xyxy == (10, 20, 110, 70)
    
    def test_from_xyxy(self):
        """Test: from_xyxy() ต้องสร้าง BoundingBox ถูกต้อง"""
        bbox = BoundingBox.from_xyxy(10, 20, 110, 70)
        
        assert bbox.x == 10
        assert bbox.y == 20
        assert bbox.width == 100
        assert bbox.height == 50


class TestColorData:
    """Test ColorData dataclass"""
    
    def test_create_basic(self):
        """Test: สร้าง ColorData ด้วยค่าพื้นฐาน"""
        color = ColorData(
            color_name="Red",
            hex_value="#FF0000",
            confidence=0.95,
            percentage=80.0,
        )
        
        assert color.color_name == "Red"
        assert color.hex_value == "#FF0000"
        assert color.confidence == 0.95
        assert color.percentage == 80.0
    
    def test_to_dict(self):
        """Test: to_dict() ต้อง return dict ที่ถูกต้อง"""
        color = ColorData(
            color_name="Blue",
            hex_value="#0000FF",
            confidence=0.88,
            rgb=(0, 0, 255),
        )
        
        d = color.to_dict()
        
        assert d["color_name"] == "Blue"
        assert d["hex_value"] == "#0000FF"
        assert d["confidence"] == 0.88
        assert d["rgb"] == (0, 0, 255)
    
    def test_default_values(self):
        """Test: ค่า default ต้องถูกต้อง"""
        color = ColorData(color_name="Green")
        
        assert color.hex_value is None
        assert color.confidence == 0.0
        assert color.percentage == 0.0
        assert color.rgb is None


class TestDetectedItem:
    """Test DetectedItem dataclass"""
    
    def test_create_basic(self):
        """Test: สร้าง DetectedItem ด้วยค่าพื้นฐาน"""
        item = DetectedItem(
            class_name="Short_Sleeve_Shirt",
            category=ClothingCategory.TOP,
            confidence=0.92,
        )
        
        assert item.class_name == "Short_Sleeve_Shirt"
        assert item.category == ClothingCategory.TOP
        assert item.confidence == 0.92
    
    def test_with_colors(self):
        """Test: DetectedItem กับ ColorData"""
        primary = ColorData(color_name="Red", confidence=0.95)
        secondary = [
            ColorData(color_name="White", confidence=0.70),
        ]
        
        item = DetectedItem(
            class_name="T_Shirt",
            primary_color=primary,
            secondary_colors=secondary,
        )
        
        assert item.primary_color.color_name == "Red"
        assert len(item.secondary_colors) == 1
        assert item.secondary_colors[0].color_name == "White"
    
    def test_to_dict(self):
        """Test: to_dict() ต้อง return dict ที่ถูกต้อง"""
        bbox = BoundingBox(x=0, y=0, width=50, height=60)
        item = DetectedItem(
            class_name="Long_Pants",
            category=ClothingCategory.BOTTOM,
            confidence=0.88,
            relative_bbox=bbox,
        )
        
        d = item.to_dict()
        
        assert d["class_name"] == "Long_Pants"
        assert d["category"] == "BOTTOM"
        assert d["relative_bbox"]["width"] == 50
        assert d["relative_bbox"]["height"] == 60


class TestPersonDetection:
    """Test PersonDetection dataclass"""
    
    def test_create_basic(self):
        """Test: สร้าง PersonDetection ด้วยค่าพื้นฐาน"""
        bbox = BoundingBox(x=100, y=200, width=80, height=160)
        
        person = PersonDetection(
            track_id=42,
            persistent_id=12345,
            bbox=bbox,
            confidence=0.95,
        )
        
        assert person.track_id == 42
        assert person.persistent_id == 12345
        assert person.confidence == 0.95
    
    def test_with_items(self):
        """Test: PersonDetection กับ clothing items"""
        item1 = DetectedItem(class_name="Shirt", category=ClothingCategory.TOP)
        item2 = DetectedItem(class_name="Pants", category=ClothingCategory.BOTTOM)
        
        person = PersonDetection(
            track_id=1,
            items=[item1, item2],
        )
        
        assert len(person.items) == 2
        assert person.items[0].class_name == "Shirt"
        assert person.items[1].class_name == "Pants"
    
    def test_with_embedding(self):
        """Test: PersonDetection กับ embedding vector"""
        embedding = np.array([0.1, 0.2, 0.3, 0.4])
        
        person = PersonDetection(
            track_id=1,
            embedding=embedding,
        )
        
        assert np.array_equal(person.embedding, embedding)
    
    def test_to_dict(self):
        """Test: to_dict() ต้อง return dict ที่ถูกต้อง"""
        bbox = BoundingBox(x=100, y=200, width=80, height=160)
        item = DetectedItem(class_name="Jacket", category=ClothingCategory.TOP)
        
        person = PersonDetection(
            track_id=5,
            persistent_id=100,
            bbox=bbox,
            confidence=0.90,
            items=[item],
            frame_number=42,
        )
        
        d = person.to_dict()
        
        assert d["track_id"] == 5
        assert d["persistent_id"] == 100
        assert d["bbox"]["x"] == 100
        assert d["bbox"]["width"] == 80
        assert len(d["items"]) == 1
        assert d["frame_number"] == 42


class TestAIProcessingResult:
    """Test AIProcessingResult dataclass"""
    
    def test_create_success(self):
        """Test: สร้าง AIProcessingResult แบบสำเร็จ"""
        bbox = BoundingBox(x=100, y=200, width=80, height=160)
        person = PersonDetection(track_id=1, bbox=bbox)
        
        result = AIProcessingResult(
            status=ProcessingStatus.SUCCESS,
            detections=[person],
            frame_number=10,
            processing_time_ms=45.5,
            image_width=1920,
            image_height=1080,
        )
        
        assert result.status == ProcessingStatus.SUCCESS
        assert len(result.detections) == 1
        assert result.frame_number == 10
        assert result.processing_time_ms == 45.5
    
    def test_create_error(self):
        """Test: สร้าง AIProcessingResult แบบ error"""
        result = AIProcessingResult(
            status=ProcessingStatus.ERROR,
            error_message="Failed to load model",
        )
        
        assert result.status == ProcessingStatus.ERROR
        assert result.error_message == "Failed to load model"
    
    def test_create_no_detections(self):
        """Test: สร้าง AIProcessingResult ไม่มี detections"""
        result = AIProcessingResult(
            status=ProcessingStatus.NO_DETECTIONS,
            detections=[],
        )
        
        assert result.status == ProcessingStatus.NO_DETECTIONS
        assert len(result.detections) == 0
        assert result.num_persons == 0
    
    def test_to_dict(self):
        """Test: to_dict() ต้อง return dict ที่ถูกต้อง"""
        person = PersonDetection(track_id=1)
        result = AIProcessingResult(
            status=ProcessingStatus.SUCCESS,
            detections=[person],
            frame_number=5,
            processing_time_ms=33.3,
        )
        
        d = result.to_dict()
        
        assert d["status"] == "success"
        assert d["num_persons"] == 1
        assert d["frame_number"] == 5
        assert d["processing_time_ms"] == 33.3


class TestVideoProcessingStats:
    """Test VideoProcessingStats dataclass"""
    
    def test_create_basic(self):
        """Test: สร้าง VideoProcessingStats ด้วยค่าพื้นฐาน"""
        stats = VideoProcessingStats(
            total_frames=1800,
            processed_frames=60,
            skipped_frames=1740,
            total_detections=45,
            unique_persons=5,
        )
        
        assert stats.total_frames == 1800
        assert stats.processed_frames == 60
        assert stats.total_detections == 45
    
    def test_duration_seconds(self):
        """Test: duration_seconds property"""
        import time
        
        start = time.time()
        time.sleep(0.01)  # Small delay
        end = time.time()
        
        stats = VideoProcessingStats(
            start_time=start,
            end_time=end,
        )
        
        assert stats.duration_seconds > 0
        assert stats.duration_seconds < 1.0
    
    def test_fps(self):
        """Test: fps property"""
        stats = VideoProcessingStats(
            processed_frames=100,
            start_time=100.0,
            end_time=110.0,
        )
        
        assert stats.fps == 10.0  # 100 frames / 10 seconds
    
    def test_fps_zero_duration(self):
        """Test: fps ต้อง return 0 ถ้าไม่มี duration"""
        stats = VideoProcessingStats(
            processed_frames=100,
        )
        
        assert stats.fps == 0.0
    
    def test_to_dict(self):
        """Test: to_dict() ต้อง return dict ที่ถูกต้อง"""
        import time
        
        start = time.time()
        time.sleep(0.01)
        end = time.time()
        
        stats = VideoProcessingStats(
            total_frames=100,
            processed_frames=10,
            total_detections=5,
            start_time=start,
            end_time=end,
        )
        
        d = stats.to_dict()
        
        assert d["total_frames"] == 100
        assert d["processed_frames"] == 10
        assert d["duration_seconds"] > 0
        assert d["fps"] > 0


class TestImageAnalysisResult:
    """Test ImageAnalysisResult dataclass"""
    
    def test_create_success(self):
        """Test: สร้าง ImageAnalysisResult แบบสำเร็จ"""
        result = ImageAnalysisResult(
            status="success",
            class_name="Short_Sleeve_Shirt",
            color_name="Red",
            category="TOP",
            confidence=0.92,
            processing_time_ms=150.5,
            num_persons_detected=1,
        )
        
        assert result.status == "success"
        assert result.class_name == "Short_Sleeve_Shirt"
        assert result.color_name == "Red"
        assert result.confidence == 0.92
    
    def test_create_error(self):
        """Test: สร้าง ImageAnalysisResult แบบ error"""
        result = ImageAnalysisResult(
            status="error",
            message="Could not decode image",
        )
        
        assert result.status == "error"
        assert result.message == "Could not decode image"
    
    def test_to_api_response_success(self):
        """Test: to_api_response() สำหรับ success"""
        result = ImageAnalysisResult(
            status="success",
            class_name="T_Shirt",
            color_name="Blue",
            category="TOP",
            confidence=0.88,
            processing_time_ms=120.0,
        )
        
        response = result.to_api_response()
        
        assert response["status"] == "success"
        assert response["detected_attributes"]["class_name"] == "T_Shirt"
        assert response["detected_attributes"]["color_name"] == "Blue"
        assert response["detected_attributes"]["category"] == "TOP"
        assert response["detected_attributes"]["confidence"] == 0.88
        assert response["processing_time_ms"] == 120.0
    
    def test_to_api_response_error(self):
        """Test: to_api_response() สำหรับ error"""
        result = ImageAnalysisResult(
            status="error",
            message="Invalid image format",
        )
        
        response = result.to_api_response()
        
        assert response["status"] == "error"
        assert response["message"] == "Invalid image format"
        assert "detected_attributes" not in response


class TestEnums:
    """Test Enum classes"""
    
    def test_clothing_category_values(self):
        """Test: ClothingCategory enum values"""
        assert ClothingCategory.TOP.value == "TOP"
        assert ClothingCategory.BOTTOM.value == "BOTTOM"
        assert ClothingCategory.FULL_BODY.value == "FULL_BODY"
        assert ClothingCategory.ACCESSORY.value == "ACCESSORY"
        assert ClothingCategory.UNKNOWN.value == "UNKNOWN"
    
    def test_processing_status_values(self):
        """Test: ProcessingStatus enum values"""
        assert ProcessingStatus.SUCCESS.value == "success"
        assert ProcessingStatus.ERROR.value == "error"
        assert ProcessingStatus.NO_DETECTIONS.value == "no_detections"
        assert ProcessingStatus.SKIPPED.value == "skipped"
        assert ProcessingStatus.TIMEOUT.value == "timeout"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
