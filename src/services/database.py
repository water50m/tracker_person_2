import psycopg2
from psycopg2.extras import Json
import os
from dotenv import load_dotenv

load_dotenv()

class DatabaseService:
    def __init__(self):
        self.conn = None
        self.connect()

    def connect(self):
        try:
            self.conn = psycopg2.connect(
                host=os.getenv("DB_HOST"),
                port=os.getenv("DB_PORT"),
                database=os.getenv("DB_NAME"),
                user=os.getenv("DB_USER"),
                password=os.getenv("DB_PASS")
            )
            self.conn.autocommit = True
            print("✅ Database Connected!")
            self.setup_tables()
        except Exception as e:
            print(f"\n❌ FATAL ERROR: Database Connection Failed")
            print(f"   Error Details: {e}")
            print("   👉 คำแนะนำ: เช็คไฟล์ .env อีกครั้ง (User, Password, Database Name)\n")
            self.conn = None

    def _ensure_connection(self):
        """ตรวจสอบและเชื่อมต่อ database ใหม่ถ้าจำเป็น"""
        if self.conn is None or self.conn.closed:
            self.connect()

    def setup_tables(self):
        if self.conn is None:
            return
        try:
            with self.conn.cursor() as cur:
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS detections (
                        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                        track_id INT,
                        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        image_path TEXT,
                        clothing_category VARCHAR(50),
                        class_name VARCHAR(100),
                        camera_id VARCHAR(50)
                    );
                    
                    CREATE TABLE IF NOT EXISTS processed_videos (
                        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                        camera_id VARCHAR(50),
                        label VARCHAR(100),
                        filename VARCHAR(255),
                        file_path TEXT,
                        status VARCHAR(20) DEFAULT 'processing',
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    );
                    
                    CREATE TABLE IF NOT EXISTS cameras (
                        id SERIAL PRIMARY KEY,
                        name VARCHAR(100) UNIQUE NOT NULL,
                        source_url TEXT,
                        is_active BOOLEAN DEFAULT true,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    );
                """)
                cur.execute("ALTER TABLE detections ADD COLUMN IF NOT EXISTS video_time_offset DOUBLE PRECISION;")
                cur.execute("ALTER TABLE detections ADD COLUMN IF NOT EXISTS video_id TEXT;")
                try:
                    cur.execute("ALTER TABLE detections ALTER COLUMN video_id TYPE TEXT USING video_id::text;")
                except Exception:
                    pass
                
                # Add width and height columns to processed_videos
                cur.execute("ALTER TABLE processed_videos ADD COLUMN IF NOT EXISTS width INT;")
                cur.execute("ALTER TABLE processed_videos ADD COLUMN IF NOT EXISTS height INT;")
                
                # Add progress column for resume functionality
                cur.execute("ALTER TABLE processed_videos ADD COLUMN IF NOT EXISTS progress INT DEFAULT 0;")
                
                # เพิ่มคอลัมน์สำหรับระบบสีใหม่
                cur.execute("ALTER TABLE detections ADD COLUMN IF NOT EXISTS detailed_colors JSONB;")
                cur.execute("ALTER TABLE detections ADD COLUMN IF NOT EXISTS color_groups JSONB;")
                cur.execute("ALTER TABLE detections ADD COLUMN IF NOT EXISTS primary_detailed_color VARCHAR(50);")
                cur.execute("ALTER TABLE detections ADD COLUMN IF NOT EXISTS primary_color_group VARCHAR(50);")
                cur.execute("ALTER TABLE detections ADD COLUMN IF NOT EXISTS clothes JSONB;")
                cur.execute("ALTER TABLE detections ADD COLUMN IF NOT EXISTS bbox JSONB;")
                
                # เพิ่มคอลัมน์สำหรับ Re-ID embedding
                cur.execute("ALTER TABLE detections ADD COLUMN IF NOT EXISTS embedding JSONB;")
                cur.execute("CREATE INDEX IF NOT EXISTS idx_embedding ON detections USING gin (embedding);")
                
                # สร้าง index สำหรับการค้นหาสี
                cur.execute("CREATE INDEX IF NOT EXISTS idx_detailed_colors ON detections USING gin (detailed_colors);")
                cur.execute("CREATE INDEX IF NOT EXISTS idx_color_groups ON detections USING gin (color_groups);")
                cur.execute("CREATE INDEX IF NOT EXISTS idx_primary_detailed_color ON detections (primary_detailed_color);")
                cur.execute("CREATE INDEX IF NOT EXISTS idx_primary_color_group ON detections (primary_color_group);")
                
                # Create detection_items table for new schema
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS detection_items (
                        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                        detection_id UUID REFERENCES detections(id) ON DELETE CASCADE,
                        item_index INT NOT NULL,
                        class_name VARCHAR(100) NOT NULL,
                        category VARCHAR(50) NOT NULL,
                        confidence FLOAT NOT NULL,
                        bbox JSONB,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        UNIQUE(detection_id, item_index)
                    );
                """)
                cur.execute("CREATE INDEX IF NOT EXISTS idx_detection_items_detection_id ON detection_items(detection_id);")
                cur.execute("CREATE INDEX IF NOT EXISTS idx_detection_items_category ON detection_items(category);")
                cur.execute("CREATE INDEX IF NOT EXISTS idx_detection_items_class_name ON detection_items(class_name);")
                
                # Create detection_colors table with new schema (detection_item_id support)
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS detection_colors (
                        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                        detection_id UUID REFERENCES detections(id) ON DELETE CASCADE,
                        detection_item_id UUID REFERENCES detection_items(id) ON DELETE CASCADE,
                        top_colors JSONB,
                        brightness_groups JSONB,
                        vibrancy_groups JSONB,
                        temperature_groups JSONB,
                        clothing_groups JSONB,
                        primary_color VARCHAR(50),
                        primary_tone_group VARCHAR(50),
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    );
                """)
                cur.execute("CREATE INDEX IF NOT EXISTS idx_detection_colors_detection_id ON detection_colors(detection_id);")
                cur.execute("CREATE INDEX IF NOT EXISTS idx_detection_colors_detection_item_id ON detection_colors(detection_item_id);")
        except Exception as e:
            print(f"❌ Setup Tables Failed: {e}")
    
    def register_video(self, camera_id: str, label: str, filename: str, file_path: str, width: int = None, height: int = None):
        query = """
            INSERT INTO processed_videos (camera_id, label, filename, file_path, status, width, height)
            VALUES (%s, %s, %s, %s, 'processing', %s, %s)
            RETURNING id;
        """
        try:
            self._ensure_connection()
            with self.conn.cursor() as cur:
                cur.execute(query, (camera_id, label, filename, file_path, width, height))
                video_id = cur.fetchone()[0]
                self.conn.commit()
                print(f"🎬 Video registered in DB with ID: {video_id}")
                return video_id
        except Exception as e:
            self.conn.rollback()
            print(f"❌ Error registering video: {e}")
            return None

    def update_video_status(self, video_id, status: str):
        # Convert UUID objects to strings for psycopg2
        if hasattr(video_id, 'hex'):
            video_id = str(video_id)

        query = "UPDATE processed_videos SET status = %s WHERE id = %s"
        try:
            self._ensure_connection()
            with self.conn.cursor() as cur:
                cur.execute(query, (status, video_id))
                self.conn.commit()
        except Exception as e:
            self.conn.rollback()
            print(f"❌ Error updating video status: {e}")

    def insert_detection(self, *, camera_id, track_id, class_name, image_path, category=None, video_time_offset=None, video_id=None, bbox=None, embedding=None):
        """
        บันทึกการตรวจจับพื้นฐาน (ไม่รวมข้อมูลสี - ข้อมูลสีจะบันทึกใน detection_colors table)
        """
        query = """
            INSERT INTO detections (
                camera_id, track_id, clothing_category, class_name,
                bbox, image_path, video_time_offset, video_id, embedding
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
        """
        try:
            self._ensure_connection()
            with self.conn.cursor() as cur:
                cur.execute(query, (
                    camera_id, track_id, category, class_name,
                    Json(bbox) if bbox else None,
                    image_path, video_time_offset, video_id,
                    Json(embedding) if embedding is not None else None,
                ))
                detection_id = cur.fetchone()[0]
                self.conn.commit()
                return detection_id
        except Exception as e:
            self.conn.rollback()
            print(f"❌ Database Insert Error: {e}")
            return None

    def insert_detections_batch(self, batch):
        """บันทึกการตรวจจับหลายรายการพร้อมกัน (batch insert)"""
        if not batch:
            return
        query = """
            INSERT INTO detections (
                camera_id, track_id, clothing_category, class_name,
                bbox, image_path, video_time_offset, video_id, embedding
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        """
        try:
            self._ensure_connection()
            with self.conn.cursor() as cur:
                values = []
                for row in batch:
                    values.append((
                        row.get("camera_id"),
                        row.get("track_id"),
                        row.get("category"),
                        row.get("class_name"),
                        Json(row.get("bbox")) if row.get("bbox") else None,
                        row.get("image_path", ""),
                        row.get("video_time_offset"),
                        row.get("video_id"),
                        Json(row.get("embedding")) if row.get("embedding") is not None else None,
                    ))
                cur.executemany(query, values)
                self.conn.commit()
        except Exception as e:
            self.conn.rollback()
            print(f"❌ Database Batch Insert Error: {e}")

    def close(self):
        if self.conn:
            self.conn.close()

    def search_by_detailed_color(self, color_name, limit=100):
        """ค้นหาคนตามสีละเอียด"""
        query = """
            SELECT * FROM detections 
            WHERE detailed_colors ? %s
            ORDER BY timestamp DESC
            LIMIT %s
        """
        try:
            self._ensure_connection()
            with self.conn.cursor() as cur:
                cur.execute(query, (color_name, limit))
                columns = [desc[0] for desc in cur.description]
                return [dict(zip(columns, row)) for row in cur.fetchall()]
        except Exception as e:
            print(f"❌ Search Error: {e}")
            return []

    def search_by_color_group(self, group_name, limit=100):
        """ค้นหาคนตามกลุ่มสี"""
        query = """
            SELECT * FROM detections 
            WHERE color_groups ? %s
            ORDER BY timestamp DESC
            LIMIT %s
        """
        try:
            self._ensure_connection()
            with self.conn.cursor() as cur:
                cur.execute(query, (group_name, limit))
                columns = [desc[0] for desc in cur.description]
                return [dict(zip(columns, row)) for row in cur.fetchall()]
        except Exception as e:
            print(f"❌ Search Error: {e}")
            return []

    def search_by_clothes(self, clothing_item, limit=100):
        """ค้นหาคนตามเสื้อผ้า"""
        query = """
            SELECT * FROM detections 
            WHERE clothes @> %s::jsonb
            ORDER BY timestamp DESC
            LIMIT %s
        """
        try:
            self._ensure_connection()
            with self.conn.cursor() as cur:
                cur.execute(query, (Json([clothing_item]), limit))
                columns = [desc[0] for desc in cur.description]
                return [dict(zip(columns, row)) for row in cur.fetchall()]
        except Exception as e:
            print(f"❌ Search Error: {e}")
            return []

    def search_by_embedding(self, query_embedding, threshold=0.7, limit=100):
        """
        ค้นหาคนที่คล้ายกันด้วย embedding similarity (cosine similarity)
        
        Args:
            query_embedding: list/numpy array ของ embedding (768-dim)
            threshold: ค่า similarity ขั้นต่ำ (0-1)
            limit: จำนวนผลลัพธ์สูงสุด
        """
        import numpy as np
        
        try:
            self._ensure_connection()
            with self.conn.cursor() as cur:
                # ดึงทุก detection ที่มี embedding แล้วคำนวณ cosine similarity
                cur.execute("""
                    SELECT * FROM detections 
                    WHERE embedding IS NOT NULL
                    ORDER BY timestamp DESC
                    LIMIT 1000
                """)
                columns = [desc[0] for desc in cur.description]
                rows = cur.fetchall()
                
                # คำนวณ cosine similarity
                query_vec = np.array(query_embedding)
                query_norm = np.linalg.norm(query_vec)
                
                results = []
                for row in rows:
                    row_dict = dict(zip(columns, row))
                    emb = row_dict.get('embedding')
                    if emb:
                        emb_vec = np.array(emb)
                        emb_norm = np.linalg.norm(emb_vec)
                        if emb_norm > 0 and query_norm > 0:
                            similarity = np.dot(query_vec, emb_vec) / (query_norm * emb_norm)
                            if similarity >= threshold:
                                row_dict['similarity'] = float(similarity)
                                results.append(row_dict)
                
                # Sort by similarity and return top results
                results.sort(key=lambda x: x['similarity'], reverse=True)
                return results[:limit]
                
        except Exception as e:
            print(f"❌ Search by Embedding Error: {e}")
            return []

    def get_person_detections(self, track_id, camera_id=None, limit=100):
        """
        ดึงทุก detection ของคนๆ หนึ่ง (ตาม track_id) สำหรับ Re-ID
        """
        try:
            self._ensure_connection()
            with self.conn.cursor() as cur:
                if camera_id:
                    cur.execute("""
                        SELECT * FROM detections 
                        WHERE track_id = %s AND camera_id = %s
                        ORDER BY timestamp DESC
                        LIMIT %s
                    """, (track_id, camera_id, limit))
                else:
                    cur.execute("""
                        SELECT * FROM detections 
                        WHERE track_id = %s
                        ORDER BY timestamp DESC
                        LIMIT %s
                    """, (track_id, limit))
                columns = [desc[0] for desc in cur.description]
                return [dict(zip(columns, row)) for row in cur.fetchall()]
        except Exception as e:
            print(f"❌ Get Person Detections Error: {e}")
            return []

    def get_video_progress(self, video_id):
        """Get the last processed frame number for a video to enable resume functionality."""
        if not video_id:
            return 0
        try:
            self._ensure_connection()
            with self.conn.cursor() as cur:
                cur.execute(
                    "SELECT progress FROM processed_videos WHERE id = %s",
                    (video_id,)
                )
                result = cur.fetchone()
                return result[0] if result and result[0] else 0
        except Exception as e:
            print(f"❌ Get Video Progress Error: {e}")
            return 0

    def update_video_progress(self, video_id, progress, status=None):
        """Update the processing progress for a video."""
        if not video_id:
            return

        # Convert UUID objects to strings for psycopg2
        if hasattr(video_id, 'hex'):
            video_id = str(video_id)

        try:
            self._ensure_connection()
            with self.conn.cursor() as cur:
                if status:
                    cur.execute(
                        "UPDATE processed_videos SET progress = %s, status = %s WHERE id = %s",
                        (progress, status, video_id)
                    )
                else:
                    cur.execute(
                        "UPDATE processed_videos SET progress = %s WHERE id = %s",
                        (progress, video_id)
                    )
                self.conn.commit()
        except Exception as e:
            self.conn.rollback()
            print(f"❌ Update Video Progress Error: {e}")

    # ============================================
    # 🎨 Detection Colors Methods
    # ============================================

    def insert_detection_colors(self, detection_id: str = None, detection_item_id: str = None,
                                 top_colors: list = None,
                                 brightness_groups: dict = None, vibrancy_groups: dict = None,
                                 temperature_groups: dict = None, clothing_groups: dict = None,
                                 primary_color: str = None, primary_tone_group: str = None):
        """
        Insert color data into detection_colors table
        
        Supports both old schema (detection_id only) and new schema (detection_item_id).
        For new data, provide detection_item_id. For backward compatibility, detection_id can be provided.
        
        Args:
            detection_id: UUID of the parent detection (optional, for backward compatibility)
            detection_item_id: UUID of the detection item (optional, new schema)
            top_colors: List of top 3 colors [{"name": "red", "percentage": 45.5}, ...]
            brightness_groups: Dict of brightness groups {"light_colors": 15.2, ...}
            vibrancy_groups: Dict of vibrancy groups {"vibrant_colors": 45.5, ...}
            temperature_groups: Dict of temperature groups {"warm_colors": 45.5, ...}
            clothing_groups: Dict of clothing groups {"common_shirt_colors": 45.5, ...}
            primary_color: Primary detailed color name
            primary_tone_group: Primary tone group name
        """
        query = """
            INSERT INTO detection_colors (
                detection_id, detection_item_id, top_colors,
                brightness_groups, vibrancy_groups,
                temperature_groups, clothing_groups,
                primary_color, primary_tone_group
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        """
        try:
            self._ensure_connection()
            with self.conn.cursor() as cur:
                cur.execute(query, (
                    detection_id,
                    detection_item_id,
                    Json(top_colors if top_colors else []),
                    Json(brightness_groups if brightness_groups else {}),
                    Json(vibrancy_groups if vibrancy_groups else {}),
                    Json(temperature_groups if temperature_groups else {}),
                    Json(clothing_groups if clothing_groups else {}),
                    primary_color,
                    primary_tone_group
                ))
                self.conn.commit()
        except Exception as e:
            self.conn.rollback()
            print(f"❌ Detection Colors Insert Error: {e}")

    def insert_detection_items(self, detection_id: str, items: list):
        """
        Insert multiple clothing items for a detection and return their IDs
        
        Args:
            detection_id: UUID of the parent detection
            items: List of item dicts with keys:
                - item_index: 1 or 2
                - class_name: e.g., "long_sleeve", "short_sleeve", "skirt"
                - category: "TOP" or "BOTTOM"
                - confidence: float
                - bbox: [x1, y1, x2, y2] relative to person_crop (optional)
        
        Returns:
            list: UUIDs of inserted detection_items in order
        """
        query = """
            INSERT INTO detection_items (
                detection_id, item_index, class_name, category, confidence, bbox
            ) VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING id
        """
        try:
            self._ensure_connection()
            with self.conn.cursor() as cur:
                item_ids = []
                for item in items:
                    cur.execute(query, (
                        detection_id,
                        item.get("item_index"),
                        item.get("class_name"),
                        item.get("category"),
                        item.get("confidence"),
                        Json(item.get("bbox")) if item.get("bbox") else None
                    ))
                    item_id = cur.fetchone()[0]
                    item_ids.append(item_id)
                self.conn.commit()
                return item_ids
        except Exception as e:
            self.conn.rollback()
            print(f"❌ Detection Items Insert Error: {e}")
            return []

    def get_detection_colors(self, detection_id: str):
        """
        Get color data for a specific detection (backward compatibility)
        
        Args:
            detection_id: UUID of the detection
            
        Returns:
            dict: Color data or None if not found
        """
        query = """
            SELECT * FROM detection_colors WHERE detection_id = %s
        """
        try:
            self._ensure_connection()
            with self.conn.cursor() as cur:
                cur.execute(query, (detection_id,))
                row = cur.fetchone()
                if row:
                    columns = [desc[0] for desc in cur.description]
                    return dict(zip(columns, row))
                return None
        except Exception as e:
            print(f"❌ Get Detection Colors Error: {e}")
            return None

    def get_detection_colors_by_item(self, detection_item_id: str):
        """
        Get color data for a specific detection item (new schema)
        
        Args:
            detection_item_id: UUID of the detection item
            
        Returns:
            dict: Color data or None if not found
        """
        query = """
            SELECT * FROM detection_colors WHERE detection_item_id = %s
        """
        try:
            self._ensure_connection()
            with self.conn.cursor() as cur:
                cur.execute(query, (detection_item_id,))
                row = cur.fetchone()
                if row:
                    columns = [desc[0] for desc in cur.description]
                    return dict(zip(columns, row))
                return None
        except Exception as e:
            print(f"❌ Get Detection Colors by Item Error: {e}")
            return None

    def get_detection_items(self, detection_id: str):
        """
        Get all detection items for a specific detection
        
        Args:
            detection_id: UUID of the detection
            
        Returns:
            list: List of detection item dicts, ordered by item_index
        """
        query = """
            SELECT * FROM detection_items 
            WHERE detection_id = %s 
            ORDER BY item_index ASC
        """
        try:
            self._ensure_connection()
            with self.conn.cursor() as cur:
                cur.execute(query, (detection_id,))
                columns = [desc[0] for desc in cur.description]
                rows = cur.fetchall()
                return [dict(zip(columns, row)) for row in rows]
        except Exception as e:
            print(f"❌ Get Detection Items Error: {e}")
            return []

    # ============================================
    # 🔍 Enhanced Color Search Methods
    # ============================================

    def search_by_tone_group(self, group_name: str, limit: int = 100, min_percentage: float = 5.0):
        """
        Search detections by tone group (red_tones, blue_tones, etc.)
        
        Args:
            group_name: Name of the tone group (e.g., "red_tones", "blue_tones")
            limit: Maximum number of results
            min_percentage: Minimum percentage threshold
            
        Returns:
            list: Detection records with color data
        """
        query = """
            SELECT d.*, dc.top_colors, dc.tone_groups, dc.primary_color, dc.primary_tone_group
            FROM detections d
            JOIN detection_items di ON d.id = di.detection_id
            JOIN detection_colors dc ON di.id = dc.detection_item_id
            WHERE dc.tone_groups->>%s IS NOT NULL
            AND (dc.tone_groups->>%s)::float >= %s
            ORDER BY (dc.tone_groups->>%s)::float DESC
            LIMIT %s
        """
        try:
            self._ensure_connection()
            with self.conn.cursor() as cur:
                cur.execute(query, (group_name, group_name, min_percentage, group_name, limit))
                columns = [desc[0] for desc in cur.description]
                return [dict(zip(columns, row)) for row in cur.fetchall()]
        except Exception as e:
            print(f"❌ Search by Tone Group Error: {e}")
            return []

    def search_by_temperature(self, temp_type: str, limit: int = 100, min_percentage: float = 5.0):
        """
        Search detections by temperature (warm_colors, cool_colors, neutral_colors)
        
        Args:
            temp_type: Temperature type ("warm", "cool", "neutral")
            limit: Maximum number of results
            min_percentage: Minimum percentage threshold
            
        Returns:
            list: Detection records with color data
        """
        group_map = {
            "warm": "warm_colors",
            "cool": "cool_colors",
            "neutral": "neutral_colors"
        }
        group_name = group_map.get(temp_type.lower(), temp_type.lower() + "_colors")
        
        query = """
            SELECT d.*, dc.top_colors, dc.temperature_groups, dc.primary_color
            FROM detections d
            JOIN detection_items di ON d.id = di.detection_id
            JOIN detection_colors dc ON di.id = dc.detection_item_id
            WHERE dc.temperature_groups->>%s IS NOT NULL
            AND (dc.temperature_groups->>%s)::float >= %s
            ORDER BY (dc.temperature_groups->>%s)::float DESC
            LIMIT %s
        """
        try:
            self._ensure_connection()
            with self.conn.cursor() as cur:
                cur.execute(query, (group_name, group_name, min_percentage, group_name, limit))
                columns = [desc[0] for desc in cur.description]
                return [dict(zip(columns, row)) for row in cur.fetchall()]
        except Exception as e:
            print(f"❌ Search by Temperature Error: {e}")
            return []

    def search_by_vibrancy(self, vibrancy_type: str, limit: int = 100, min_percentage: float = 5.0):
        """
        Search detections by vibrancy (vibrant_colors, muted_colors, pastel_colors)
        
        Args:
            vibrancy_type: Vibrancy type ("vibrant", "muted", "pastel")
            limit: Maximum number of results
            min_percentage: Minimum percentage threshold
            
        Returns:
            list: Detection records with color data
        """
        group_map = {
            "vibrant": "vibrant_colors",
            "muted": "muted_colors",
            "pastel": "pastel_colors"
        }
        group_name = group_map.get(vibrancy_type.lower(), vibrancy_type.lower() + "_colors")
        
        query = """
            SELECT d.*, dc.top_colors, dc.vibrancy_groups, dc.primary_color
            FROM detections d
            JOIN detection_items di ON d.id = di.detection_id
            JOIN detection_colors dc ON di.id = dc.detection_item_id
            WHERE dc.vibrancy_groups->>%s IS NOT NULL
            AND (dc.vibrancy_groups->>%s)::float >= %s
            ORDER BY (dc.vibrancy_groups->>%s)::float DESC
            LIMIT %s
        """
        try:
            self._ensure_connection()
            with self.conn.cursor() as cur:
                cur.execute(query, (group_name, group_name, min_percentage, group_name, limit))
                columns = [desc[0] for desc in cur.description]
                return [dict(zip(columns, row)) for row in cur.fetchall()]
        except Exception as e:
            print(f"❌ Search by Vibrancy Error: {e}")
            return []

    def search_by_brightness(self, brightness_type: str, limit: int = 100, min_percentage: float = 5.0):
        """
        Search detections by brightness (light_colors, dark_colors, medium_colors)
        
        Args:
            brightness_type: Brightness type ("light", "dark", "medium")
            limit: Maximum number of results
            min_percentage: Minimum percentage threshold
            
        Returns:
            list: Detection records with color data
        """
        group_map = {
            "light": "light_colors",
            "dark": "dark_colors",
            "medium": "medium_colors"
        }
        group_name = group_map.get(brightness_type.lower(), brightness_type.lower() + "_colors")
        
        query = """
            SELECT d.*, dc.top_colors, dc.brightness_groups, dc.primary_color
            FROM detections d
            JOIN detection_items di ON d.id = di.detection_id
            JOIN detection_colors dc ON di.id = dc.detection_item_id
            WHERE dc.brightness_groups->>%s IS NOT NULL
            AND (dc.brightness_groups->>%s)::float >= %s
            ORDER BY (dc.brightness_groups->>%s)::float DESC
            LIMIT %s
        """
        try:
            self._ensure_connection()
            with self.conn.cursor() as cur:
                cur.execute(query, (group_name, group_name, min_percentage, group_name, limit))
                columns = [desc[0] for desc in cur.description]
                return [dict(zip(columns, row)) for row in cur.fetchall()]
        except Exception as e:
            print(f"❌ Search by Brightness Error: {e}")
            return []

    def search_by_clothing_group(self, group_name: str, limit: int = 100, min_percentage: float = 5.0):
        """
        Search detections by clothing group (common_shirt_colors, formal_colors, etc.)
        
        Args:
            group_name: Clothing group name
            limit: Maximum number of results
            min_percentage: Minimum percentage threshold
            
        Returns:
            list: Detection records with color data
        """
        query = """
            SELECT d.*, dc.top_colors, dc.clothing_groups, dc.primary_color
            FROM detections d
            JOIN detection_items di ON d.id = di.detection_id
            JOIN detection_colors dc ON di.id = dc.detection_item_id
            WHERE dc.clothing_groups->>%s IS NOT NULL
            AND (dc.clothing_groups->>%s)::float >= %s
            ORDER BY (dc.clothing_groups->>%s)::float DESC
            LIMIT %s
        """
        try:
            self._ensure_connection()
            with self.conn.cursor() as cur:
                cur.execute(query, (group_name, group_name, min_percentage, group_name, limit))
                columns = [desc[0] for desc in cur.description]
                return [dict(zip(columns, row)) for row in cur.fetchall()]
        except Exception as e:
            print(f"❌ Search by Clothing Group Error: {e}")
            return []

    def search_by_color_advanced(self, tone_groups=None, temperature=None, 
                                  brightness=None, vibrancy=None, 
                                  clothing_groups=None, limit=100):
        """
        Advanced color search with multiple category filters
        
        Args:
            tone_groups: List of tone group names (e.g., ["red_tones", "blue_tones"])
            temperature: Temperature type ("warm", "cool", "neutral")
            brightness: Brightness type ("light", "dark", "medium")
            vibrancy: Vibrancy type ("vibrant", "muted", "pastel")
            clothing_groups: List of clothing group names
            limit: Maximum number of results
            
        Returns:
            list: Detection records matching all criteria
        """
        conditions = []
        params = []
        
        # Build conditions dynamically
        if tone_groups:
            for group in tone_groups:
                conditions.append("dc.tone_groups->>%s IS NOT NULL")
                params.append(group)
        
        if temperature:
            temp_map = {"warm": "warm_colors", "cool": "cool_colors", "neutral": "neutral_colors"}
            group_name = temp_map.get(temperature.lower())
            if group_name:
                conditions.append("dc.temperature_groups->>%s IS NOT NULL")
                params.append(group_name)
        
        if brightness:
            bright_map = {"light": "light_colors", "dark": "dark_colors", "medium": "medium_colors"}
            group_name = bright_map.get(brightness.lower())
            if group_name:
                conditions.append("dc.brightness_groups->>%s IS NOT NULL")
                params.append(group_name)
        
        if vibrancy:
            vibrancy_map = {"vibrant": "vibrant_colors", "muted": "muted_colors", "pastel": "pastel_colors"}
            group_name = vibrancy_map.get(vibrancy.lower())
            if group_name:
                conditions.append("dc.vibrancy_groups->>%s IS NOT NULL")
                params.append(group_name)
        
        if clothing_groups:
            for group in clothing_groups:
                conditions.append("dc.clothing_groups->>%s IS NOT NULL")
                params.append(group)
        
        if not conditions:
            # No filters specified, return empty
            return []
        
        query = f"""
            SELECT d.*, dc.top_colors, dc.tone_groups, dc.temperature_groups,
                   dc.brightness_groups, dc.vibrancy_groups, dc.clothing_groups,
                   dc.primary_color, dc.primary_tone_group
            FROM detections d
            JOIN detection_items di ON d.id = di.detection_id
            JOIN detection_colors dc ON di.id = dc.detection_item_id
            WHERE {" AND ".join(conditions)}
            ORDER BY d.timestamp DESC
            LIMIT %s
        """
        params.append(limit)
        
        try:
            self._ensure_connection()
            with self.conn.cursor() as cur:
                cur.execute(query, tuple(params))
                columns = [desc[0] for desc in cur.description]
                return [dict(zip(columns, row)) for row in cur.fetchall()]
        except Exception as e:
            print(f"❌ Advanced Color Search Error: {e}")
            return []

    def resolve_camera_id(self, camera_name: str) -> int:
        """
        Resolve camera name to camera ID. If camera doesn't exist, create it.
        
        Args:
            camera_name: The name of the camera (e.g., "CAM-01", "FrontDoor")
            
        Returns:
            int: The camera ID from the database
        """
        if not camera_name or not camera_name.strip():
            raise ValueError("Camera name cannot be empty")
        
        camera_name = camera_name.strip()
        
        try:
            self._ensure_connection()
            with self.conn.cursor() as cur:
                # First, try to find existing camera by name
                cur.execute("SELECT id FROM cameras WHERE name = %s", (camera_name,))
                result = cur.fetchone()
                
                if result:
                    # Camera exists, return its ID
                    return result[0]
                
                # Camera doesn't exist, create it
                cur.execute("""
                    INSERT INTO cameras (name, source_url, is_active) 
                    VALUES (%s, NULL, true) 
                    RETURNING id
                """, (camera_name,))
                new_id = cur.fetchone()[0]
                self.conn.commit()
                print(f"✅ Created new camera: {camera_name} (ID: {new_id})")
                return new_id
                
        except Exception as e:
            self.conn.rollback()
            print(f"❌ Error resolving camera ID: {e}")
            raise

if __name__ == "__main__":
    db = DatabaseService()
