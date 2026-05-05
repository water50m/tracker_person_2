// ============================================================
// NEXUS-EYE · Shared TypeScript Types
// ============================================================

// ─── Search & Detection ─────────────────────────────────────

export type ClothingClass =
  | "Long_sleeve"
  | "Short_sleeve"
  | "Trousers"
  | "Shorts"
  | "skirt"
  | "Dress"
  | "Unknown";

export type ClothingColor =
  | "Red"
  | "Blue"
  | "Black"
  | "White"
  | "Yellow"
  | "Green"
  | "Orange"
  | "Purple"
  | "Pink"
  | "Brown"
  | "Gray"
  | "Navy"
  | "Unknown";

// New 63-color system types
export type DetailedColor =
  // Red shades (5)
  | "red" | "dark_red" | "crimson" | "scarlet" | "maroon"
  // Orange shades (5)
  | "orange" | "dark_orange" | "amber" | "peach" | "coral"
  // Yellow shades (5)
  | "yellow" | "gold" | "light_yellow" | "mustard" | "khaki"
  // Green shades (8)
  | "green" | "dark_green" | "light_green" | "olive" | "lime" | "forest_green" | "mint" | "teal"
  // Blue shades (9)
  | "blue" | "dark_blue" | "light_blue" | "navy" | "sky_blue" | "royal_blue" | "cobalt" | "turquoise"
  // Purple shades (8)
  | "purple" | "dark_purple" | "light_purple" | "violet" | "lavender" | "magenta" | "fuchsia" | "plum"
  // Brown shades (6)
  | "brown" | "dark_brown" | "light_brown" | "tan" | "beige" | "camel"
  // Pink shades (6)
  | "pink" | "light_pink" | "hot_pink" | "rose" | "salmon"
  // Grayscale (7)
  | "black" | "dark_gray" | "gray" | "light_gray" | "white" | "silver";

// Color group types (10 tone groups - new system)
export type ToneGroup =
  | "red_tones" | "orange_tones" | "yellow_tones" | "green_tones"
  | "blue_tones" | "purple_tones" | "brown_tones" | "pink_tones"
  | "white_tones" | "black_tones";

export type BrightnessGroup = "light_colors" | "dark_colors" | "medium_colors";
export type VibrancyGroup = "vibrant_colors" | "muted_colors" | "pastel_colors";
export type TemperatureGroup = "warm_colors" | "cool_colors" | "neutral_colors";
export type ClothingColorGroup = "common_shirt_colors" | "common_pants_colors" | "formal_colors" | "casual_colors";

// DetectionColors interface for detection_colors table
export interface DetectionColors {
  top_colors: { name: DetailedColor; percentage: number }[];
  brightness_groups: Record<BrightnessGroup, number>;
  vibrancy_groups: Record<VibrancyGroup, number>;
  temperature_groups: Record<TemperatureGroup, number>;
  clothing_groups: Record<ClothingColorGroup, number>;
  primary_color: DetailedColor;
  primary_tone_group?: string;
}

// DetectionItem interface for multi-item schema (TOP + BOTTOM)
export interface DetectionItem {
  id: string;
  item_index: number;
  class_name: string;
  category: "TOP" | "BOTTOM";
  confidence: number;
  bbox?: number[];
  colors: {
    top_colors: { name: DetailedColor; percentage: number }[];
    primary_color: DetailedColor;
    primary_tone_group?: string;
    brightness_groups: Record<BrightnessGroup, number>;
    temperature_groups: Record<TemperatureGroup, number>;
    vibrancy_groups: Record<VibrancyGroup, number>;
    clothing_groups: Record<ClothingColorGroup, number>;
  };
}

export interface DetectedItem {
  class_name: string;
  category: string;
  color: string;
  confidence?: number;
}

export interface AttributeDetectionResult {
  status: string;
  detected_attributes: {
    class_name: string;
    color_name: string;
    category: string;
    confidence: number;
  };
  all_items?: DetectedItem[];
  processing_time_ms: number;
  num_persons_detected: number;
}

