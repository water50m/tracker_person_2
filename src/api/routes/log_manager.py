"""
Log Manager API Routes - จัดการการแสดง/ซ่อน logs ผ่าน API
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
import sys
import os
from datetime import datetime

# Add parent directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

try:
    from src.utils.log_manager import log_manager, enable_silent_logs, disable_silent_logs, toggle_logs, get_recent_logs
except ImportError:
    # Fallback if log_manager not available
    log_manager = None

router = APIRouter()

class LogToggleRequest(BaseModel):
    action: str  # "enable", "disable", "toggle"
    log_file: Optional[str] = None

class LogStatusResponse(BaseModel):
    is_silent: bool
    log_file_enabled: bool
    buffer_size: int
    status: str

class LogResponse(BaseModel):
    success: bool
    message: str
    status: Optional[LogStatusResponse] = None

@router.get("/status", response_model=LogStatusResponse)
async def get_log_status():
    """ดูสถานะปัจจุบันของ log manager"""
    if not log_manager:
        raise HTTPException(status_code=501, detail="Log manager not available")
    
    return LogStatusResponse(
        is_silent=log_manager.is_silent,
        log_file_enabled=log_manager.log_file is not None,
        buffer_size=len(log_manager.log_buffer),
        status="silent" if log_manager.is_silent else "normal"
    )

@router.post("/toggle", response_model=LogResponse)
async def toggle_logs(request: LogToggleRequest):
    """สลับการแสดง logs"""
    if not log_manager:
        raise HTTPException(status_code=501, detail="Log manager not available")
    
    try:
        if request.action == "enable":
            log_file = request.log_file or f"web_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            enable_silent_logs(log_file)
            message = f"Silent mode enabled. Logs saved to: logs/{log_file}.log"
            
        elif request.action == "disable":
            disable_silent_logs()
            message = "Silent mode disabled. Logs will show in terminal."
            
        elif request.action == "toggle":
            log_file = request.log_file or f"web_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            toggle_logs(log_file)
            status = "enabled" if log_manager.is_silent else "disabled"
            message = f"Silent mode {status}."
            
        else:
            raise HTTPException(status_code=400, detail=f"Invalid action: {request.action}")
        
        # Get updated status
        status_response = LogStatusResponse(
            is_silent=log_manager.is_silent,
            log_file_enabled=log_manager.log_file is not None,
            buffer_size=len(log_manager.log_buffer),
            status="silent" if log_manager.is_silent else "normal"
        )
        
        return LogResponse(
            success=True,
            message=message,
            status=status_response
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to toggle logs: {str(e)}")

@router.get("/recent")
async def get_recent_logs_api(count: int = 50):
    """ดึง logs ล่าสุด"""
    if not log_manager:
        raise HTTPException(status_code=501, detail="Log manager not available")
    
    try:
        logs = get_recent_logs(count)
        return {
            "success": True,
            "count": len(logs),
            "logs": [log.rstrip() for log in logs]
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get recent logs: {str(e)}")

@router.post("/clear")
async def clear_log_buffer():
    """ล้าง log buffer"""
    if not log_manager:
        raise HTTPException(status_code=501, detail="Log manager not available")
    
    try:
        log_manager.clear_buffer()
        return {
            "success": True,
            "message": "Log buffer cleared."
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to clear log buffer: {str(e)}")
