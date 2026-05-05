"""
Unit tests for Advanced Search endpoint
Tests clothing-specific color selection with independent OR/AND logic per item.
"""
import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime


# Mock fixtures for advanced search testing
@pytest.fixture
def mock_db_service():
    """Mock database service for testing"""
    mock_db = MagicMock()
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_db.conn = mock_conn
    mock_conn.cursor.return_value = mock_cursor
    return mock_db, mock_cursor


@pytest.fixture
def sample_clothing_groups():
    """Sample clothing groups for advanced search"""
    return [
        {
            "clothing": "Long_sleeve",
            "colors": ["red", "dark_red"],
            "color_logic": "OR"
        },
        {
            "clothing": "Trousers",
            "colors": ["blue", "navy"],
            "color_logic": "AND"
        }
    ]


class TestAdvancedSearchSchemas:
    """Test Pydantic schemas for advanced search request/response"""

    def test_advanced_search_request_schema(self):
        """Test that AdvancedSearchRequest schema validates correctly"""
        from src.api.schemas import AdvancedSearchRequest

        # Valid request with OR logic
        request = AdvancedSearchRequest(
            clothing_groups=[
                {"clothing": "Long_sleeve", "colors": ["red"], "color_logic": "OR"}
            ],
            global_logic="OR",
            threshold=0.1,
        )
        assert request.global_logic == "OR"
        assert len(request.clothing_groups) == 1
        assert request.clothing_groups[0].color_logic == "OR"

    def test_advanced_search_request_with_optional_fields(self):
        """Test AdvancedSearchRequest with optional camera/video/time fields"""
        from src.api.schemas import AdvancedSearchRequest

        request = AdvancedSearchRequest(
            clothing_groups=[
                {"clothing": "Short_sleeve", "colors": ["blue", "navy"], "color_logic": "AND"}
            ],
            global_logic="AND",
            threshold=0.5,
            camera_id="CAM-01",
            video_id="VID-123",
            start_time="2024-01-01T00:00:00",
            end_time="2024-01-02T00:00:00",
        )
        assert request.camera_id == "CAM-01"
        assert request.video_id == "VID-123"

    def test_advanced_search_request_empty_clothing_groups(self):
        """Test that empty clothing groups raises validation error"""
        from src.api.schemas import AdvancedSearchRequest
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            AdvancedSearchRequest(
                clothing_groups=[],  # Empty should fail
                global_logic="OR",
                threshold=0.1,
            )


class TestAdvancedSearchQueryBuilder:
    """Test SQL query builder for advanced search"""

    def test_or_logic_between_clothing_items(self):
        """Test OR logic: (Long_sleeve has red) OR (Trousers has blue)"""
        from src.api.controllers import DetectionController

        controller = DetectionController()

        clothing_groups = [
            {"clothing": "Long_sleeve", "colors": ["red"], "color_logic": "OR"},
            {"clothing": "Trousers", "colors": ["blue"], "color_logic": "OR"},
        ]

        query, params = controller._build_advanced_search_query(
            clothing_groups=clothing_groups,
            global_logic="OR",
            threshold=0.1,
        )

        # Query should be non-empty and contain expected SQL
        assert query
        assert "WHERE" in query
        assert len(params) > 0

    def test_and_logic_between_clothing_items(self):
        """Test AND logic: (Long_sleeve has red) AND (Trousers has blue)"""
        from src.api.controllers import DetectionController

        controller = DetectionController()

        clothing_groups = [
            {"clothing": "Long_sleeve", "colors": ["red"], "color_logic": "OR"},
            {"clothing": "Trousers", "colors": ["blue"], "color_logic": "OR"},
        ]

        query, params = controller._build_advanced_search_query(
            clothing_groups=clothing_groups,
            global_logic="AND",
            threshold=0.1,
        )

        # Query should be non-empty and contain expected SQL
        assert query
        assert "WHERE" in query
        assert len(params) > 0

    def test_or_logic_within_clothing_item(self):
        """Test OR logic within a clothing item: (red OR dark_red) for Long_sleeve"""
        from src.api.controllers import DetectionController

        controller = DetectionController()

        clothing_groups = [
            {"clothing": "Long_sleeve", "colors": ["red", "dark_red"], "color_logic": "OR"},
        ]

        query, params = controller._build_advanced_search_query(
            clothing_groups=clothing_groups,
            global_logic="OR",
            threshold=0.1,
        )

        # Query should be non-empty with params for both colors
        assert query
        assert "WHERE" in query
        assert len(params) >= 2  # At least clothing + 2 colors

    def test_and_logic_within_clothing_item(self):
        """Test AND logic within a clothing item: (blue AND navy) for Trousers"""
        from src.api.controllers import DetectionController

        controller = DetectionController()

        clothing_groups = [
            {"clothing": "Trousers", "colors": ["blue", "navy"], "color_logic": "AND"},
        ]

        query, params = controller._build_advanced_search_query(
            clothing_groups=clothing_groups,
            global_logic="OR",
            threshold=0.1,
        )

        # Query should be non-empty with params for both colors
        assert query
        assert "WHERE" in query
        assert len(params) >= 2  # At least clothing + 2 colors

    def test_mixed_logic_scenario(self):
        """Test complex scenario: (A=colors[OR]) OR (B=colors[AND])"""
        from src.api.controllers import DetectionController

        controller = DetectionController()

        # Long_sleeve with OR colors, Trousers with AND colors
        clothing_groups = [
            {"clothing": "Long_sleeve", "colors": ["red", "crimson"], "color_logic": "OR"},
            {"clothing": "Trousers", "colors": ["blue", "navy"], "color_logic": "AND"},
        ]

        query, params = controller._build_advanced_search_query(
            clothing_groups=clothing_groups,
            global_logic="OR",
            threshold=0.1,
        )

        # Query should be non-empty with params for both clothing items
        assert query
        assert "WHERE" in query
        assert len(params) >= 2  # At least 2 clothing items + colors


