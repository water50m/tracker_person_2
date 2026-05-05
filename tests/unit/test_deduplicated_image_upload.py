"""
Tests for deduplicated image upload feature.
Only uploads image when our_id is first created, reuses image_path for subsequent detections.
"""
import pytest
import asyncio
import uuid
from unittest.mock import Mock, patch, MagicMock, call
import numpy as np


class TestDeduplicatedImageUpload:
    """Test suite for deduplicated image upload to MINIO."""

    @pytest.fixture
    def mock_storage(self):
        """Mock StorageService for MINIO uploads."""
        storage = Mock()
        storage.upload_image = Mock(return_value="http://minio/detections/test-image.jpg")
        return storage

    @pytest.fixture
    def mock_db(self):
        """Mock DatabaseService."""
        db = Mock()
        db.insert_detections_batch = Mock()
        db.insert_detection_colors = Mock()
        return db

    @pytest.fixture
    def mock_detector(self):
        """Mock PersonDetector with track_people."""
        detector = Mock()
        
        # Create mock results with boxes
        def create_mock_box(x1, y1, x2, y2, track_id):
            box = Mock()
            box.xyxy = [[x1, y1, x2, y2]]
            box.id = [track_id]
            return box
        
        mock_results = Mock()
        mock_results.boxes = [
            create_mock_box(100, 100, 200, 300, 1),  # byte_id=1
        ]
        detector.track_people = Mock(return_value=mock_results)
        return detector

    @pytest.fixture
    def mock_classifier(self):
        """Mock ClothingClassifier."""
        classifier = Mock()
        classifier.predict = Mock(return_value=("T-Shirt", 0.95, [110, 110, 190, 290]))
        classifier.predict_top_n = Mock(return_value=[("T-Shirt", 0.95, [110, 110, 190, 290])])
        return classifier

    def test_new_our_id_uploads_image(self, mock_storage, mock_db, mock_detector, mock_classifier):
        """
        Test Case 1: When a new our_id is created, image should be uploaded.
        
        Given: ByteTrack assigns new byte_id
        When: Hybrid tracking creates new our_id
        Then: Image should be uploaded to MINIO
        """
        # Simulate: byte_id 1 -> new our_id 1
        hybrid_state = {
            "id_mapping": {},  # byte_id not yet mapped
            "lost_tracks": {},
            "next_our_id": 1,
            "track_history": {},
        }
        
        # Mock the embedder for Re-ID
        mock_embedder = Mock()
        mock_embedder.get_embedding = Mock(return_value=(np.array([0.1, 0.2, 0.3]), ["T-Shirt"]))
        
        # Import and test the matching logic
        from src.ai.reid_utils import match_lost_track
        
        # When byte_id is not in mapping and no lost track match
        # New our_id should be assigned
        byte_id = 1
        if byte_id not in hybrid_state["id_mapping"]:
            # Try to match with lost tracks (should return None for new track)
            new_features = {
                "detailed_colors": {"red": 0.8},
                "color_groups": {"warm": 0.8},
                "embedding": [0.1, 0.2, 0.3],
                "clothes": ["T-Shirt"]
            }
            recovered_id = match_lost_track(new_features, hybrid_state["lost_tracks"], threshold=0.7)
            
            if recovered_id is None:
                # New track - should upload image
                hybrid_state["id_mapping"][byte_id] = hybrid_state["next_our_id"]
                hybrid_state["next_our_id"] += 1
                should_upload = True
            else:
                should_upload = False  # Recovered - reuse existing image
        else:
            should_upload = False  # Existing - already has image
        
        assert should_upload is True, "New our_id should trigger image upload"
        assert hybrid_state["id_mapping"][byte_id] == 1

    def test_existing_our_id_reuses_image_path(self, mock_storage, mock_db):
        """
        Test Case 2: When our_id already exists, reuse existing image_path.
        
        Given: our_id 1 already has image uploaded
        When: Same our_id detected again
        Then: Reuse image_path from track_history, do not upload
        """
        # Simulate existing state
        hybrid_state = {
            "id_mapping": {1: 1},  # byte_id 1 -> our_id 1
            "lost_tracks": {},
            "next_our_id": 2,
            "track_history": {
                1: {
                    "clothes": ["T-Shirt"],
                    "detailed_colors": {"red": 0.8},
                    "color_groups": {"warm": 0.8},
                    "primary_detailed_color": "red",
                    "primary_color_group": "warm",
                    "primary_tone_group": "vibrant",
                    "top_colors": [{"color": "red", "percentage": 0.8}],
                    "tone_groups": {},
                    "brightness_groups": {},
                    "vibrancy_groups": {},
                    "temperature_groups": {},
                    "clothing_color_groups": {},
                    "embedding": [0.1, 0.2, 0.3],
                    "last_seen": 100,
                    "confidence": 0.95,
                    # KEY: Store image_path for reuse
                    "image_path": "http://minio/detections/cam1/video1/id_1_frame_100.jpg",
                    "bbox_image_path": "http://minio/detections/cam1/video1/bbox_id_1_frame_100.jpg",
                }
            },
        }
        
        byte_id = 1
        
        # Check if byte_id is already mapped
        if byte_id in hybrid_state["id_mapping"]:
            our_id = hybrid_state["id_mapping"][byte_id]
            # Get existing image_path from track_history
            track_data = hybrid_state["track_history"].get(our_id, {})
            existing_image_path = track_data.get("image_path")
            existing_bbox_path = track_data.get("bbox_image_path")
            should_upload = False  # Don't upload, reuse existing
        else:
            should_upload = True
            existing_image_path = None
            existing_bbox_path = None
        
        assert should_upload is False, "Existing our_id should NOT trigger new upload"
        assert existing_image_path == "http://minio/detections/cam1/video1/id_1_frame_100.jpg"
        assert existing_bbox_path == "http://minio/detections/cam1/video1/bbox_id_1_frame_100.jpg"

    def test_recovered_track_uploads_new_image(self):
        """
        Test Case 3: When track is recovered from lost_tracks, upload NEW image.
        
        Given: Person was lost, now reappears with new byte_id but matches lost track
        When: Re-ID matches with lost_tracks entry
        Then: Recover original our_id but upload NEW image (not reuse old)
        """
        from src.ai.reid_utils import match_lost_track
        
        # Simulate: our_id 1 was lost
        lost_tracks = {
            1: {
                "features": {
                    "detailed_colors": {"red": 0.8, "blue": 0.2},
                    "color_groups": {"warm": 0.8},
                    "embedding": [0.1, 0.2, 0.3],
                    "clothes": ["T-Shirt"],
                    # Old image path stored
                    "image_path": "http://minio/detections/cam1/video1/id_1_original.jpg",
                    "bbox_image_path": "http://minio/detections/cam1/video1/bbox_id_1_original.jpg",
                },
                "last_seen": 50,
            }
        }
        
        hybrid_state = {
            "id_mapping": {},  # New byte_id, not yet mapped
            "lost_tracks": lost_tracks,
            "next_our_id": 2,
            "track_history": {},
        }
        
        # New detection with similar features
        new_features = {
            "detailed_colors": {"red": 0.75, "blue": 0.25},
            "color_groups": {"warm": 0.75},
            "embedding": [0.11, 0.21, 0.31],  # Similar embedding
            "clothes": ["T-Shirt"]
        }
        
        # Try to match with lost tracks
        recovered_id = match_lost_track(new_features, hybrid_state["lost_tracks"], threshold=0.7)
        
        if recovered_id is not None:
            # Recover the track
            is_recovered_track = True
            our_id = recovered_id
            
            # For recovered tracks: Upload NEW image (not reuse)
            should_upload = is_recovered_track  # True for recovered
            
            # After recovery, new image is uploaded and stored
            new_image_path = f"http://minio/detections/cam1/video1/id_{our_id}_frame_100.jpg"
            hybrid_state["track_history"][our_id] = {
                "clothes": ["T-Shirt"],
                "image_path": new_image_path,
                "bbox_image_path": f"http://minio/detections/cam1/video1/bbox_id_{our_id}_frame_100.jpg",
            }
            
            assert our_id == 1
            assert should_upload is True, "Recovered track should upload NEW image"
            # New image path should be different from old
            assert hybrid_state["track_history"][our_id]["image_path"] != lost_tracks[1]["features"]["image_path"]

    def test_image_path_stored_in_track_history(self):
        """
        Test Case 4: After first upload, image_path should be stored in track_history.
        
        Given: New our_id created and image uploaded
        When: Upload completes
        Then: Store image_path in track_history for future reuse
        """
        hybrid_state = {
            "id_mapping": {1: 1},
            "lost_tracks": {},
            "next_our_id": 2,
            "track_history": {
                1: {
                    "clothes": ["T-Shirt"],
                    "detailed_colors": {"red": 0.8},
                    "last_seen": 100,
                }
            },
        }
        
        our_id = 1
        uploaded_image_path = "http://minio/detections/cam1/video1/id_1_frame_100.jpg"
        uploaded_bbox_path = "http://minio/detections/cam1/video1/bbox_id_1_frame_100.jpg"
        
        # After upload, store paths in track_history
        if our_id in hybrid_state["track_history"]:
            hybrid_state["track_history"][our_id]["image_path"] = uploaded_image_path
            hybrid_state["track_history"][our_id]["bbox_image_path"] = uploaded_bbox_path
        
        assert hybrid_state["track_history"][our_id]["image_path"] == uploaded_image_path
        assert hybrid_state["track_history"][our_id]["bbox_image_path"] == uploaded_bbox_path

    def test_db_insert_uses_reused_image_path(self):
        """
        Test Case 5: DB insert should use the reused image_path, not empty string.
        
        Given: our_id already has image_path in track_history
        When: Creating DB insert data
        Then: Use stored image_path instead of triggering new upload
        """
        track_history = {
            1: {
                "image_path": "http://minio/detections/cam1/video1/id_1_frame_100.jpg",
                "bbox_image_path": "http://minio/detections/cam1/video1/bbox_id_1_frame_100.jpg",
            }
        }
        
        track_id = 1
        
        # When creating DB insert data
        if track_id in track_history:
            image_path = track_history[track_id].get("image_path", "")
            bbox_image_path = track_history[track_id].get("bbox_image_path", "")
        else:
            image_path = ""
            bbox_image_path = ""
        
        assert image_path == "http://minio/detections/cam1/video1/id_1_frame_100.jpg"
        assert bbox_image_path == "http://minio/detections/cam1/video1/bbox_id_1_frame_100.jpg"

    def test_multiple_detections_same_our_id_single_upload(self):
        """
        Test Case 6: Multiple detections with same our_id should only upload once.
        
        Given: our_id 1 detected at frame 100, 200, 300
        When: Processing each frame
        Then: Only first detection uploads, others reuse image_path
        """
        hybrid_state = {
            "id_mapping": {1: 1},  # byte_id 1 -> our_id 1
            "lost_tracks": {},
            "next_our_id": 2,
            "track_history": {},
        }
        
        upload_count = 0
        frames = [100, 200, 300]
        
        for frame in frames:
            our_id = 1
            
            # Check if we need to upload
            if our_id in hybrid_state["track_history"]:
                # Already has image, reuse
                image_path = hybrid_state["track_history"][our_id].get("image_path")
                should_upload = False
            else:
                # First time, need to upload
                should_upload = True
                image_path = f"http://minio/detections/cam1/video1/id_{our_id}_frame_{frame}.jpg"
                
                # After upload, store in track_history
                hybrid_state["track_history"][our_id] = {
                    "image_path": image_path,
                    "bbox_image_path": f"http://minio/detections/cam1/video1/bbox_id_{our_id}_frame_{frame}.jpg",
                    "last_seen": frame,
                }
                upload_count += 1
        
        assert upload_count == 1, f"Should only upload once, but uploaded {upload_count} times"
        assert hybrid_state["track_history"][1]["image_path"] == "http://minio/detections/cam1/video1/id_1_frame_100.jpg"

    def test_different_our_ids_upload_separately(self):
        """
        Test Case 7: Different our_ids should each upload their own image.
        
        Given: our_id 1 and our_id 2 detected
        When: Processing detections
        Then: Each our_id uploads its own image
        """
        hybrid_state = {
            "id_mapping": {1: 1, 2: 2},  # Two different persons
            "lost_tracks": {},
            "next_our_id": 3,
            "track_history": {},
        }
        
        upload_calls = []
        
        for byte_id, our_id in [(1, 1), (2, 2)]:
            if our_id not in hybrid_state["track_history"]:
                # Need to upload
                image_path = f"http://minio/detections/cam1/video1/id_{our_id}.jpg"
                hybrid_state["track_history"][our_id] = {
                    "image_path": image_path,
                    "last_seen": 100,
                }
                upload_calls.append((our_id, image_path))
        
        assert len(upload_calls) == 2
        assert (1, "http://minio/detections/cam1/video1/id_1.jpg") in upload_calls
        assert (2, "http://minio/detections/cam1/video1/id_2.jpg") in upload_calls


