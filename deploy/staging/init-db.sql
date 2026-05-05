-- Initialize Staging Database
-- This script runs when PostgreSQL container starts for the first time

-- Create extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";  -- For text search

-- Create detections table
CREATE TABLE IF NOT EXISTS detections (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    track_id INT,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    image_path TEXT,
    clothing_category VARCHAR(50),
    class_name VARCHAR(100),
    camera_id VARCHAR(50),
    bbox JSONB,
    video_time_offset INT,
    video_id UUID,
    embedding JSONB,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Create processed_videos table
CREATE TABLE IF NOT EXISTS processed_videos (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    camera_id VARCHAR(50),
    label VARCHAR(100),
    filename VARCHAR(255),
    file_path TEXT,
    status VARCHAR(20) DEFAULT 'processing',
    width INT,
    height INT,
    fps FLOAT,
    total_frames INT,
    processed_frames INT DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Create cameras table
CREATE TABLE IF NOT EXISTS cameras (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    source_url TEXT,
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Create detection_items table (for clothing items)
CREATE TABLE IF NOT EXISTS detection_items (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    detection_id UUID REFERENCES detections(id) ON DELETE CASCADE,
    item_index INT,
    class_name VARCHAR(100),
    category VARCHAR(50),
    confidence FLOAT,
    bbox JSONB,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Create detection_colors table
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

-- Create indexes for performance
CREATE INDEX IF NOT EXISTS idx_detections_camera_id ON detections(camera_id);
CREATE INDEX IF NOT EXISTS idx_detections_timestamp ON detections(timestamp);
CREATE INDEX IF NOT EXISTS idx_detections_track_id ON detections(track_id);
CREATE INDEX IF NOT EXISTS idx_detections_video_id ON detections(video_id);
CREATE INDEX IF NOT EXISTS idx_processed_videos_camera_id ON processed_videos(camera_id);
CREATE INDEX IF NOT EXISTS idx_processed_videos_status ON processed_videos(status);

-- Create function to update updated_at
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ language 'plpgsql';

-- Create trigger for processed_videos
DROP TRIGGER IF EXISTS update_processed_videos_updated_at ON processed_videos;
CREATE TRIGGER update_processed_videos_updated_at
    BEFORE UPDATE ON processed_videos
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- Insert sample camera for testing
INSERT INTO cameras (name, source_url, is_active) 
VALUES ('Test Camera', 'rtsp://localhost/test', true)
ON CONFLICT DO NOTHING;

-- Grant permissions
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO postgres;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO postgres;
