"""
Regression Tests for Monitoring Dashboard API

TDD: Tests for progress monitoring API endpoints.
These tests verify that the dashboard can display real-time progress.

Run with:
    uv run python -m pytest tests/regression/test_monitoring_dashboard.py -v
"""
import pytest
import asyncio
import sys
from pathlib import Path
from unittest.mock import Mock, patch
import tempfile
import os

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

# Test imports
try:
    from services.video_processor import VideoProcessor, get_progress_tracker, ProgressTracker
    from services.ai_processing_types import VideoProcessingStats
    PROGRESS_API_AVAILABLE = True
except ImportError as e:
    PROGRESS_API_AVAILABLE = False
    print(f"⚠️ Progress API not fully available: {e}")


class TestProgressTracker:
    """
    Test ProgressTracker functionality.
    """
    
    @pytest.mark.skipif(not PROGRESS_API_AVAILABLE, reason="ProgressTracker not implemented")
    def test_progress_tracker_can_record_progress(self):
        """ProgressTracker should record and retrieve progress"""
        tracker = ProgressTracker()
        
        tracker.update_progress(
            video_id="test-video-123",
            percentage=50,
            current_frame=150,
            total_frames=300,
            status="processing",
            message="Halfway done",
        )
        
        progress = tracker.get_progress("test-video-123")
        
        assert progress is not None
        assert progress['percentage'] == 50
        assert progress['current_frame'] == 150
        assert progress['total_frames'] == 300
        assert progress['status'] == "processing"
    
    @pytest.mark.skipif(not PROGRESS_API_AVAILABLE, reason="ProgressTracker not implemented")
    def test_progress_tracker_create_callback(self):
        """ProgressTracker should create usable callback"""
        tracker = ProgressTracker()
        
        callback = tracker.create_callback("test-video-456")
        
        # Call the callback
        callback(25, 75, 300)
        
        progress = tracker.get_progress("test-video-456")
        
        assert progress is not None
        assert progress['percentage'] == 25
        assert progress['current_frame'] == 75
    
    @pytest.mark.skipif(not PROGRESS_API_AVAILABLE, reason="ProgressTracker not implemented")
    def test_progress_tracker_remove_progress(self):
        """ProgressTracker should remove progress entries"""
        tracker = ProgressTracker()
        
        tracker.update_progress(
            video_id="test-to-remove",
            percentage=100,
            current_frame=100,
            total_frames=100,
        )
        
        # Verify it exists
        assert tracker.get_progress("test-to-remove") is not None
        
        # Remove it
        tracker.remove_progress("test-to-remove")
        
        # Verify it's gone
        assert tracker.get_progress("test-to-remove") is None


class TestGlobalProgressTracker:
    """
    Test global progress tracker singleton.
    """
    
    @pytest.mark.skipif(not PROGRESS_API_AVAILABLE, reason="Progress API not implemented")
    def test_get_progress_tracker_returns_singleton(self):
        """get_progress_tracker should return singleton instance"""
        tracker1 = get_progress_tracker()
        tracker2 = get_progress_tracker()
        
        assert tracker1 is tracker2
    
    @pytest.mark.skipif(not PROGRESS_API_AVAILABLE, reason="Progress API not implemented")
    def test_global_tracker_persists_data(self):
        """Global tracker should persist data across calls"""
        tracker = get_progress_tracker()
        
        tracker.update_progress(
            video_id="global-test",
            percentage=75,
            current_frame=225,
            total_frames=300,
        )
        
        # Get tracker again (should be same instance)
        tracker2 = get_progress_tracker()
        progress = tracker2.get_progress("global-test")
        
        assert progress['percentage'] == 75


class TestProgressAPIEndpoints:
    """
    Test progress API endpoints (simulated).
    
    Note: These tests verify the API contract. 
    Full integration tests require FastAPI test client.
    """
    
    @pytest.mark.skipif(not PROGRESS_API_AVAILABLE, reason="Progress API not implemented")
    def test_progress_event_generator_structure(self):
        """Progress event generator should yield properly formatted SSE events"""
        tracker = get_progress_tracker()
        
        # Setup test data
        tracker.update_progress(
            video_id="sse-test",
            percentage=50,
            current_frame=150,
            total_frames=300,
            status="processing",
            message="Processing...",
        )
        
        # The actual SSE endpoint would use a generator like this
        async def mock_event_generator():
            import json
            progress = tracker.get_progress("sse-test")
            if progress:
                yield f"data: {json.dumps(progress)}\n\n"
        
        # Run the generator and collect events
        async def collect_events():
            events = []
            async for event in mock_event_generator():
                events.append(event)
            return events
        
        events = asyncio.run(collect_events())
        
        assert len(events) > 0
        assert "data:" in events[0]
        assert "sse-test" in events[0]
    
    @pytest.mark.skipif(not PROGRESS_API_AVAILABLE, reason="Progress API not implemented")
    def test_active_processes_listing(self):
        """Should be able to list all active processes"""
        tracker = get_progress_tracker()
        
        # Add multiple processes
        for i in range(3):
            tracker.update_progress(
                video_id=f"video-{i}",
                percentage=i * 30,
                current_frame=i * 30,
                total_frames=100,
                status="processing",
            )
        
        # Verify we can access all
        assert tracker.get_progress("video-0") is not None
        assert tracker.get_progress("video-1") is not None
        assert tracker.get_progress("video-2") is not None


