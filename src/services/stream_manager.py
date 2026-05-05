import asyncio
from typing import Dict, Any, Optional
import time

class StreamManager:
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance.latest_frames: Dict[str, bytes] = {}
            cls._instance.latest_detections: Dict[str, list] = {}
            cls._instance.pause_prediction: Dict[str, bool] = {}
        return cls._instance

    def update_frame(self, camera_id: str, frame_bytes: bytes):
        """Update the latest JPEG frame for a camera"""
        self.latest_frames[camera_id] = frame_bytes
        
    def get_frame(self, camera_id: str) -> Optional[bytes]:
        """Get the latest JPEG frame"""
        return self.latest_frames.get(camera_id)

    def update_detections(self, camera_id: str, detections: list):
        """Update the latest detection data for API/Interactive use"""
        self.latest_detections[camera_id] = detections
        
    def get_detections(self, camera_id: str) -> list:
        """Get the latest detection data"""
        return self.latest_detections.get(camera_id, [])
        
    def clear_camera(self, camera_id: str):
        """Clean up when stream stops"""
        self.latest_frames.pop(camera_id, None)
        self.latest_detections.pop(camera_id, None)
        self.pause_prediction.pop(camera_id, None)
        
    def set_pause_prediction(self, camera_id: str, paused: bool):
        """Pause or resume AI prediction processing for a camera"""
        self.pause_prediction[camera_id] = paused
        
    def is_prediction_paused(self, camera_id: str) -> bool:
        """Check if AI prediction is paused for a camera"""
        return self.pause_prediction.get(camera_id, False)

# Global singleton instance
stream_manager = StreamManager()
