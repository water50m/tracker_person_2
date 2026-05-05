"""
Unit tests for detection_items schema refactor
Tests the FrameProcessor item selection rules and database methods
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import pytest
from src.services.frame_processor import FrameProcessor


def select_items_by_rules(predictions):
    processor = FrameProcessor.__new__(FrameProcessor)
    items = processor._select_items_by_rules(predictions)
    return [
        {
            "class_name": item.class_name,
            "category": item.category.value,
            "confidence": item.confidence,
            "bbox": list(item.relative_bbox.to_xyxy()) if item.relative_bbox else None,
            "item_index": index + 1,
        }
        for index, item in enumerate(items)
    ]


class TestSelectItemsByRules:
    """Test suite for FrameProcessor item selection rules."""

    def test_single_top_item(self):
        """Test selecting a single TOP item."""
        predictions = [
            ("long_sleeve", 0.95, [10, 10, 50, 100]),
        ]
        result = select_items_by_rules(predictions)
        
        assert len(result) == 1
        assert result[0]["class_name"] == "long_sleeve"
        assert result[0]["category"] == "TOP"
        assert result[0]["item_index"] == 1

    def test_single_bottom_item(self):
        """Test selecting a single BOTTOM item."""
        predictions = [
            ("skirt", 0.95, [10, 10, 50, 100]),
        ]
        result = select_items_by_rules(predictions)
        
        assert len(result) == 1
        assert result[0]["class_name"] == "skirt"
        assert result[0]["category"] == "BOTTOM"
        assert result[0]["item_index"] == 1

    def test_top_and_bottom_pair(self):
        """Test selecting one TOP and one BOTTOM item."""
        predictions = [
            ("long_sleeve", 0.95, [10, 10, 50, 100]),
            ("skirt", 0.85, [10, 100, 50, 200]),
        ]
        result = select_items_by_rules(predictions)
        
        assert len(result) == 2
        # Should have one TOP and one BOTTOM
        categories = [item["category"] for item in result]
        assert "TOP" in categories
        assert "BOTTOM" in categories

    def test_two_tops_selects_first(self):
        """Test that when two TOP items are predicted, only the first is selected."""
        predictions = [
            ("long_sleeve", 0.95, [10, 10, 50, 100]),
            ("short_sleeve", 0.85, [10, 10, 50, 100]),
        ]
        result = select_items_by_rules(predictions)
        
        # Should only select the first TOP (long_sleeve with higher confidence)
        assert len(result) == 1
        assert result[0]["class_name"] == "long_sleeve"

    def test_two_bottoms_selects_first(self):
        """Test that when two BOTTOM items are predicted, only the first is selected."""
        predictions = [
            ("skirt", 0.95, [10, 10, 50, 100]),
            ("pants", 0.85, [10, 10, 50, 100]),
        ]
        result = select_items_by_rules(predictions)
        
        # Should only select the first BOTTOM (skirt with higher confidence)
        assert len(result) == 1
        assert result[0]["class_name"] == "skirt"

    def test_empty_predictions(self):
        """Test handling of empty predictions."""
        result = select_items_by_rules([])
        assert result == []

    def test_item_index_assignment(self):
        """Test that item_index is correctly assigned."""
        predictions = [
            ("long_sleeve", 0.95, [10, 10, 50, 100]),
            ("skirt", 0.85, [10, 100, 50, 200]),
        ]
        result = select_items_by_rules(predictions)
        
        assert len(result) == 2
        # Item indices should be 1 and 2
        indices = [item["item_index"] for item in result]
        assert 1 in indices
        assert 2 in indices

    def test_confidence_preservation(self):
        """Test that confidence values are preserved."""
        predictions = [
            ("long_sleeve", 0.95, [10, 10, 50, 100]),
        ]
        result = select_items_by_rules(predictions)
        
        assert len(result) == 1
        assert result[0]["confidence"] == 0.95

    def test_bbox_preservation(self):
        """Test that bbox values are preserved."""
        bbox = [10, 20, 30, 40]
        predictions = [
            ("long_sleeve", 0.95, bbox),
        ]
        result = select_items_by_rules(predictions)
        
        assert len(result) == 1
        assert result[0]["bbox"] == bbox


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