class TestProgressWithVideoProcessing:
    """
    Test progress tracking integrated with VideoProcessor.
    """
    
    @pytest.mark.skipif(not PROGRESS_API_AVAILABLE, reason="Progress API not implemented")
    @pytest.mark.asyncio
    async def test_video_processor_updates_progress_tracker(self):
        """VideoProcessor should update progress in tracker"""
        from services.thread_pool_processor import ThreadPoolProcessor
        from unittest.mock import patch
        from services.ai_processing_types import AIProcessingResult, ProcessingStatus
        
        # Mock the AI processing
        mock_result = AIProcessingResult(
            status=ProcessingStatus.SUCCESS,
            frame_number=1,
            num_persons=0,
        )
        
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as f:
            video_path = f.name
        
        # Create minimal test video
        import cv2
        import numpy as np
        writer = cv2.VideoWriter(video_path, cv2.VideoWriter_fourcc(*'mp4v'), 30.0, (320, 240))
        for _ in range(60):
            writer.write(np.zeros((240, 320, 3), dtype=np.uint8))
        writer.release()
        
        try:
            with patch('services.thread_pool_processor.ThreadPoolProcessor.process_frame') as mock_process:
                mock_process.return_value = mock_result
                
                pool = ThreadPoolProcessor(max_workers=2)
                await pool.initialize()
                
                try:
                    processor = VideoProcessor(thread_pool=pool, frame_skip=10)
                    
                    # Get global tracker
                    tracker = get_progress_tracker()
                    
                    # Create callback
                    callback = tracker.create_callback("test-progress-video")
                    
                    # Process video
                    await processor.process_video(
                        source=video_path,
                        camera_id="TEST-CAM",
                        video_id="test-progress-video",
                        save_to_db=False,
                        save_images=False,
                        on_progress=callback,
                    )
                    
                    # Verify progress was recorded
                    progress = tracker.get_progress("test-progress-video")
                    assert progress is not None
                    assert progress['percentage'] > 0
                    
                finally:
                    await pool.shutdown()
        finally:
            if os.path.exists(video_path):
                os.remove(video_path)


class TestResumeState:
    """
    Test resume state functionality.
    """
    
    @pytest.mark.skipif(not PROGRESS_API_AVAILABLE, reason="ResumeState not implemented")
    def test_resume_state_save_and_load(self):
        """ResumeState should save and load correctly"""
        from services.video_processor import ResumeState
        
        with tempfile.TemporaryDirectory() as tmpdir:
            state = ResumeState(
                video_id="resume-test-123",
                source="video.mp4",
                camera_id="CAM-01",
                last_processed_frame=150,
                total_frames=300,
                processed_persons=10,
                status="processing",
            )
            
            # Save
            state.save(tmpdir)
            
            # Load
            loaded = ResumeState.load("resume-test-123", tmpdir)
            
            assert loaded is not None
            assert loaded.video_id == "resume-test-123"
            assert loaded.last_processed_frame == 150
            assert loaded.processed_persons == 10
    
    @pytest.mark.skipif(not PROGRESS_API_AVAILABLE, reason="ResumeState not implemented")
    def test_resume_state_delete(self):
        """ResumeState should delete correctly"""
        from services.video_processor import ResumeState
        
        with tempfile.TemporaryDirectory() as tmpdir:
            state = ResumeState(
                video_id="delete-test",
                source="video.mp4",
                camera_id="CAM-01",
                last_processed_frame=100,
            )
            
            state.save(tmpdir)
            assert ResumeState.load("delete-test", tmpdir) is not None
            
            ResumeState.delete("delete-test", tmpdir)
            assert ResumeState.load("delete-test", tmpdir) is None
    
    @pytest.mark.skipif(not PROGRESS_API_AVAILABLE, reason="ResumeState not implemented")
    def test_resume_state_load_nonexistent(self):
        """Loading nonexistent state should return None"""
        from services.video_processor import ResumeState
        
        with tempfile.TemporaryDirectory() as tmpdir:
            loaded = ResumeState.load("nonexistent", tmpdir)
            assert loaded is None


class TestMonitoringDashboardIntegration:
    """
    High-level integration tests for monitoring dashboard.
    """
    
    @pytest.mark.skipif(not PROGRESS_API_AVAILABLE, reason="Progress API not implemented")
    def test_complete_workflow_simulation(self):
        """Simulate complete workflow from start to completion"""
        tracker = get_progress_tracker()
        
        video_id = "workflow-test"
        
        # 1. Initial state
        tracker.update_progress(
            video_id=video_id,
            percentage=0,
            current_frame=0,
            total_frames=1000,
            status="pending",
            message="Starting...",
        )
        
        progress = tracker.get_progress(video_id)
        assert progress['status'] == "pending"
        
        # 2. Processing state
        tracker.update_progress(
            video_id=video_id,
            percentage=50,
            current_frame=500,
            total_frames=1000,
            status="processing",
            message="Halfway done...",
        )
        
        progress = tracker.get_progress(video_id)
        assert progress['percentage'] == 50
        assert progress['status'] == "processing"
        
        # 3. Complete
        tracker.update_progress(
            video_id=video_id,
            percentage=100,
            current_frame=1000,
            total_frames=1000,
            status="completed",
            message="Done!",
        )
        
        progress = tracker.get_progress(video_id)
        assert progress['percentage'] == 100
        assert progress['status'] == "completed"
    
    @pytest.mark.skipif(not PROGRESS_API_AVAILABLE, reason="Progress API not implemented")
    def test_error_state_handling(self):
        """Dashboard should handle error states correctly"""
        tracker = get_progress_tracker()
        
        video_id = "error-test"
        
        tracker.update_progress(
            video_id=video_id,
            percentage=30,
            current_frame=300,
            total_frames=1000,
            status="error",
            message="Error: Something went wrong",
        )
        
        progress = tracker.get_progress(video_id)
        assert progress['status'] == "error"
        assert "error" in progress['message'].lower()
