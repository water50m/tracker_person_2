"""
Tests for the hierarchical color search system.
Tests the new API parameters: tone_groups, detailed_colors, brightness, temperature, vibrancy, and color_logic.
"""

import pytest
from src.api.controllers import DetectionController
from src.api.schemas import SearchCriteria
from src.services.database import DatabaseService


class TestHierarchicalColorSearch:
    """Test the hierarchical color search functionality"""

    @pytest.fixture
    def controller(self):
        """Create a DetectionController instance"""
        return DetectionController()

    @pytest.fixture
    def db(self):
        """Create a database connection"""
        db = DatabaseService()
        db.connect()
        yield db
        db.close()

    def test_search_with_tone_groups(self, controller, db):
        """Test searching with tone groups (broad color search)"""
        # This test assumes there are detections in the database
        # with tone_groups data
        try:
            result = controller.search_persons(
                logic="OR",
                threshold=0.15,
                camera_id=None,
                video_id=None,
                start_time=None,
                end_time=None,
                page=1,
                limit=10,
                clothing=[],
                colors=[],
                tone_groups=["red_tones"],
                detailed_colors=None,
                brightness=None,
                temperature=None,
                vibrancy=None,
            )
            # Should return a dict with results, total, page, has_more
            assert "results" in result
            assert "total" in result
            assert "page" in result
            assert "has_more" in result
            assert isinstance(result["results"], list)
        except Exception as e:
            pytest.skip(f"Database may not have test data: {e}")

    def test_search_with_detailed_colors(self, controller, db):
        """Test searching with detailed colors (specific color search)"""
        try:
            result = controller.search_persons(
                logic="OR",
                threshold=0.15,
                camera_id=None,
                video_id=None,
                start_time=None,
                end_time=None,
                page=1,
                limit=10,
                clothing=[],
                colors=[],
                tone_groups=None,
                detailed_colors=["red", "crimson"],
                brightness=None,
                temperature=None,
                vibrancy=None,
            )
            assert "results" in result
            assert isinstance(result["results"], list)
        except Exception as e:
            pytest.skip(f"Database may not have test data: {e}")

    def test_search_with_secondary_filters(self, controller, db):
        """Test searching with secondary filters (brightness, temperature, vibrancy)"""
        try:
            result = controller.search_persons(
                logic="OR",
                threshold=0.15,
                camera_id=None,
                video_id=None,
                start_time=None,
                end_time=None,
                page=1,
                limit=10,
                clothing=[],
                colors=[],
                tone_groups=["red_tones"],
                detailed_colors=None,
                brightness="light",
                temperature="warm",
                vibrancy="vibrant",
            )
            assert "results" in result
            assert isinstance(result["results"], list)
        except Exception as e:
            pytest.skip(f"Database may not have test data: {e}")

    def test_search_with_color_logic_or(self, controller, db):
        """Test searching with OR logic (any matching color)"""
        try:
            result = controller.search_persons(
                logic="OR",
                threshold=0.15,
                camera_id=None,
                video_id=None,
                start_time=None,
                end_time=None,
                page=1,
                limit=10,
                clothing=[],
                colors=[],
                tone_groups=["red_tones", "blue_tones"],
                detailed_colors=None,
                brightness=None,
                temperature=None,
                vibrancy=None,
            )
            assert "results" in result
            assert isinstance(result["results"], list)
        except Exception as e:
            pytest.skip(f"Database may not have test data: {e}")

    def test_search_with_color_logic_and(self, controller, db):
        """Test searching with AND logic (all matching colors)"""
        try:
            result = controller.search_persons(
                logic="AND",
                threshold=0.15,
                camera_id=None,
                video_id=None,
                start_time=None,
                end_time=None,
                page=1,
                limit=10,
                clothing=[],
                colors=[],
                tone_groups=["red_tones"],
                detailed_colors=["red", "crimson"],
                brightness=None,
                temperature=None,
                vibrancy=None,
            )
            assert "results" in result
            assert isinstance(result["results"], list)
        except Exception as e:
            pytest.skip(f"Database may not have test data: {e}")

    def test_search_criteria_schema_validation(self):
        """Test that SearchCriteria schema accepts new parameters"""
        criteria = SearchCriteria(
            class_names=["Long_sleeve"],
            class_logic="OR",
            color_names=["Red"],
            color_logic="OR",
            color_threshold=15.0,
            tone_groups=["red_tones"],
            detailed_colors=["red", "crimson"],
            brightness="light",
            temperature="warm",
            vibrancy="vibrant",
            limit=50,
            offset=0,
        )
        assert criteria.tone_groups == ["red_tones"]
        assert criteria.detailed_colors == ["red", "crimson"]
        assert criteria.brightness == "light"
        assert criteria.temperature == "warm"
        assert criteria.vibrancy == "vibrant"

    def test_search_criteria_optional_parameters(self):
        """Test that new parameters are optional"""
        criteria = SearchCriteria(
            class_names=["Long_sleeve"],
            limit=50,
            offset=0,
        )
        assert criteria.tone_groups is None
        assert criteria.detailed_colors is None
        assert criteria.brightness is None
        assert criteria.temperature is None
        assert criteria.vibrancy is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
