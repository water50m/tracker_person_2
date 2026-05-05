"""
Migration: Add color_groups column to detection_colors table

This migration adds the color_groups JSONB column to store the full
color groups data in the detection_colors table instead of detections table.
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.services.database import DatabaseService


def migrate():
    """Add color_groups column to detection_colors table"""
    db = DatabaseService()
    
    try:
        db._ensure_connection()
        with db.conn.cursor() as cur:
            # Add color_groups column
            cur.execute("""
                ALTER TABLE detection_colors 
                ADD COLUMN IF NOT EXISTS color_groups JSONB DEFAULT '{}';
            """)
            
            # Create index for color_groups
            cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_detection_colors_color_groups 
                ON detection_colors USING gin (color_groups);
            """)
            
            db.conn.commit()
            print("✅ Migration completed: color_groups column added to detection_colors")
            return True
            
    except Exception as e:
        db.conn.rollback()
        print(f"❌ Migration failed: {e}")
        return False


if __name__ == "__main__":
    migrate()
