"""
Test for video queue service stop/resume functionality.

This test verifies that after stopping a job, new jobs can still be processed
(not stuck in pending state indefinitely).
"""
import asyncio
import pytest
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.services.video_queue_service import VideoQueueService, JobStatus


@pytest.mark.asyncio
async def test_stop_job_then_add_new_job():
    """
    Test that after stopping a job, the processing loop continues
    and can process new jobs (not stuck in pending).
    
    This is a regression test for the bug where:
    1. Job A is processing
    2. Job A is stopped
    3. Job B is added
    4. Job B gets stuck in pending forever because the processing loop exited
    """
    service = VideoQueueService(max_concurrent=1)
    
    # Start the processing loop
    await service.start_processing()
    
    try:
        # Add a fake video job (we'll stop it before it completes)
        job1_id = await service.add_video(
            source="/tmp/fake_video1.mp4",
            camera_id="CAM-01",
            display_mode="background",
            priority=0
        )
        
        # Wait a bit for the job to start processing
        await asyncio.sleep(0.5)
        
        # Get the job status - should be processing or at least pending
        job1 = service.get_job(job1_id)
        assert job1 is not None, "Job 1 should exist"
        print(f"Job 1 status before stop: {job1.status.value}")
        
        # Stop the job
        stop_result = await service.stop_job(job1_id)
        assert stop_result, "Should be able to stop the job"
        
        # Wait for the job to be marked as stopped or failed
        await asyncio.sleep(1.0)
        
        job1 = service.get_job(job1_id)
        # Job may be STOPPED or FAILED (if video doesn't exist, it fails immediately)
        assert job1.status in [JobStatus.STOPPED, JobStatus.FAILED], \
            f"Job 1 should be stopped or failed, got {job1.status.value}"
        print(f"Job 1 status after stop: {job1.status.value}")
        
        # Add a second job
        job2_id = await service.add_video(
            source="/tmp/fake_video2.mp4", 
            camera_id="CAM-01",
            display_mode="background",
            priority=0
        )
        
        # Wait for the second job to be processed (or at least attempted)
        # The processing loop should still be running!
        await asyncio.sleep(2.0)
        
        # Check the status
        job2 = service.get_job(job2_id)
        assert job2 is not None, "Job 2 should exist"
        print(f"Job 2 status after waiting: {job2.status.value}")
        
        # The job should NOT still be pending - it should have been attempted
        # (will likely fail since the video file doesn't exist, but shouldn't be stuck)
        assert job2.status != JobStatus.PENDING, \
            f"Job 2 is stuck in pending - processing loop likely exited! Status: {job2.status.value}"
        
        print("✅ Test passed: New job was processed after stopping previous job")
        
    finally:
        # Clean up
        await service.stop_processing()


if __name__ == "__main__":
    # Run the test directly
    asyncio.run(test_stop_job_then_add_new_job())
