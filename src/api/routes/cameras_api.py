from fastapi import APIRouter, HTTPException
from src.services.database import DatabaseService
from pydantic import BaseModel

router = APIRouter()

# Singleton — สร้างครั้งเดียวตอน import (setup_tables รันแค่ครั้งเดียว)
_db = DatabaseService()


class CameraCreate(BaseModel):
    name: str
    source_url: str
    is_active: bool = True

class CameraUpdate(BaseModel):
    name: str
    source_url: str
    is_active: bool

class RelationshipCreate(BaseModel):
    from_camera_id: int
    to_camera_id: int
    avg_transition_time: int

@router.get("/cameras")
async def get_all_cameras():
    """Get all cameras"""
    try:
        db = _db
        db._ensure_connection()
        
        query = "SELECT id, name, source_url, is_active FROM cameras ORDER BY id"
        
        with db.conn.cursor() as cur:
            cur.execute(query)
            rows = cur.fetchall()
            
            cameras = []
            for row in rows:
                cameras.append({
                    "id": row[0],
                    "name": row[1],
                    "source_url": row[2],
                    "is_active": row[3]
                })
            
            return {"cameras": cameras}
            
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/cameras")
async def create_camera(camera: CameraCreate):
    """Create a new camera"""
    try:
        db = _db
        db._ensure_connection()
        
        query = """
            INSERT INTO cameras (name, source_url, is_active) 
            VALUES (%s, %s, %s) 
            RETURNING id, name, source_url, is_active
        """
        
        with db.conn.cursor() as cur:
            cur.execute(query, (camera.name, camera.source_url, camera.is_active))
            result = cur.fetchone()
            db.conn.commit()
            
            return {
                "id": result[0],
                "name": result[1],
                "source_url": result[2],
                "is_active": result[3]
            }
            
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.put("/cameras/{camera_id}")
async def update_camera(camera_id: int, camera: CameraUpdate):
    """Update an existing camera"""
    try:
        db = _db
        db._ensure_connection()
        
        query = """
            UPDATE cameras 
            SET name = %s, source_url = %s, is_active = %s 
            WHERE id = %s 
            RETURNING id, name, source_url, is_active
        """
        
        with db.conn.cursor() as cur:
            cur.execute(query, (camera.name, camera.source_url, camera.is_active, camera_id))
            result = cur.fetchone()
            
            if not result:
                raise HTTPException(status_code=404, detail="Camera not found")
                
            db.conn.commit()
            
            return {
                "id": result[0],
                "name": result[1],
                "source_url": result[2],
                "is_active": result[3]
            }
            
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/cameras/{camera_id}")
async def delete_camera(camera_id: int):
    """Delete a camera"""
    try:
        db = _db
        db._ensure_connection()
        
        # First delete related relationships
        with db.conn.cursor() as cur:
            cur.execute("DELETE FROM camera_relationships WHERE from_camera_id = %s OR to_camera_id = %s", (camera_id, camera_id))
            
            # Then delete the camera
            cur.execute("DELETE FROM cameras WHERE id = %s", (camera_id,))
            
            if cur.rowcount == 0:
                raise HTTPException(status_code=404, detail="Camera not found")
                
            db.conn.commit()
            
            return {"status": "deleted", "camera_id": camera_id}
            
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
