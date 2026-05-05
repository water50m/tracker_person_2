from fastapi import APIRouter, HTTPException
from src.services.database import DatabaseService
from pydantic import BaseModel

router = APIRouter()

class RelationshipCreate(BaseModel):
    from_camera_id: int
    to_camera_id: int
    avg_transition_time: int

@router.get("/camera-relationships")
async def get_all_relationships():
    """Get all camera relationships"""
    try:
        db = DatabaseService()
        
        query = """
            SELECT 
                from_camera_id,
                to_camera_id,
                avg_transition_time
            FROM camera_relationships 
            ORDER BY from_camera_id, to_camera_id
        """
        
        with db.conn.cursor() as cur:
            cur.execute(query)
            rows = cur.fetchall()
            
            relationships = []
            for row in rows:
                relationships.append({
                    "from_camera_id": row[0],
                    "to_camera_id": row[1],
                    "avg_transition_time": row[2]
                })
            
            return relationships
            
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/camera-relationships")
async def create_relationship(relationship: RelationshipCreate):
    """Create a new camera relationship"""
    try:
        db = DatabaseService()
        
        query = """
            INSERT INTO camera_relationships (from_camera_id, to_camera_id, avg_transition_time) 
            VALUES (%s, %s, %s) 
            RETURNING from_camera_id, to_camera_id, avg_transition_time
        """
        
        with db.conn.cursor() as cur:
            cur.execute(query, (relationship.from_camera_id, relationship.to_camera_id, relationship.avg_transition_time))
            result = cur.fetchone()
            db.conn.commit()
            
            return {
                "from_camera_id": result[0],
                "to_camera_id": result[1],
                "avg_transition_time": result[2]
            }
            
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/camera-relationships/{from_id}/{to_id}")
async def delete_relationship(from_id: int, to_id: int):
    """Delete a camera relationship"""
    try:
        db = DatabaseService()
        
        query = """
            DELETE FROM camera_relationships 
            WHERE from_camera_id = %s AND to_camera_id = %s
        """
        
        with db.conn.cursor() as cur:
            cur.execute(query, (from_id, to_id))
            
            if cur.rowcount == 0:
                raise HTTPException(status_code=404, detail="Relationship not found")
                
            db.conn.commit()
            
            return {"status": "deleted", "from_id": from_id, "to_id": to_id}
            
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
