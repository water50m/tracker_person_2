#!/usr/bin/env python3
"""
Migration: Create detection_colors table for 63-color competitive grouping system

This migration:
1. Creates the detection_colors table with structured color data
2. Migrates existing data from detections table (if any)
3. Creates indexes for efficient searching
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


def create_detection_colors_table():
    """Create the detection_colors table"""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            # Create detection_colors table
            cur.execute("""
                CREATE TABLE IF NOT EXISTS detection_colors (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    detection_id UUID REFERENCES detections(id) ON DELETE CASCADE,
                    
                    -- Top 3 colors: [{"name": "red", "percentage": 45.5}, ...]
                    top_colors JSONB NOT NULL DEFAULT '[]',
                    
                    -- 5 category columns for color groups
                    tone_groups JSONB DEFAULT '{}',        -- {"red_tones": 45.5, "blue_tones": 30.0}
                    brightness_groups JSONB DEFAULT '{}',  -- {"light_colors": 15.2}
                    vibrancy_groups JSONB DEFAULT '{}',    -- {"vibrant_colors": 45.5}
                    temperature_groups JSONB DEFAULT '{}', -- {"warm_colors": 45.5}
                    clothing_groups JSONB DEFAULT '{}',    -- {"common_shirt_colors": 45.5}
                    
                    -- Summary for indexing
                    primary_color VARCHAR(50),
                    primary_tone_group VARCHAR(50),
                    
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)
            
            # Create indexes
            cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_detection_colors_detection_id 
                ON detection_colors(detection_id);
            """)
            
            cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_detection_colors_primary_color 
                ON detection_colors(primary_color);
            """)
            
            cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_detection_colors_primary_tone 
                ON detection_colors(primary_tone_group);
            """)
            
            # GIN indexes for JSONB columns
            cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_detection_colors_top_colors 
                ON detection_colors USING gin (top_colors);
            """)
            
            cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_detection_colors_tone_groups 
                ON detection_colors USING gin (tone_groups);
            """)
            
            cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_detection_colors_brightness 
                ON detection_colors USING gin (brightness_groups);
            """)
            
            cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_detection_colors_vibrancy 
                ON detection_colors USING gin (vibrancy_groups);
            """)
            
            cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_detection_colors_temperature 
                ON detection_colors USING gin (temperature_groups);
            """)
            
            conn.commit()
            print("✅ detection_colors table created successfully")
            
    except Exception as e:
        conn.rollback()
        print(f"❌ Error creating detection_colors table: {e}")
        raise
    finally:
        conn.close()


def migrate_existing_data():
    """Migrate existing color data from detections table"""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            # Check if there are any existing detections with color data
            cur.execute("""
                SELECT COUNT(*) FROM detections 
                WHERE detailed_colors IS NOT NULL 
                AND (color_groups IS NOT NULL OR detailed_colors != '{}')
            """)
            count = cur.fetchone()[0]
            
            if count == 0:
                print("ℹ️ No existing color data to migrate")
                return
            
            print(f"🔄 Found {count} detections with color data to migrate")
            
            # Get detections that need migration
            cur.execute("""
                SELECT id, detailed_colors, color_groups, 
                       primary_detailed_color, primary_color_group
                FROM detections 
                WHERE detailed_colors IS NOT NULL 
                AND detailed_colors != '{}'
                AND id NOT IN (SELECT detection_id FROM detection_colors)
            """)
            
            detections = cur.fetchall()
            migrated = 0
            
            for detection_id, detailed_colors, color_groups, primary_detailed, primary_group in detections:
                try:
                    # Convert to new format
                    top_colors = []
                    if detailed_colors:
                        # Get top 3 colors
                        sorted_colors = sorted(
                            detailed_colors.items(), 
                            key=lambda x: x[1], 
                            reverse=True
                        )[:3]
                        top_colors = [
                            {"name": name, "percentage": pct}
                            for name, pct in sorted_colors
                        ]
                    
                    # Categorize color groups
                    tone_groups = {}
                    brightness_groups = {}
                    vibrancy_groups = {}
                    temperature_groups = {}
                    clothing_groups = {}
                    
                    if color_groups:
                        for group_name, percentage in color_groups.items():
                            if group_name.endswith('_tones'):
                                tone_groups[group_name] = percentage
                            elif group_name.endswith('_colors') and group_name in [
                                'light_colors', 'dark_colors', 'medium_colors'
                            ]:
                                brightness_groups[group_name] = percentage
                            elif group_name in ['vibrant_colors', 'muted_colors', 'pastel_colors']:
                                vibrancy_groups[group_name] = percentage
                            elif group_name in ['warm_colors', 'cool_colors', 'neutral_colors']:
                                temperature_groups[group_name] = percentage
                            elif group_name in [
                                'common_shirt_colors', 'common_pants_colors', 
                                'formal_colors', 'casual_colors'
                            ]:
                                clothing_groups[group_name] = percentage
                    
                    # Insert into detection_colors
                    cur.execute("""
                        INSERT INTO detection_colors (
                            detection_id, top_colors,
                            tone_groups, brightness_groups, vibrancy_groups,
                            temperature_groups, clothing_groups,
                            primary_color, primary_tone_group
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """, (
                        detection_id,
                        top_colors,
                        tone_groups,
                        brightness_groups,
                        vibrancy_groups,
                        temperature_groups,
                        clothing_groups,
                        primary_detailed or 'unknown',
                        primary_group or 'unknown'
                    ))
                    
                    migrated += 1
                    
                    if migrated % 100 == 0:
                        conn.commit()
                        print(f"  Migrated {migrated}/{len(detections)}...")
                
                except Exception as e:
                    print(f"  ⚠️ Error migrating detection {detection_id}: {e}")
                    continue
            
            conn.commit()
            print(f"✅ Migrated {migrated} detections to detection_colors table")
            
    except Exception as e:
        conn.rollback()
        print(f"❌ Error migrating data: {e}")
        raise
    finally:
        conn.close()


def verify_migration():
    """Verify the migration was successful"""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            # Check table exists
            cur.execute("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables 
                    WHERE table_name = 'detection_colors'
                );
            """)
            table_exists = cur.fetchone()[0]
            
            if not table_exists:
                print("❌ detection_colors table does not exist")
                return False
            
            # Check indexes
            cur.execute("""
                SELECT indexname FROM pg_indexes 
                WHERE tablename = 'detection_colors'
            """)
            indexes = [row[0] for row in cur.fetchall()]
            
            # Check row count
            cur.execute("SELECT COUNT(*) FROM detection_colors")
            count = cur.fetchone()[0]
            
            print("\n📊 Migration Summary:")
            print(f"  - Table exists: {table_exists}")
            print(f"  - Total rows: {count}")
            print(f"  - Indexes created: {len(indexes)}")
            print(f"  - Indexes: {', '.join(indexes)}")
            
            return True
            
    except Exception as e:
        print(f"❌ Error verifying migration: {e}")
        return False
    finally:
        conn.close()


if __name__ == "__main__":
    print("=" * 60)
    print("Migration: Create detection_colors table")
    print("=" * 60)
    
    try:
        create_detection_colors_table()
        migrate_existing_data()
        verify_migration()
        print("\n✅ Migration completed successfully!")
    except Exception as e:
        print(f"\n❌ Migration failed: {e}")
        sys.exit(1)
