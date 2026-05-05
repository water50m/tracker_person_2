#!/usr/bin/env python3
"""
Migration: Create detection_items table for multi-clothing support

This migration:
1. Creates the detection_items table to store individual clothing items per detection
2. Modifies detection_colors table to add detection_item_id column
3. Creates indexes for efficient searching
4. Implements backward compatibility - keeps detection_id nullable

Schema:
- detection: 1 row per person detection
- detection_items: 1-2 rows per detection (max 2 items: 1 TOP + 1 BOTTOM)
- detection_colors: 1 row per detection_item (color data per clothing item)
"""

import os
import sys
import psycopg2
from dotenv import load_dotenv

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

load_dotenv()


def get_connection():
    """Get database connection"""
    return psycopg2.connect(
        host=os.getenv("DB_HOST"),
        port=os.getenv("DB_PORT"),
        database=os.getenv("DB_NAME"),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASS")
    )


def create_detection_items_table():
    """Create the detection_items table"""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            # Create detection_items table
            cur.execute("""
                CREATE TABLE IF NOT EXISTS detection_items (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    detection_id UUID REFERENCES detections(id) ON DELETE CASCADE,
                    item_index INT NOT NULL,  -- 1 or 2
                    
                    -- Clothing classification
                    class_name VARCHAR(100) NOT NULL,
                    category VARCHAR(50) NOT NULL,  -- TOP or BOTTOM
                    confidence FLOAT NOT NULL,
                    bbox JSONB,  -- [x1, y1, x2, y2] relative to person_crop
                    
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    
                    UNIQUE(detection_id, item_index)
                );
            """)
            print("✅ Created detection_items table")
            
            # Create indexes for detection_items
            cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_detection_items_detection_id 
                ON detection_items(detection_id);
            """)
            
            cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_detection_items_category 
                ON detection_items(category);
            """)
            
            cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_detection_items_class_name 
                ON detection_items(class_name);
            """)
            print("✅ Created indexes on detection_items")
            
            # Modify detection_colors table for new schema
            # Add detection_item_id column (nullable for backward compatibility)
            cur.execute("""
                ALTER TABLE detection_colors 
                ADD COLUMN IF NOT EXISTS detection_item_id UUID REFERENCES detection_items(id) ON DELETE CASCADE;
            """)
            print("✅ Added detection_item_id column to detection_colors")
            
            # Create index for the new column
            cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_detection_colors_detection_item_id 
                ON detection_colors(detection_item_id);
            """)
            print("✅ Created index on detection_colors(detection_item_id)")
            
            # Make detection_id nullable for backward compatibility
            # This allows old data to continue working while new data uses detection_item_id
            try:
                cur.execute("""
                    ALTER TABLE detection_colors 
                    ALTER COLUMN detection_id DROP NOT NULL;
                """)
                print("✅ Made detection_id nullable for backward compatibility")
            except Exception as e:
                print(f"ℹ️ detection_id already nullable or constraint not found: {e}")
            
            conn.commit()
            print("\n✅ Migration completed successfully!")
            print("   - detection_items table created")
            print("   - detection_colors updated with detection_item_id")
            print("   - Backward compatibility maintained (detection_id remains nullable)")
            
    except Exception as e:
        conn.rollback()
        print(f"❌ Migration failed: {e}")
        raise
    finally:
        conn.close()


def verify_migration():
    """Verify the migration was successful"""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            # Check detection_items table exists
            cur.execute("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables 
                    WHERE table_schema = 'public' 
                    AND table_name = 'detection_items'
                );
            """)
            items_exists = cur.fetchone()[0]
            
            # Check detection_item_id column exists
            cur.execute("""
                SELECT EXISTS (
                    SELECT FROM information_schema.columns 
                    WHERE table_schema = 'public' 
                    AND table_name = 'detection_colors' 
                    AND column_name = 'detection_item_id'
                );
            """)
            column_exists = cur.fetchone()[0]
            
            if items_exists and column_exists:
                print("\n✅ Migration verified: All tables and columns created successfully")
                return True
            else:
                print(f"\n❌ Migration verification failed:")
                print(f"   - detection_items table exists: {items_exists}")
                print(f"   - detection_item_id column exists: {column_exists}")
                return False
                
    finally:
        conn.close()


if __name__ == "__main__":
    print("=" * 60)
    print("Migration: Create detection_items table")
    print("=" * 60)
    
    create_detection_items_table()
    verify_migration()
