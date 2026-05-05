"""
progress_api.py - Real-time Progress Monitoring API

This module provides Server-Sent Events (SSE) endpoints for
monitoring video processing progress in real-time.

Endpoints:
- GET /api/video/{video_id}/progress - SSE stream for video progress
- GET /api/video/active-processes - List active video processes

Usage (Frontend):
    const eventSource = new EventSource(`/api/video/${videoId}/progress`);
    eventSource.onmessage = (event) => {
        const data = JSON.parse(event.data);
        updateProgressBar(data.percentage);
        updateStatusText(data.message);
    };
"""
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
import asyncio
import json
import time
from typing import Optional, Dict, Any, AsyncGenerator

from services.video_processor import get_progress_tracker, ProgressTracker


router = APIRouter(prefix="/api/video", tags=["Progress Monitoring"])


# In-memory store for process metadata (complements ProgressTracker)
_process_metadata: Dict[str, Dict[str, Any]] = {}


async def progress_event_generator(video_id: str) -> AsyncGenerator[str, None]:
    """
    Generate SSE events for video processing progress.
    
    Yields:
        Server-Sent Event formatted strings
    """
    progress_tracker = get_progress_tracker()
    last_percentage = -1
    last_update = time.time()
    
    try:
        while True:
            # Get current progress
            progress = progress_tracker.get_progress(video_id)
            
            if progress is None:
                # No progress found yet, might be starting
                yield f"data: {json.dumps({'status': 'starting', 'percentage': 0})}\n\n"
                await asyncio.sleep(1.0)
                continue
            
            current_percentage = progress.get('percentage', 0)
            
            # Only send update if changed or every 2 seconds
            if current_percentage != last_percentage or (time.time() - last_update) > 2.0:
                # Build event data
                event_data = {
                    'video_id': video_id,
                    'percentage': current_percentage,
                    'current_frame': progress.get('current_frame', 0),
                    'total_frames': progress.get('total_frames', 0),
                    'status': progress.get('status', 'processing'),
                    'message': progress.get('message', ''),
                    'timestamp': time.time(),
                }
                
                yield f"data: {json.dumps(event_data)}\n\n"
                
                last_percentage = current_percentage
                last_update = time.time()
                
                # Check if complete
                if progress.get('status') in ['completed', 'error', 'stopped']:
                    # Send final update
                    final_data = {
                        **event_data,
                        'completed': True,
                        'final_status': progress.get('status'),
                    }
                    yield f"data: {json.dumps(final_data)}\n\n"
                    break
            
            # Throttle updates to avoid overwhelming client
            await asyncio.sleep(0.5)  # 2 updates per second max
            
    except asyncio.CancelledError:
        # Client disconnected
        raise
    except Exception as e:
        # Send error event
        error_data = {
            'video_id': video_id,
            'status': 'error',
            'error': str(e),
            'timestamp': time.time(),
        }
        yield f"data: {json.dumps(error_data)}\n\n"


@router.get("/{video_id}/progress")
async def video_progress_stream(video_id: str):
    """
    Server-Sent Events endpoint for video processing progress.
    
    This endpoint streams real-time progress updates as the video
    is being processed. Use EventSource in JavaScript to consume.
    
    Args:
        video_id: Video identifier
    
    Returns:
        StreamingResponse with SSE content type
    
    Example JavaScript:
        const es = new EventSource(`/api/video/${videoId}/progress`);
        es.onmessage = (e) => {
            const data = JSON.parse(e.data);
            console.log(`${data.percentage}% - ${data.message}`);
        };
        es.onerror = (e) => {
            console.error('Progress stream error');
        };
    """
    return StreamingResponse(
        progress_event_generator(video_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # Disable nginx buffering if applicable
        }
    )


@router.get("/{video_id}/progress/poll")
async def video_progress_poll(video_id: str) -> Dict[str, Any]:
    """
    Polling endpoint for video processing progress.
    
    Use this for clients that don't support SSE (older browsers)
    or when SSE connection issues occur.
    
    Args:
        video_id: Video identifier
    
    Returns:
        Current progress data
    """
    progress_tracker = get_progress_tracker()
    progress = progress_tracker.get_progress(video_id)
    
    if progress is None:
        return {
            'video_id': video_id,
            'status': 'not_found',
            'percentage': 0,
            'message': 'No progress data found for this video',
        }
    
    return {
        'video_id': video_id,
        'percentage': progress.get('percentage', 0),
        'current_frame': progress.get('current_frame', 0),
        'total_frames': progress.get('total_frames', 0),
        'status': progress.get('status', 'processing'),
        'message': progress.get('message', ''),
        'timestamp': time.time(),
    }


@router.get("/active-processes")
async def list_active_processes() -> Dict[str, Any]:
    """
    List all currently active video processing jobs.
    
    Returns:
        Dictionary with list of active processes and their status
    """
    progress_tracker = get_progress_tracker()
    
    # Get all progress entries
    # Note: This is a simple implementation - in production, you might want
    # to store this in Redis or database for persistence
    active_processes = []
    
    # Access the internal _progress dict (for demo purposes)
    # In production, add a proper method to ProgressTracker
    if hasattr(progress_tracker, '_progress'):
        for video_id, progress in progress_tracker._progress.items():
            active_processes.append({
                'video_id': video_id,
                'percentage': progress.get('percentage', 0),
                'status': progress.get('status', 'unknown'),
                'message': progress.get('message', ''),
                'last_update': progress.get('timestamp', 0),
            })
    
    return {
        'active_count': len(active_processes),
        'processes': active_processes,
    }


@router.delete("/{video_id}/progress")
async def clear_progress(video_id: str) -> Dict[str, Any]:
    """
    Clear progress tracking for a video.
    
    Use this after processing is complete and progress data is no longer needed.
    
    Args:
        video_id: Video identifier
    
    Returns:
        Status message
    """
    progress_tracker = get_progress_tracker()
    progress_tracker.remove_progress(video_id)
    
    return {
        'video_id': video_id,
        'status': 'cleared',
        'message': 'Progress tracking removed',
    }


# ==============================================================================
# Stream Progress API
# ==============================================================================

@router.get("/stream/{camera_id}/stats")
async def stream_stats(camera_id: str) -> Dict[str, Any]:
    """
    Get statistics for an active stream.
    
    This is for real-time streams (RTSP cameras), not file uploads.
    
    Args:
        camera_id: Camera identifier
    
    Returns:
        Stream statistics
    """
    # This would integrate with StreamManager to get live stats
    # For now, return placeholder
    return {
        'camera_id': camera_id,
        'status': 'active',  # or 'inactive'
        'processed_frames': 0,
        'total_detections': 0,
        'fps': 0.0,
        'uptime_seconds': 0.0,
    }


# ==============================================================================
# Health Check
# ==============================================================================

@router.get("/progress/health")
async def progress_health() -> Dict[str, Any]:
    """
    Health check endpoint for progress monitoring.
    
    Returns:
        Health status
    """
    return {
        'status': 'healthy',
        'timestamp': time.time(),
        'service': 'progress-monitoring',
    }