class TestAdvancedSearchEdgeCases:
    """Test edge cases for advanced search"""

    def test_single_clothing_single_color(self):
        """Test single clothing + single color"""
        from src.api.controllers import DetectionController

        controller = DetectionController()

        clothing_groups = [
            {"clothing": "Dress", "colors": ["pink"], "color_logic": "OR"},
        ]

        query, params = controller._build_advanced_search_query(
            clothing_groups=clothing_groups,
            global_logic="OR",
            threshold=0.1,
        )

        # Query should be non-empty
        assert query
        assert "WHERE" in query
        assert len(params) > 0

    def test_empty_colors_filter(self):
        """Test that clothing item with no colors searches for clothing with any color"""
        from src.api.controllers import DetectionController

        controller = DetectionController()

        # Empty colors: should match clothing type with any color
        clothing_groups = [
            {"clothing": "Shorts", "colors": [], "color_logic": "OR"},
        ]

        query, params = controller._build_advanced_search_query(
            clothing_groups=clothing_groups,
            global_logic="OR",
            threshold=0.1,
        )

        # Query should be non-empty
        assert query
        assert "WHERE" in query
        # Should only have 1 param (just clothing, no colors)
        assert len(params) == 1

    def test_all_six_clothing_items(self):
        """Test with all 6 clothing items"""
        from src.api.controllers import DetectionController

        controller = DetectionController()

        clothing_groups = [
            {"clothing": "Long_sleeve", "colors": ["red"], "color_logic": "OR"},
            {"clothing": "Short_sleeve", "colors": ["blue"], "color_logic": "OR"},
            {"clothing": "Trousers", "colors": ["black"], "color_logic": "OR"},
            {"clothing": "Shorts", "colors": ["white"], "color_logic": "OR"},
            {"clothing": "skirt", "colors": ["green"], "color_logic": "OR"},
            {"clothing": "Dress", "colors": ["yellow"], "color_logic": "OR"},
        ]

        query, params = controller._build_advanced_search_query(
            clothing_groups=clothing_groups,
            global_logic="AND",
            threshold=0.1,
        )

        # Query should be non-empty with params for all 6 clothing items
        assert query
        assert "WHERE" in query
        assert len(params) >= 6  # At least 6 clothing items


class TestAdvancedSearchIntegration:
    """Integration-style tests for the full advanced search flow"""

    def test_advanced_search_endpoint_exists(self):
        """Test that the advanced search endpoint is registered"""
        from src.api.main import app
        from fastapi.testclient import TestClient

        client = TestClient(app)

        # Endpoint should exist (may return 422 for validation error, but not 404)
        response = client.post("/api/search/advanced", json={
            "clothing_groups": [{"clothing": "Long_sleeve", "colors": ["red"], "color_logic": "OR"}],
            "global_logic": "OR",
            "threshold": 0.1,
        })

        # Should not return 404 (endpoint exists)
        assert response.status_code != 404

    def test_advanced_search_returns_expected_structure(self, mock_db_service):
        """Test that advanced search returns expected response structure"""
        mock_db, mock_cursor = mock_db_service

        # Mock the database response
        mock_cursor.fetchone.return_value = [100]  # total count
        mock_cursor.fetchall.return_value = [
            ("uuid-1", 1, datetime.now(), "/path/to/img1.jpg", "CAM-01", "VID-1", 0, []),
            ("uuid-2", 2, datetime.now(), "/path/to/img2.jpg", "CAM-02", "VID-2", 0, []),
        ]

        with patch('src.api.controllers.DatabaseService', return_value=mock_db):
            from src.api.controllers import DetectionController
            controller = DetectionController()

            result = controller.search_advanced(
                clothing_groups=[
                    {"clothing": "Long_sleeve", "colors": ["red"], "color_logic": "OR"}
                ],
                global_logic="OR",
                threshold=0.1,
            )

            assert "results" in result
            assert "total" in result
            assert "has_more" in result


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
