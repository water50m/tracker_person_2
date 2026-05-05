"""
Migration: Remove tone_groups and primary_tone_group columns from detection_colors table
Run this script to migrate existing databases to remove redundant tone group storage
"""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.services.database import DatabaseService

def migrate_remove_tone_groups():
    """Remove tone_groups and primary_tone_group columns from detection_colors table"""
    db = DatabaseService()
    
    if db.conn is None:
        print("❌ Cannot connect to database. Migration aborted.")
        return False
    
    try:
        with db.conn.cursor() as cur:
            # Check if tone_groups column exists in detection_colors table
            cur.execute("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name = 'detection_colors' AND column_name = 'tone_groups'
            """)
            tone_groups_result = cur.fetchone()
            
            if tone_groups_result:
                # Remove tone_groups column
                cur.execute("ALTER TABLE detection_colors DROP COLUMN tone_groups;")
                db.conn.commit()
                print("✅ Successfully removed tone_groups column from detection_colors table")
            else:
                print("ℹ️ tone_groups column does not exist in detection_colors - nothing to migrate")
            
            # Check if primary_tone_group column exists in detection_colors table
            cur.execute("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name = 'detection_colors' AND column_name = 'primary_tone_group'
            """)
            primary_tone_result = cur.fetchone()
            
            if primary_tone_result:
                # Remove primary_tone_group column
                cur.execute("ALTER TABLE detection_colors DROP COLUMN primary_tone_group;")
                db.conn.commit()
                print("✅ Successfully removed primary_tone_group column from detection_colors table")
            else:
                print("ℹ️ primary_tone_group column does not exist in detection_colors - nothing to migrate")
            
            # Drop indexes related to tone_groups if they exist
            cur.execute("""
                SELECT indexname 
                FROM pg_indexes 
                WHERE tablename = 'detection_colors' AND indexname = 'idx_detection_colors_tone_groups'
            """)
            tone_index_result = cur.fetchone()
            
            if tone_index_result:
                cur.execute("DROP INDEX IF EXISTS idx_detection_colors_tone_groups;")
                db.conn.commit()
                print("✅ Successfully dropped idx_detection_colors_tone_groups index")
            else:
                print("ℹ️ idx_detection_colors_tone_groups index does not exist - nothing to migrate")
            
            # Drop index for primary_tone_group if it exists
            cur.execute("""
                SELECT indexname 
                FROM pg_indexes 
                WHERE tablename = 'detection_colors' AND indexname = 'idx_detection_colors_primary_tone'
            """)
            primary_tone_index_result = cur.fetchone()
            
            if primary_tone_index_result:
                cur.execute("DROP INDEX IF EXISTS idx_detection_colors_primary_tone;")
                db.conn.commit()
                print("✅ Successfully dropped idx_detection_colors_primary_tone index")
            else:
                print("ℹ️ idx_detection_colors_primary_tone index does not exist - nothing to migrate")
                
        print("\n🎉 Migration completed successfully!")
        print("The tone_groups and primary_tone_group columns have been removed from detection_colors table.")
        print("Tone groups are now calculated dynamically from detailed_colors using the new 10-tone system.")
        return True
        
    except Exception as e:
        db.conn.rollback()
        print(f"❌ Migration failed: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    print("=" * 60)
    print("Database Migration: Remove tone_groups columns")
    print("=" * 60)
    success = migrate_remove_tone_groups()
    sys.exit(0 if success else 1)
