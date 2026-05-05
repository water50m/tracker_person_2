"""
Migration: Remove color_profile column from detections table
Run this script to migrate existing databases to remove the redundant color_profile column
"""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.services.database import DatabaseService

def migrate_remove_color_profile():
    """Remove color_profile column from detections table"""
    db = DatabaseService()
    
    if db.conn is None:
        print("❌ Cannot connect to database. Migration aborted.")
        return False
    
    try:
        with db.conn.cursor() as cur:
            # Check if color_profile column exists
            cur.execute("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name = 'detections' AND column_name = 'color_profile'
            """)
            result = cur.fetchone()
            
            if result:
                # Remove color_profile column
                cur.execute("ALTER TABLE detections DROP COLUMN color_profile;")
                db.conn.commit()
                print("✅ Successfully removed color_profile column from detections table")
            else:
                print("ℹ️ color_profile column does not exist - nothing to migrate")
            
            # Also drop the index if it exists
            cur.execute("""
                SELECT indexname 
                FROM pg_indexes 
                WHERE tablename = 'detections' AND indexname = 'idx_color_profile'
            """)
            index_result = cur.fetchone()
            
            if index_result:
                cur.execute("DROP INDEX IF EXISTS idx_color_profile;")
                db.conn.commit()
                print("✅ Successfully dropped idx_color_profile index")
            else:
                print("ℹ️ idx_color_profile index does not exist - nothing to migrate")
                
        print("\n🎉 Migration completed successfully!")
        print("The color_profile column has been removed from the database.")
        print("The system now uses detailed_colors and color_groups exclusively.")
        return True
        
    except Exception as e:
        db.conn.rollback()
        print(f"❌ Migration failed: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    print("=" * 60)
    print("Database Migration: Remove color_profile column")
    print("=" * 60)
    success = migrate_remove_color_profile()
    sys.exit(0 if success else 1)