export interface SearchFilters {
  clothing: ClothingClass[];
  colors: ClothingColor[];
  logic: "OR" | "AND";
  threshold: number;
  camera_id?: string;
  video_id?: string;
  start_time?: string;
  end_time?: string;
  // Secondary color filters (tone groups calculated on-the-fly from detailed_colors)
  temperature?: "warm" | "cool" | "neutral";
  brightness?: "light" | "dark" | "medium";
  vibrancy?: "vibrant" | "muted" | "pastel";
  clothing_groups?: ClothingColorGroup[];
}

// ─── Advanced Search Types ───────────────────────────────────

export interface AdvancedFilter {
  clothing: ClothingClass;
  colors: DetailedColor[];
  colorLogic: "OR" | "AND";
  includeWithoutColors?: boolean;
}

export interface AdvancedSearchRequest {
  clothing_groups: {
    clothing: ClothingClass;
    colors: DetailedColor[];
    color_logic: "OR" | "AND";
  }[];
  global_logic: "OR" | "AND";
  threshold: number;
  camera_id?: string;
  video_id?: string;
  start_time?: string;
  end_time?: string;
}

export interface SearchResult {
  id: string;
  thumbnail_url: string | null;
  camera_id: string;
  camera_name?: string;
  timestamp: string;
  // Backward compatibility: primary item info (first item)
  clothing_class: ClothingClass;
  color: ClothingColor;
  confidence: number;
  primary_color?: DetailedColor;
  video_id?: string;
  video_time_offset?: number;
  // New multi-item structure
  items?: DetectionItem[];  // 1-2 items per detection (TOP + BOTTOM)
  all_top_colors?: { name: DetailedColor; percentage: number }[];
  // Legacy fields (kept for backward compatibility)
  detection_colors?: DetectionColors;
  primary_detailed_color?: DetailedColor;
  top_colors?: { name: DetailedColor; percentage: number }[];
}

export interface SearchResultsResponse {
  results: SearchResult[];
  total: number;
  page: number;
  has_more: boolean;
}

// ─── Trace / Journey ─────────────────────────────────────────

export interface TraceEvent {
  id: string;
  camera_id: string;
  camera_name: string;
  timestamp: string;
  thumbnail_url: string | null;
  confidence: number;
  clothing_class?: string;
  color?: string;
  color_profile?: Record<string, number>;
  bounding_box?: {
    x: number;
    y: number;
    w: number;
    h: number;
  } | null;
}

export interface TraceResponse {
  person_id: string;
  thumbnail_url: string | null;
  detections: TraceEvent[];
  cameras: string[];
  attributes: Partial<Record<string, string>>;
}

// ─── Live Events (SSE) ───────────────────────────────────────

export interface LiveDetectionEvent {
  type: "detection";
  payload: {
    id: string;
    camera_id: string;
    timestamp: string;
    clothing: string;
    confidence: number;
    thumbnail_url: string;
  };
}

export interface LiveStatsEvent {
  type: "stats_update";
  payload: {
    total_today: number;
    active_cameras: number;
    detections_per_hour: number;
  };
}

export interface HeartbeatEvent {
  type: "heartbeat";
  ts: number;
}

export type SSEEvent = LiveDetectionEvent | LiveStatsEvent | HeartbeatEvent;

// ─── Stats / Dashboard ───────────────────────────────────────

export interface DashboardStats {
  total_today: number;
  active_cameras: number;
  detections_per_hour: number;
  peak_hour?: string;
}

export interface HourlyDataPoint {
  hour: string;
  count: number;
}

// ─── Input Manager ───────────────────────────────────────────

export type JobStatus = "queued" | "processing" | "done" | "error";

export interface UploadJob {
  job_id: string;
  status: JobStatus;
  camera_id: string;
  filename: string;
  size_bytes: number;
  progress?: number;
  estimated_duration_sec?: number;
  error?: string;
  video_id?: string;
  stream_url?: string;
  is_streaming?: boolean;
  is_paused?: boolean;
}

export interface RTSPStream {
  camera_id: string;
  rtsp_url: string;
  label?: string;
  status: "live" | "offline" | "error";
  resolution?: string;
  fps?: number;
}

export interface RTSPTestResult {
  reachable: boolean;
  latency_ms?: number;
  resolution?: string;
  fps?: number;
  error?: string;
}

// ─── Camera ──────────────────────────────────────────────────

export interface Camera {
  id: string;
  name: string;
  location?: string;
  status: "online" | "offline";
  stream_url?: string;
}
