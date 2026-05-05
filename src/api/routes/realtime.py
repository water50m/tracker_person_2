from fastapi import APIRouter, Query
from fastapi.responses import StreamingResponse
from src.api.controllers import DetectionController
from src.services.stream_manager import stream_manager
import asyncio
import json
from datetime import datetime

router = APIRouter()
controller = DetectionController()

@router.get("/api/events/stream")
async def events_stream(
    camera_id: list[str] = Query(default=[], alias="camera_id[]"),
    start_time: str | None = Query(None),
    end_time: str | None = Query(None),
):
    """
    Server-Sent Events (SSE) endpoint for real-time detection events
    Streams actual detection data from stream_manager with heartbeat
    """
    
    async def event_generator():
        # Track last sent detections to avoid duplicates
        last_detections = {}
        
        try:
            # Send initial connection message
            msg = json.dumps({
                "type": "connected",
                "timestamp": datetime.now().isoformat(),
                "message": "Event stream connected",
                "camera_ids": camera_id
            })
            yield f"data: {msg}\n\n"
            
            # Send detection events every 2 seconds
            detection_check_interval = 2.0
            heartbeat_interval = 30.0
            
            last_detection_check = 0
            last_heartbeat = 0
            
            while True:
                current_time = asyncio.get_event_loop().time()
                
                # Check for new detections
                if current_time - last_detection_check >= detection_check_interval:
                    last_detection_check = current_time
                    
                    # Get detections for requested cameras (or all if not specified)
                    target_cameras = camera_id if camera_id else list(stream_manager.latest_detections.keys())
                    
                    for cam_id in target_cameras:
                        detections = stream_manager.get_detections(cam_id)
                        if detections:
                            # Check if detections changed
                            detection_hash = hash(json.dumps(detections, sort_keys=True, default=str))
                            
                            if last_detections.get(cam_id) != detection_hash:
                                last_detections[cam_id] = detection_hash
                                
                                # Send detection event
                                msg = json.dumps({
                                    "type": "detection",
                                    "timestamp": datetime.now().isoformat(),
                                    "camera_id": cam_id,
                                    "payload": {
                                        "detections": detections,
                                        "count": len(detections)
                                    }
                                })
                                yield f"data: {msg}\n\n"
                
                # Send heartbeat every 30 seconds
                if current_time - last_heartbeat >= heartbeat_interval:
                    last_heartbeat = current_time
                    msg = json.dumps({
                        "type": "heartbeat",
                        "timestamp": datetime.now().isoformat()
                    })
                    yield f"data: {msg}\n\n"
                
                # Small sleep to prevent CPU spinning
                await asyncio.sleep(0.5)
                
        except asyncio.CancelledError:
            # Client disconnected
            msg = json.dumps({
                "type": "disconnected",
                "timestamp": datetime.now().isoformat()
            })
            yield f"data: {msg}\n\n"
    
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET",
            "Access-Control-Allow-Headers": "Content-Type",
        }
    )


@router.post("/api/events/video-end")
async def video_end_notification(
    request: dict
):
    """
    Receive video end notifications from streaming endpoints
    """
    stream_id = request.get("stream_id")
    frame_count = request.get("frame_count", 0)
    save_to_db = request.get("save_to_db", False)
    
    # Broadcast video end event to all connected SSE clients
    msg = json.dumps({
        "type": "video_end",
        "timestamp": datetime.now().isoformat(),
        "payload": {
            "stream_id": stream_id,
            "frame_count": frame_count,
            "save_to_db": save_to_db,
            "message": f"Video stream {stream_id} ended after {frame_count} frames"
        }
    })
    
    # Here we would normally broadcast to SSE clients
    # For now, just log the event
    print(f"🎬 Video End Notification: Stream {stream_id} ended after {frame_count} frames")
    
    return {"status": "success", "message": "Video end notification received"}