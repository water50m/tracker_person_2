"""Unit tests for StorageService.clear_bucket() and /api/video/clear endpoint with delete_img parameter."""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import pytest
from unittest.mock import Mock, patch, MagicMock

# Mock environment variables before importing
MOCK_ENV = {
    'MINIO_ENDPOINT': 'localhost:9000',
    'MINIO_ACCESS_KEY': 'test',
    'MINIO_SECRET_KEY': 'test',
    'MINIO_SECURE': 'False',
    'MINIO_BUCKET': 'test-bucket',
    'DB_HOST': 'localhost',
    'DB_NAME': 'test',
    'DB_USER': 'test',
    'DB_PASSWORD': 'test'
}

# Test StorageService.clear_bucket()
try:
    with patch.dict('os.environ', MOCK_ENV):
        from src.services.storage import StorageService
    STORAGE_AVAILABLE = True
except ImportError as e:
    STORAGE_AVAILABLE = False
    print(f"Warning: Could not import StorageService: {e}")


@pytest.mark.skipif(not STORAGE_AVAILABLE, reason="StorageService not available")
class TestStorageServiceClearBucket:
    """Test cases for StorageService.clear_bucket() method."""

    @pytest.fixture
    def mock_minio_client(self):
        """Create a mock MinIO client."""
        client = Mock()
        return client

    @pytest.fixture
    def storage_service(self, mock_minio_client):
        """Create a StorageService with mocked MinIO client."""
        with patch.dict('os.environ', MOCK_ENV):
            with patch('src.services.storage.Minio') as mock_minio_class:
                mock_minio_class.return_value = mock_minio_client
                service = StorageService()
                return service

    def test_clear_bucket_exists(self, storage_service, mock_minio_client):
        """Test clear_bucket when bucket exists."""
        # Arrange
        mock_minio_client.bucket_exists.return_value = True

        # Act
        result = storage_service.clear_bucket()

        # Assert
        mock_minio_client.bucket_exists.assert_called_once_with('test-bucket')
        mock_minio_client.remove_bucket.assert_called_once_with('test-bucket')
        mock_minio_client.make_bucket.assert_called_once_with('test-bucket')
        assert result["status"] == "success"
        assert "cleared" in result["message"]
        assert result["deleted_objects"] == "all"

    def test_clear_bucket_not_exists(self, storage_service, mock_minio_client):
        """Test clear_bucket when bucket doesn't exist."""
        # Arrange
        mock_minio_client.bucket_exists.return_value = False

        # Act
        result = storage_service.clear_bucket()

        # Assert
        mock_minio_client.bucket_exists.assert_called_once_with('test-bucket')
        mock_minio_client.remove_bucket.assert_not_called()
        mock_minio_client.make_bucket.assert_called_once_with('test-bucket')
        assert result["status"] == "success"
        assert "created" in result["message"]
        assert result["deleted_objects"] == 0

    def test_clear_bucket_error(self, storage_service, mock_minio_client):
        """Test clear_bucket when an error occurs."""
        # Arrange
        mock_minio_client.bucket_exists.side_effect = Exception("Connection error")

        # Act
        result = storage_service.clear_bucket()

        # Assert
        assert result["status"] == "error"
        assert "Connection error" in result["message"]


# Test video_controller clear_data endpoint
try:
    from src.api.video_controller import clear_data
    VIDEO_CONTROLLER_AVAILABLE = True
except ImportError as e:
    VIDEO_CONTROLLER_AVAILABLE = False
    print(f"Warning: Could not import video_controller: {e}")


@pytest.mark.skipif(not VIDEO_CONTROLLER_AVAILABLE, reason="video_controller not available")
class TestClearDataEndpoint:
    """Test cases for /api/video/clear endpoint with delete_img parameter."""

    @pytest.fixture
    def mock_db(self):
        """Create a mock DatabaseService."""
        db = Mock()
        db.conn = Mock()
        mock_cursor = Mock()
        mock_cursor.execute = Mock()
        mock_cursor.rowcount = 5
        db.conn.cursor = Mock(return_value=mock_cursor)
        db.conn.commit = Mock()
        db.conn.rollback = Mock()
        return db

    @pytest.fixture
    def mock_storage(self):
        """Create a mock StorageService."""
        storage = Mock()
        storage.clear_bucket.return_value = {
            "status": "success",
            "message": "Bucket cleared",
            "deleted_objects": "all"
        }
        return storage

    @pytest.mark.asyncio
    async def test_clear_data_without_delete_img(self, mock_db):
        """Test clear_data endpoint without delete_img parameter."""
        with patch('src.api.video_controller.DatabaseService', return_value=mock_db):
            result = await clear_data(type="all", delete_img=False)

            assert result["status"] == "success"
            assert "bucket_cleared" not in result

    @pytest.mark.asyncio
    async def test_clear_data_with_delete_img(self, mock_db, mock_storage):
        """Test clear_data endpoint with delete_img=True."""
        with patch('src.api.video_controller.DatabaseService', return_value=mock_db), \
             patch('src.api.video_controller.StorageService', return_value=mock_storage):
            result = await clear_data(type="all", delete_img=True)

            assert result["status"] == "success"
            assert "bucket_cleared" in result
            assert result["bucket_cleared"]["status"] == "success"
            mock_storage.clear_bucket.assert_called_once()

    @pytest.mark.asyncio
    async def test_clear_data_detections_with_delete_img(self, mock_db, mock_storage):
        """Test clear_data endpoint with type=detections and delete_img=True."""
        with patch('src.api.video_controller.DatabaseService', return_value=mock_db), \
             patch('src.api.video_controller.StorageService', return_value=mock_storage):
            result = await clear_data(type="detections", delete_img=True)

            assert result["status"] == "success"
            assert "bucket_cleared" in result
            assert "deleted_detections" in result
            assert "deleted_colors" in result

    @pytest.mark.asyncio
    async def test_clear_data_videos_with_delete_img(self, mock_db, mock_storage):
        """Test clear_data endpoint with type=videos and delete_img=True."""
        with patch('src.api.video_controller.DatabaseService', return_value=mock_db), \
             patch('src.api.video_controller.StorageService', return_value=mock_storage):
            result = await clear_data(type="videos", delete_img=True)

            assert result["status"] == "success"
            assert "bucket_cleared" in result
            assert "deleted_count" in result

    @pytest.mark.asyncio
    async def test_clear_data_storage_error(self, mock_db, mock_storage):
        """Test clear_data endpoint when StorageService raises an error."""
        mock_storage.clear_bucket.side_effect = Exception("MinIO connection failed")

        with patch('src.api.video_controller.DatabaseService', return_value=mock_db), \
             patch('src.api.video_controller.StorageService', return_value=mock_storage):
            result = await clear_data(type="all", delete_img=True)

            assert result["status"] == "success"
            assert "bucket_cleared" in result
            assert result["bucket_cleared"]["status"] == "error"
            assert "MinIO connection failed" in result["bucket_cleared"]["message"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