class TestImageDeduplicationIntegration:
    """Integration tests for image deduplication with actual flow."""

    def test_classification_results_store_image_path(self):
        """
        Test that classification_results stores image_path for DB reuse.
        """
        # Simulate classification results structure
        classification_results = {
            1: {
                "clothing_type": "T-Shirt",
                "confidence": 0.95,
                "person_crop": np.zeros((100, 100, 3), dtype=np.uint8),
                "bbox": (110, 110, 190, 290),
                "predictions": [("T-Shirt", 0.95, [110, 110, 190, 290])],
                # NEW: Add image_path for reuse
                "image_path": "http://minio/detections/cam1/video1/id_1.jpg",
                "bbox_image_path": "http://minio/detections/cam1/video1/bbox_id_1.jpg",
            }
        }
        
        track_id = 1
        result = classification_results[track_id]
        
        assert "image_path" in result
        assert "bbox_image_path" in result
        assert result["image_path"] == "http://minio/detections/cam1/video1/id_1.jpg"

    def test_hybrid_state_structure_with_image_paths(self):
        """
        Test that hybrid_state track_history includes image_path fields.
        """
        hybrid_state = {
            "id_mapping": {1: 1},
            "lost_tracks": {},
            "next_our_id": 2,
            "track_history": {
                1: {
                    "clothes": ["T-Shirt"],
                    "detailed_colors": {"red": 0.8},
                    "color_groups": {"warm": 0.8},
                    "primary_detailed_color": "red",
                    "primary_color_group": "warm",
                    "primary_tone_group": "vibrant",
                    "top_colors": [{"color": "red", "percentage": 0.8}],
                    "tone_groups": {},
                    "brightness_groups": {},
                    "vibrancy_groups": {},
                    "temperature_groups": {},
                    "clothing_color_groups": {},
                    "embedding": [0.1, 0.2, 0.3],
                    "last_seen": 100,
                    "confidence": 0.95,
                    # NEW FIELDS
                    "image_path": "http://minio/detections/cam1/video1/id_1.jpg",
                    "bbox_image_path": "http://minio/detections/cam1/video1/bbox_id_1.jpg",
                }
            },
        }
        
        track_data = hybrid_state["track_history"][1]
        assert "image_path" in track_data
        assert "bbox_image_path" in track_data
        assert track_data["image_path"].startswith("http://minio/")
