from fastapi import APIRouter, HTTPException
from src.services.database import DatabaseService

router = APIRouter()

@router.get("/cameras/{camera_id}/relationships")
async def get_camera_relationships(camera_id: str):
    """
    Get all cameras that have relationships with the specified camera
    Returns both outgoing and incoming relationships
    """
    try:
        db = DatabaseService()
        
        # Query for both from_camera_id and to_camera_id relationships
        # Handle both string and integer camera IDs - try to parse as integer first
        try:
            camera_id_int = int(camera_id)
            # Try integer comparison first
            query = """
                SELECT 
                    from_camera_id,
                    to_camera_id,
                    avg_transition_time,
                    CASE 
                        WHEN from_camera_id = %s THEN 'outgoing'
                        ELSE 'incoming'
                    END as relationship_type
                FROM camera_relationships 
                WHERE from_camera_id = %s OR to_camera_id = %s
            """
            params = (camera_id_int, camera_id_int, camera_id_int)
        except ValueError:
            # If not integer, use string comparison
            query = """
                SELECT 
                    from_camera_id,
                    to_camera_id,
                    avg_transition_time,
                    CASE 
                        WHEN from_camera_id::text = %s THEN 'outgoing'
                        ELSE 'incoming'
                    END as relationship_type
                FROM camera_relationships 
                WHERE from_camera_id::text = %s OR to_camera_id::text = %s
            """
            params = (camera_id, camera_id, camera_id)
        
        with db.conn.cursor() as cur:
            cur.execute(query, params)
            rows = cur.fetchall()
            
            relationships = []
            for row in rows:
                from_camera, to_camera, avg_time, rel_type = row
                
                # Determine the related camera (the other one in the relationship)
                related_camera = to_camera if rel_type == 'outgoing' else from_camera
                
                relationships.append({
                    "camera_id": str(related_camera),
                    "relationship_type": rel_type,
                    "avg_transition_time": avg_time,
                    "description": f"{'From' if rel_type == 'outgoing' else 'To'} camera {camera_id} {'to' if rel_type == 'outgoing' else 'from'} camera {related_camera}"
                })
            
            return {
                "camera_id": camera_id,
                "relationships": relationships,
                "total_relationships": len(relationships)
            }
            
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/cameras/relationships/all")
async def get_all_camera_relationships():
    """
    Get all camera relationships for display in map or list view
    """
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
            
            return {
                "relationships": relationships,
                "total_count": len(relationships)
            }
            
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
