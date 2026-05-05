from typing import List, Optional
from src.services.database import DatabaseService
from src.api.schemas import SearchCriteria, DetectionResponse, PersonTimeline, DailyStats, ClothingStats
from datetime import datetime
import cv2
import numpy as np
import os
import sys
from pathlib import Path

# Add parent directory for imports (for Feature Flag and ImageAnalyzer)
sys.path.insert(0, str(Path(__file__).parent.parent))

# Feature Flag imports
from config_loader import use_refactored_image_analyzer

class DetectionController:
    def __init__(self):
        self.db = DatabaseService()
        self.minio_base = os.getenv("MINIO_BASE_URL", "http://myserver:9000")
        self._image_analyzer = None  # Lazy initialization for refactored code

    def _get_select_columns(self):
        """ Helper เพื่อให้ SQL Select ข้อมูลลำดับเดียวกันเสมอ """
        return """d.id, d.track_id, d.timestamp, d.image_path, d.clothing_category, d.class_name, 
                   d.detailed_colors, d.primary_detailed_color, d.clothes, d.bbox, d.camera_id, 
                   d.video_id, d.video_time_offset, 
                   di.id as detection_item_id, di.item_index, di.class_name as item_class_name, 
                   di.category as item_category, di.confidence as item_confidence, di.bbox as item_bbox,
                   dc.top_colors, dc.tone_groups, dc.brightness_groups, dc.vibrancy_groups, 
                   dc.temperature_groups, dc.clothing_groups, dc.primary_color, dc.primary_tone_group"""

    def _map_to_schema(self, row) -> DetectionResponse:
        """ แปลงข้อมูลจาก DB Tuple -> Pydantic Model """
        return DetectionResponse(
            id=str(row[0]),          # UUID -> String
            track_id=int(row[1]),
            timestamp=row[2],
            image_url=f"{self.minio_base}/{row[3]}" if row[3] else None,
            category=str(row[4]) if row[4] else "UNKNOWN",
            class_name=str(row[5]) if row[5] else "unknown",
            detailed_colors=row[6] if row[6] else {},
            color_groups={},  # Removed - calculated on-the-fly from detailed_colors
            primary_detailed_color=str(row[7]) if row[7] else "unknown",
            primary_color_group="unknown",  # Removed - calculated on-the-fly
            clothes=row[8] if row[8] else [],
            bbox=row[9] if row[9] else None,
            camera_id=str(row[10]) if row[10] else "N/A",
            video_id=str(row[11]) if row[11] else None,
            video_time_offset=float(row[12]) if row[12] else None
        )

    def get_all(self, limit: int, offset: int) -> List[DetectionResponse]:
        query = f"""SELECT {self._get_select_columns()} 
                   FROM detections d 
                   LEFT JOIN detection_items di ON d.id = di.detection_id
                   LEFT JOIN detection_colors dc ON di.id = dc.detection_item_id
                   ORDER BY d.timestamp DESC LIMIT %s OFFSET %s"""
        with self.db.conn.cursor() as cur:
            cur.execute(query, (limit, offset))
            rows = cur.fetchall()
            return [self._map_to_schema(r) for r in rows]

    def search_persons(
        self,
        *,
        logic: str,
        threshold: float,
        camera_id: str | None,
        video_id: str | None,
        start_time: str | None,
        end_time: str | None,
        page: int,
        limit: int,
        clothing: list[str],
        colors: list[str],
        brightness: str | None = None,
        temperature: str | None = None,
        vibrancy: str | None = None,
    ):
        self.db._ensure_connection()
        if self.db.conn is None:
            raise RuntimeError("Database not connected")
        if logic not in ["OR", "AND"]:
            raise ValueError("Logic must be OR or AND")
        # Strip accidental empty strings (frontend sends clothing[]="" when none selected)
        clothing = [c for c in clothing if c]
        colors = [c for c in colors if c]

        # Allow search if camera_id or video_id narrows scope, even without clothing/colors
        if not clothing and not colors and not camera_id and not video_id:
            return {"results": [], "total": 0, "page": page, "has_more": False}

        offset = (page - 1) * limit
        params: list[object] = []

        # UI threshold is 0..1. DB stores percentages 0..100
        threshold_pct = max(0.0, min(1.0, threshold)) * 100.0

        base_where = "WHERE 1=1"
        if camera_id:
            base_where += " AND camera_id = %s"
            params.append(camera_id)
        if video_id:
            base_where += " AND video_id = %s"
            params.append(video_id)
        if start_time:
            base_where += " AND timestamp >= %s"
            params.append(start_time)
        if end_time:
            base_where += " AND timestamp <= %s"
            params.append(end_time)

        # Clothing filter: Check if ANY detection_item matches selected class_names (case-insensitive)
        if clothing:
            # Normalize clothing filter values to lowercase for case-insensitive matching
            clothing_lower = [c.lower() for c in clothing]
            if logic == "OR":
                placeholders = ",".join(["%s"] * len(clothing_lower))
                base_where += f""" AND EXISTS (
                    SELECT 1 FROM detection_items di2
                    WHERE di2.detection_id = d.id
                    AND LOWER(di2.class_name) IN ({placeholders})
                )"""
                params.extend(clothing_lower)
            else:
                # AND logic: All selected clothing classes must exist in this detection's items
                for cls in clothing_lower:
                    base_where += """ AND EXISTS (
                        SELECT 1 FROM detection_items di2
                        WHERE di2.detection_id = d.id
                        AND LOWER(di2.class_name) = %s
                    )"""
                    params.append(cls)

        # Color filter: Check if ANY item has the selected colors
        if colors:
            color_conds = []
            for c in colors:
                # Check if ANY detection_item for this detection has the color
                color_conds.append("""EXISTS (
                    SELECT 1 FROM detection_items di2
                    JOIN detection_colors dc2 ON di2.id = dc2.detection_item_id
                    WHERE di2.detection_id = d.id
                    AND EXISTS (
                        SELECT 1 FROM jsonb_array_elements(dc2.top_colors) AS tc
                        WHERE (tc->>'name') = %s AND (tc->>'percentage')::float >= %s
                    )
                )""")
                params.extend([c.lower(), threshold_pct])
            joiner = " OR " if logic == "OR" else " AND "
            base_where += f" AND ({joiner.join(color_conds)})"

        # Secondary filters: brightness, temperature, vibrancy (check ANY item)
        if brightness:
            base_where += """ AND EXISTS (
                SELECT 1 FROM detection_items di2
                JOIN detection_colors dc2 ON di2.id = dc2.detection_item_id
                WHERE di2.detection_id = d.id
                AND (dc2.brightness_groups->>%s)::float > 0
            )"""
            brightness_key = f"{brightness}_colors"
            params.append(brightness_key)

        if temperature:
            base_where += """ AND EXISTS (
                SELECT 1 FROM detection_items di2
                JOIN detection_colors dc2 ON di2.id = dc2.detection_item_id
                WHERE di2.detection_id = d.id
                AND (dc2.temperature_groups->>%s)::float > 0
            )"""
            temperature_key = f"{temperature}_colors"
            params.append(temperature_key)

        if vibrancy:
            base_where += """ AND EXISTS (
                SELECT 1 FROM detection_items di2
                JOIN detection_colors dc2 ON di2.id = dc2.detection_item_id
                WHERE di2.detection_id = d.id
                AND (dc2.vibrancy_groups->>%s)::float > 0
            )"""
            vibrancy_key = f"{vibrancy}_colors"
            params.append(vibrancy_key)

        with self.db.conn.cursor() as cur:
            # Count distinct detections
            count_query = f"""SELECT COUNT(DISTINCT d.id) FROM detections d {base_where}"""
            cur.execute(count_query, tuple(params))
            total = int(cur.fetchone()[0] or 0)

            # Main query with aggregated items using CTE
            cur.execute(
                f"""
                WITH detection_items_agg AS (
                    SELECT 
                        di.detection_id,
                        json_agg(json_build_object(
                            'id', di.id,
                            'item_index', di.item_index,
                            'class_name', di.class_name,
                            'category', di.category,
                            'confidence', di.confidence,
                            'bbox', di.bbox,
                            'colors', json_build_object(
                                'top_colors', dc.top_colors,
                                'primary_color', dc.primary_color,
                                'primary_tone_group', dc.primary_tone_group,
                                'brightness_groups', dc.brightness_groups,
                                'temperature_groups', dc.temperature_groups,
                                'vibrancy_groups', dc.vibrancy_groups,
                                'clothing_groups', dc.clothing_groups
                            )
                        ) ORDER BY di.item_index) as items
                    FROM detection_items di
                    LEFT JOIN detection_colors dc ON di.id = dc.detection_item_id
                    GROUP BY di.detection_id
                )
                SELECT 
                    d.id,
                    d.track_id,
                    d.timestamp,
                    d.image_path,
                    d.camera_id,
                    d.video_id,
                    d.video_time_offset,
                    dia.items
                FROM detections d
                JOIN detection_items_agg dia ON d.id = dia.detection_id
                {base_where}
                ORDER BY d.timestamp DESC
                LIMIT %s OFFSET %s
                """,
                tuple(params + [limit + 1, offset]),
            )
            rows = cur.fetchall()

        has_more = len(rows) > limit
        rows = rows[:limit]

        results = []
        for row in rows:
            detection_id = str(row[0])
            track_id = int(row[1]) if row[1] else 0
            timestamp = row[2]
            image_path = row[3]
            camera_id = str(row[4]) if row[4] else "N/A"
            video_id = row[5] if len(row) > 5 else None
            video_time_offset = row[6] if len(row) > 6 else None
            items = row[7] if len(row) > 7 else []

            # Build image URL from first item or detection
            thumbnail_url = f"{self.minio_base}/{image_path}" if image_path else None

            # Get primary info from first item for backward compatibility
            first_item = items[0] if items else None
            primary_class = first_item.get('class_name', 'Unknown') if first_item else 'Unknown'
            primary_category = first_item.get('category', 'Unknown') if first_item else 'Unknown'
            primary_color = first_item.get('colors', {}).get('primary_color', 'Unknown') if first_item else 'Unknown'

            # Collect all top_colors from all items for display
            all_top_colors = []
            for item in items:
                colors_data = item.get('colors', {})
                top_colors = colors_data.get('top_colors', [])
                if top_colors:
                    all_top_colors.extend(top_colors)
            # Sort by percentage and deduplicate by color name
            seen_colors = set()
            unique_colors = []
            for color in sorted(all_top_colors, key=lambda x: x.get('percentage', 0), reverse=True):
                name = color.get('name')
                if name and name not in seen_colors:
                    seen_colors.add(name)
                    unique_colors.append(color)

            results.append(
                {
                    "id": detection_id,
                    "thumbnail_url": thumbnail_url,
                    "camera_id": camera_id,
                    "camera_name": camera_id,
                    "timestamp": timestamp.isoformat() if timestamp else None,
                    # Backward compatibility fields (from first item)
                    "clothing_class": primary_class,
                    "color": primary_category,
                    "primary_color": primary_color,
                    # New multi-item structure
                    "items": items,
                    "all_top_colors": unique_colors[:5],  # Top 5 colors across all items
                    "video_id": video_id,
                    "video_time_offset": video_time_offset,
                    "track_id": track_id,
                    "confidence": 0.9,
                }
            )

        return {"results": results, "total": total, "page": page, "has_more": has_more}

    def search(self, criteria: SearchCriteria) -> List[DetectionResponse]:
        params = []
        
        # เริ่มต้น Query หลัก with new detection_items schema
        query = f"""SELECT {self._get_select_columns()} 
                   FROM detections d 
                   LEFT JOIN detection_items di ON d.id = di.detection_id
                   LEFT JOIN detection_colors dc ON di.id = dc.detection_item_id 
                   WHERE 1=1"""

        # -------------------------------------------------------
        # 🔥 ไฮไลท์: การจัดการ Class Logic (AND / OR)
        # -------------------------------------------------------
        if criteria.class_names and len(criteria.class_names) > 0:
            if criteria.class_logic == "AND":
                # กรณี AND: หา track_id ที่มีครบทุก class ด้วย INTERSECT
                intersect_queries = []
                for cls_name in criteria.class_names:
                    intersect_queries.append("SELECT track_id FROM detections WHERE class_name = %s")
                    params.append(cls_name)
                full_intersect_sql = " INTERSECT ".join(intersect_queries)
                query += f" AND track_id IN ({full_intersect_sql})"
            else:
                # กรณี OR: ใช้ IN (...)
                placeholders = ', '.join(['%s'] * len(criteria.class_names))
                query += f" AND class_name IN ({placeholders})"
                params.extend(criteria.class_names)

        # -------------------------------------------------------
        # จัดการเงื่อนไขอื่นๆ (เหมือนเดิม)
        # -------------------------------------------------------
        if criteria.color_names and len(criteria.color_names) > 0:
            color_conditions = []
            for color in criteria.color_names:
                color_conditions.append(f"(detailed_colors->>%s)::float > 20.0")
                params.append(color)
            
            joiner = " OR " if criteria.color_logic == "OR" else " AND "
            query += f" AND ({joiner.join(color_conditions)})"

        if criteria.start_time:
            query += " AND timestamp >= %s"
            params.append(criteria.start_time)
        
        if criteria.end_time:
            query += " AND timestamp <= %s"
            params.append(criteria.end_time)

        if criteria.camera_id:
            query += " AND camera_id = %s"
            params.append(criteria.camera_id)

        # จบด้วยการ Sort และ Limit
        query += " ORDER BY timestamp DESC LIMIT %s OFFSET %s"
        params.extend([criteria.limit, criteria.offset])

        with self.db.conn.cursor() as cur:
            cur.execute(query, tuple(params))
            rows = cur.fetchall()
            return [self._map_to_schema(r) for r in rows]

    def get_person_timeline(self, track_id: int) -> PersonTimeline:
        """ ดึงประวัติการเคลื่อนที่ของคนเฉพาะ ID """
        query = f"""SELECT {self._get_select_columns()} 
                   FROM detections d 
                   LEFT JOIN detection_items di ON d.id = di.detection_id
                   LEFT JOIN detection_colors dc ON di.id = dc.detection_item_id 
                   WHERE d.track_id = %s ORDER BY d.timestamp ASC"""
        with self.db.conn.cursor() as cur:
            cur.execute(query, (track_id,))
            rows = cur.fetchall()
            
            if not rows:
                # กรณีไม่เจอข้อมูลเลย
                return PersonTimeline(
                    track_id=track_id,
                    first_seen=datetime.now(),
                    last_seen=datetime.now(),
                    total_detections=0,
                    history=[]
                )

            history = [self._map_to_schema(r) for r in rows]
            return PersonTimeline(
                track_id=track_id,
                first_seen=history[0].timestamp,
                last_seen=history[-1].timestamp,
                total_detections=len(history),
                history=history
            )

    def trace_person(self, *, person_id: str):
        self.db._ensure_connection()
        if self.db.conn is None:
            raise RuntimeError("Database not connected")

        # Handle both numeric and string person IDs
        try:
            track_id = int(person_id)
        except ValueError:
            # If it's not numeric, try to find by person_id field
            with self.db.conn.cursor() as cur:
                cur.execute(
                    f"SELECT track_id FROM detections WHERE person_id = %s LIMIT 1",
                    (person_id,),
                )
                result = cur.fetchone()
                if not result:
                    raise LookupError("Person not found")
                track_id = result[0]
        with self.db.conn.cursor() as cur:
            cur.execute(
                f"""SELECT {self._get_select_columns()} 
                FROM detections d 
                LEFT JOIN detection_items di ON d.id = di.detection_id
                LEFT JOIN detection_colors dc ON di.id = dc.detection_item_id 
                WHERE d.track_id = %s ORDER BY d.timestamp ASC""",
                (track_id,),
            )
            rows = cur.fetchall()

        if not rows:
            raise LookupError("Person not found")

        detections = []
        cameras: list[str] = []
        thumb = None
        for row in rows:
            det = self._map_to_schema(row)
            if thumb is None:
                thumb = det.image_url
            cam = det.camera_id or "N/A"
            cameras.append(cam)
            detections.append(
                {
                    "id": det.id,
                    "camera_id": cam,
                    "camera_name": cam,
                    "timestamp": det.timestamp.isoformat(),
                    "thumbnail_url": det.image_url,
                    "confidence": 0.9,
                    "clothing_class": det.class_name,
                    "color": det.category,
                    "detailed_colors": det.detailed_colors,
                    "primary_detailed_color": det.primary_detailed_color,
                    "video_id": row[11] if len(row) > 11 else None,
                    "video_time_offset": row[12] if len(row) > 12 else None,
                    "top_colors": row[13] if len(row) > 13 else [],
                    "tone_groups": row[14] if len(row) > 14 else {},
                    "brightness_groups": row[15] if len(row) > 15 else {},
                    "vibrancy_groups": row[16] if len(row) > 16 else {},
                    "temperature_groups": row[17] if len(row) > 17 else {},
                    "clothing_groups": row[18] if len(row) > 18 else {},
                    "primary_color": row[19] if len(row) > 19 else None,
                    "primary_tone_group": row[20] if len(row) > 20 else None,
                    "bounding_box": None,
                }
            )

        return {
            "person_id": person_id,
            "thumbnail_url": thumb,
            "detections": detections,
            "cameras": sorted(list(set(cameras))),
            "attributes": {},
        }

    def get_detection_detail(self, detection_id: str):
        """Get all details of a specific detection by ID"""
        self.db._ensure_connection()
        if self.db.conn is None:
            raise RuntimeError("Database not connected")

        with self.db.conn.cursor() as cur:
            cur.execute(
                f"""SELECT {self._get_select_columns()}, d.person_id 
                FROM detections d 
                LEFT JOIN detection_items di ON d.id = di.detection_id
                LEFT JOIN detection_colors dc ON di.id = dc.detection_item_id 
                WHERE d.id = %s""",
                (detection_id,),
            )
            row = cur.fetchone()
            
        if not row:
            raise LookupError("Detection not found")
        
        # Map to extended schema with additional fields
        detection = self._map_to_schema(row)
        
        # Add person_id field (after _get_select_columns which has 21 columns: 0-20)
        return {
            **detection.__dict__,
            "person_id": row[21] if len(row) > 21 else None,
        }

    def get_hourly_stats(self) -> List[DailyStats]:
        query = """
            SELECT EXTRACT(HOUR FROM timestamp) as hr, COUNT(*) 
            FROM detections 
            WHERE timestamp >= CURRENT_DATE 
            GROUP BY hr ORDER BY hr
        """
        with self.db.conn.cursor() as cur:
            cur.execute(query)
            return [DailyStats(hour=int(r[0]), count=r[1]) for r in cur.fetchall()]

    def get_clothing_distribution(self) -> List[ClothingStats]:
        query = "SELECT class_name, COUNT(*) FROM detections GROUP BY class_name"
        with self.db.conn.cursor() as cur:
            cur.execute(query)
            return [ClothingStats(label=r[0], count=r[1]) for r in cur.fetchall()]

    def get_unique_persons_today(self) -> int:
        query = "SELECT COUNT(DISTINCT track_id) FROM detections WHERE timestamp >= CURRENT_DATE"
        with self.db.conn.cursor() as cur:
            cur.execute(query)
            return int(cur.fetchone()[0] or 0)

    def delete_detection(self, detection_id: str) -> bool: # ✅ แก้ Type เป็น str (UUID)
        """ ลบข้อมูลด้วย UUID string """
        query = "DELETE FROM detections WHERE id = %s"
        with self.db.conn.cursor() as cur:
            cur.execute(query, (detection_id,))
            self.db.conn.commit()
            return True
        
    
        
    def analyze_image_for_search(self, image_bytes: bytes):
        """
        รับไฟล์รูป -> วิเคราะห์ -> ส่งคืน Class และ Color

        Feature Flag: USE_REFACTORED_IMAGE_ANALYZER
        - false (default): ใช้โค้ดเดิม (original implementation)
        - true: ใช้โค้ดใหม่ (refactored ImageAnalyzer)
        """
        print(f"[CONTROLLER] analyze_image_for_search called, bytes: {len(image_bytes)}")

        # Check Feature Flag
        use_refactored = use_refactored_image_analyzer()
        print(f"[CONTROLLER] Feature flag USE_REFACTORED_IMAGE_ANALYZER: {use_refactored}")

        if use_refactored:
            print("[CONTROLLER] Using refactored ImageAnalyzer")
            return self._analyze_image_refactored(image_bytes)
        else:
            print("[CONTROLLER] Using original analyzer")
            return self._analyze_image_original(image_bytes)
    
    def _analyze_image_original(self, image_bytes: bytes):
        """
        Original implementation (fallback).
        Uses the existing classifier directly.
        """
        try:
            # 1. แปลง Bytes เป็น OpenCV Image
            nparr = np.frombuffer(image_bytes, np.uint8)
            img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

            if img is None:
                raise ValueError("Could not decode image")

            # 2. ส่งเข้า Classifier (ตัวเดิมที่คุณมี)
            # สมมติว่า classifier.predict ส่งคืนค่า (class_name, color_name, confidence)
            # คุณอาจต้องปรับบรรทัดนี้ตาม return type จริงของ classifier คุณ
            class_name, color_name = self.classifier.predict(img)

            # 3. จัด Format ผลลัพธ์ส่งกลับ
            return {
                "status": "success",
                "detected_attributes": {
                    "class_name": class_name,  # เช่น "Short_Sleeve_Shirt"
                    "color_name": color_name   # เช่น "Red"
                }
            }

        except Exception as e:
            return {
                "status": "error",
                "message": str(e)
            }
    
    def _analyze_image_refactored(self, image_bytes: bytes):
        """
        Refactored implementation using ImageAnalyzer.
        Uses the new ThreadPoolProcessor architecture.
        """
        try:
            # Lazy initialization of ImageAnalyzer
            if self._image_analyzer is None:
                from services.image_analyzer import ImageAnalyzer
                self._image_analyzer = ImageAnalyzer()
            
            # Use refactored analyzer
            result = self._image_analyzer.analyze(image_bytes)
            return result
            
        except Exception as e:
            # Fallback to original if refactored fails
            print(f"[DetectionController] Refactored analyzer failed: {e}")
            print("[DetectionController] Falling back to original implementation...")
            return self._analyze_image_original(image_bytes)

    # ─── Advanced Search Methods ──────────────────────────────────────

    def _build_advanced_search_query(
        self,
        *,
        clothing_groups: list[dict],
        global_logic: str,
        threshold: float,
        camera_id: str | None = None,
        video_id: str | None = None,
        start_time: str | None = None,
        end_time: str | None = None,
    ) -> tuple[str, list]:
        """
        Build SQL query for advanced search with clothing-specific color selection.

        Query logic:
        - global_logic = "OR": (group1 matches) OR (group2 matches) OR ...
        - global_logic = "AND": (group1 matches) AND (group2 matches) AND ...
        - Within each group:
          - color_logic = "OR": item has ANY of the colors
          - color_logic = "AND": item has ALL of the colors
        """
        if not clothing_groups:
            raise ValueError("clothing_groups must not be empty")

        # Validate all groups have at least one color OR includeWithoutColors flag
        # Empty colors array means "match any color for this clothing type"
        for group in clothing_groups:
            if not group.get("colors") and not group.get("include_without_colors"):
                # Allow empty colors - this means "search for this clothing with any color"
                pass

        # UI threshold is 0..1. DB stores percentages 0..100
        threshold_pct = max(0.0, min(1.0, threshold)) * 100.0
        params: list[object] = []

        # Build base WHERE clause (time, camera, video filters)
        base_where = "WHERE 1=1"
        if camera_id:
            base_where += " AND d.camera_id = %s"
            params.append(camera_id)
        if video_id:
            base_where += " AND d.video_id = %s"
            params.append(video_id)
        if start_time:
            base_where += " AND d.timestamp >= %s"
            params.append(start_time)
        if end_time:
            base_where += " AND d.timestamp <= %s"
            params.append(end_time)

        # Build conditions for each clothing group
        group_conditions = []

        for group in clothing_groups:
            clothing = group["clothing"].lower()
            colors = [c.lower() for c in group.get("colors", [])]
            color_logic = group.get("color_logic", "OR")

            if not colors:
                # Empty colors: match this clothing type with ANY color
                group_conditions.append("""EXISTS (
                    SELECT 1 FROM detection_items di2
                    WHERE di2.detection_id = d.id
                    AND LOWER(di2.class_name) = %s
                )""")
                params.append(clothing)
            else:
                # Build color conditions for this clothing item
                color_conds = []
                for color in colors:
                    # Check if a detection_item of the specified clothing type has the color
                    color_conds.append("""EXISTS (
                        SELECT 1 FROM detection_items di2
                        JOIN detection_colors dc2 ON di2.id = dc2.detection_item_id
                        WHERE di2.detection_id = d.id
                        AND LOWER(di2.class_name) = %s
                        AND EXISTS (
                            SELECT 1 FROM jsonb_array_elements(dc2.top_colors) AS tc
                            WHERE LOWER(tc->>'name') = %s AND (tc->>'percentage')::float >= %s
                        )
                    )""")
                    params.extend([clothing, color, threshold_pct])

                # Join color conditions based on color_logic
                if color_logic == "OR":
                    # OR: item has ANY of the colors
                    clothing_condition = f"({ ' OR '.join(color_conds) })"
                else:
                    # AND: item has ALL of the colors
                    clothing_condition = f"({ ' AND '.join(color_conds) })"

                group_conditions.append(clothing_condition)

        # Join group conditions based on global_logic
        if global_logic == "OR":
            global_condition = f"({ ' OR '.join(group_conditions) })"
        else:
            global_condition = f"({ ' AND '.join(group_conditions) })"

        # Combine with base WHERE
        full_where = f"{base_where} AND {global_condition}"

        # Return the WHERE clause and params
        # The actual query will be constructed in search_advanced
        return full_where, params

    def search_advanced(
        self,
        *,
        clothing_groups: list[dict],
        global_logic: str,
        threshold: float,
        camera_id: str | None = None,
        video_id: str | None = None,
        start_time: str | None = None,
        end_time: str | None = None,
        page: int = 1,
        limit: int = 24,
    ):
        """
        Advanced search with clothing-specific color selection.

        Example query scenarios:
        1. global_logic=OR: (Long_sleeve has red OR dark_red) OR (Trousers has blue AND navy)
        2. global_logic=AND: (Long_sleeve has red) AND (Short_sleeve has blue)
        """
        self.db._ensure_connection()
        if self.db.conn is None:
            raise RuntimeError("Database not connected")

        if global_logic not in ["OR", "AND"]:
            raise ValueError("global_logic must be OR or AND")

        # Build the WHERE clause and parameters
        full_where, params = self._build_advanced_search_query(
            clothing_groups=clothing_groups,
            global_logic=global_logic,
            threshold=threshold,
            camera_id=camera_id,
            video_id=video_id,
            start_time=start_time,
            end_time=end_time,
        )

        offset = (page - 1) * limit
        query_params = params + [limit + 1, offset]

        # Build relevance scoring based on clothing_groups
        relevance_score_parts = []
        for i, group in enumerate(clothing_groups):
            clothing = group["clothing"].lower()
            colors = [c.lower() for c in group.get("colors", [])]
            
            # Clothing match score (40% weight)
            clothing_score = f"""
                CASE WHEN EXISTS (
                    SELECT 1 FROM detection_items di_score
                    WHERE di_score.detection_id = d.id
                    AND LOWER(di_score.class_name) = '{clothing}'
                ) THEN 0.4 ELSE 0 END
            """
            
            # Color match score (60% weight) - average of color percentages
            color_score = "0"
            if colors:
                color_conditions = " OR ".join([f"LOWER(tc->>'name') = '{c}'" for c in colors])
                color_score = f"""
                    COALESCE((
                        SELECT AVG((tc->>'percentage')::float / 100.0) * 0.6
                        FROM detection_items di_color
                        JOIN detection_colors dc_color ON di_color.id = dc_color.detection_item_id
                        CROSS JOIN jsonb_array_elements(dc_color.top_colors) AS tc
                        WHERE di_color.detection_id = d.id
                        AND LOWER(di_color.class_name) = '{clothing}'
                        AND ({color_conditions})
                    ), 0)
                """
            
            relevance_score_parts.append(f"({clothing_score} + {color_score})")
        
        # Combine scores based on global_logic
        if global_logic == "OR":
            # OR: take the maximum score (best matching group)
            relevance_score = f"GREATEST({', '.join(relevance_score_parts)})"
        else:
            # AND: sum scores divided by number of groups (average)
            relevance_score = f"({' + '.join(relevance_score_parts)}) / {len(clothing_groups)}"

        with self.db.conn.cursor() as cur:
            # Count distinct detections
            count_query = f"SELECT COUNT(DISTINCT d.id) FROM detections d {full_where}"
            cur.execute(count_query, tuple(params))
            total = int(cur.fetchone()[0] or 0)

            # Main query with aggregated items and relevance scoring
            cur.execute(
                f"""
                WITH detection_items_agg AS (
                    SELECT
                        di.detection_id,
                        json_agg(json_build_object(
                            'id', di.id,
                            'item_index', di.item_index,
                            'class_name', di.class_name,
                            'category', di.category,
                            'confidence', di.confidence,
                            'bbox', di.bbox,
                            'colors', json_build_object(
                                'top_colors', dc.top_colors,
                                'primary_color', dc.primary_color,
                                'primary_tone_group', dc.primary_tone_group,
                                'brightness_groups', dc.brightness_groups,
                                'temperature_groups', dc.temperature_groups,
                                'vibrancy_groups', dc.vibrancy_groups,
                                'clothing_groups', dc.clothing_groups
                            )
                        ) ORDER BY di.item_index) as items
                    FROM detection_items di
                    LEFT JOIN detection_colors dc ON di.id = dc.detection_item_id
                    GROUP BY di.detection_id
                ),
                ranked_results AS (
                    SELECT
                        d.id,
                        d.track_id,
                        d.timestamp,
                        d.image_path,
                        d.camera_id,
                        d.video_id,
                        d.video_time_offset,
                        dia.items,
                        {relevance_score} as relevance_score
                    FROM detections d
                    JOIN detection_items_agg dia ON d.id = dia.detection_id
                    {full_where}
                )
                SELECT * FROM ranked_results
                ORDER BY relevance_score DESC, timestamp DESC
                LIMIT %s OFFSET %s
                """,
                tuple(query_params),
            )
            rows = cur.fetchall()

        has_more = len(rows) > limit
        rows = rows[:limit]

        # Transform results
        results = []
        for row in rows:
            detection_id = str(row[0])
            track_id = int(row[1]) if row[1] else 0
            timestamp = row[2]
            image_path = row[3]
            camera_id_res = str(row[4]) if row[4] else "N/A"
            video_id_res = row[5] if len(row) > 5 else None
            video_time_offset = row[6] if len(row) > 6 else None
            items = row[7] if len(row) > 7 else []
            relevance_score = float(row[8]) if len(row) > 8 else 0.0

            # Build image URL
            thumbnail_url = f"{self.minio_base}/{image_path}" if image_path else None

            # Get primary info from first item for backward compatibility
            first_item = items[0] if items else None
            primary_class = first_item.get('class_name', 'Unknown') if first_item else 'Unknown'
            primary_color = first_item.get('colors', {}).get('primary_color', 'Unknown') if first_item else 'Unknown'

            # Collect all top_colors from all items
            all_top_colors = []
            for item in items:
                colors_data = item.get('colors', {})
                top_colors = colors_data.get('top_colors', [])
                if top_colors:
                    all_top_colors.extend(top_colors)

            # Sort by percentage and deduplicate
            seen_colors = set()
            unique_colors = []
            for color in sorted(all_top_colors, key=lambda x: x.get('percentage', 0), reverse=True):
                name = color.get('name')
                if name and name not in seen_colors:
                    seen_colors.add(name)
                    unique_colors.append(color)

            results.append({
                "id": detection_id,
                "thumbnail_url": thumbnail_url,
                "relevance_score": round(relevance_score, 3),
                "camera_id": camera_id_res,
                "camera_name": camera_id_res,
                "timestamp": timestamp.isoformat() if timestamp else None,
                "clothing_class": primary_class,
                "color": primary_color,
                "primary_color": primary_color,
                "items": items,
                "all_top_colors": unique_colors[:5],
                "video_id": video_id_res,
                "video_time_offset": video_time_offset,
                "track_id": track_id,
                "confidence": 0.9,
            })

        return {"results": results, "total": total, "page": page, "has_more": has_more}