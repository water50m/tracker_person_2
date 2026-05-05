from pydantic import BaseModel, field_validator, Field
from typing import Optional, List, Dict
from datetime import datetime

# --- 1. สำหรับข้อมูลดิบ (ใช้ใน List และ Response) ---
class DetectionBase(BaseModel):
    track_id: int
    timestamp: datetime
    image_url: Optional[str] = None
    bbox_image_url: Optional[str] = None
    category: str  # TOP, BOTTOM, FULL
    class_name: str
    detailed_colors: Dict[str, float] = {}
    color_groups: Dict[str, Dict] = {}
    primary_detailed_color: str = "unknown"
    primary_color_group: str = "unknown"
    clothes: List[str] = []
    bbox: Optional[List[int]] = None
    camera_id: Optional[str] = None

class DetectionResponse(DetectionBase):
    id: str # Primary Key จาก Database
    video_id: Optional[str] = None
    video_time_offset: Optional[float] = None

# --- 2. สำหรับการค้นหา (นี่คือตัวที่ขาดไปครับ) ---
class SearchCriteria(BaseModel):
    class_names: Optional[List[str]] = None
    class_logic: str = "OR"

    color_names: Optional[List[str]] = None
    color_logic: str = "OR"

    # ✅ เพิ่มตัวนี้: เกณฑ์ความเข้มข้นของสี (Default 15% คือยอมรับเงา/แสงได้เยอะ)
    # ถ้าตั้ง 10-15% จะจับ "แดงมืดๆ" หรือ "แดงซีดๆ" ได้
    # ถ้าตั้ง 50% จะจับเฉพาะ "แดงสด" เท่านั้น
    color_threshold: float = Field(default=15.0, ge=0.0, le=100.0)

    # Secondary color search parameters (tone groups calculated on-the-fly from detailed_colors)
    tone_groups: Optional[List[str]] = None  # e.g., ["red_tones", "blue_tones"]
    detailed_colors: Optional[List[str]] = None  # e.g., ["red", "crimson"]
    brightness: Optional[str] = None  # "light" | "medium" | "dark"
    temperature: Optional[str] = None  # "warm" | "cool" | "neutral"
    vibrancy: Optional[str] = None  # "vibrant" | "muted" | "pastel"

    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    camera_id: Optional[str] = None
    limit: int = 50
    offset: int = 0

# --- 3. สำหรับการวิเคราะห์และสถิติ ---
class PersonTimeline(BaseModel):
    track_id: int
    first_seen: datetime
    last_seen: datetime
    total_detections: int
    history: List[DetectionResponse]

class DailyStats(BaseModel):
    hour: int
    count: int

class ClothingStats(BaseModel):
    label: str
    count: int


# --- Advanced Search Schemas ---

class ClothingGroupFilter(BaseModel):
    clothing: str
    colors: List[str]
    color_logic: str = "OR"  # "OR" or "AND" for colors within this clothing item


class AdvancedSearchRequest(BaseModel):
    clothing_groups: List[ClothingGroupFilter]
    global_logic: str = "OR"  # "OR" or "AND" between clothing groups
    threshold: float = Field(default=0.1, ge=0.0, le=1.0)
    camera_id: Optional[str] = None
    video_id: Optional[str] = None
    start_time: Optional[str] = None
    end_time: Optional[str] = None

    @field_validator('clothing_groups')
    @classmethod
    def validate_non_empty_groups(cls, v):
        if not v:
            raise ValueError('clothing_groups must not be empty')
        return v


class AdvancedSearchResponse(BaseModel):
    results: List[dict]
    total: int
    page: int
    has_more: bool