"""
Test script to verify Upload flow and Realtime flow produce identical detection results.

Usage:
    python tests/verify_flow_parity.py --video-path temp_videos/CAM-01_CAM-01_CAM-01_CAM-01_CAM-01_UNKNOWN_testvideo.mp4 --verbose

This script will:
1. Clear test data from database
2. Run Upload flow with camera_id='test_upload_001'
3. Run Realtime flow with save_to_db=true (camera_id will be 'stream_<id>')
4. Query and compare detection results
5. Generate comparison report
"""

import argparse
import json
import os
import sys
import time
import requests
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.services.database import DatabaseService


class FlowParityTester:
    """Test parity between Upload and Realtime flows."""
    
    def __init__(self, base_url: str = "http://localhost:8000", verbose: bool = False):
        self.base_url = base_url.rstrip("/")
        self.verbose = verbose
        self.db = DatabaseService()
        self.results = {
            "upload": {},
            "realtime": {},
            "comparison": {},
            "passed": False
        }
        
    def log(self, message: str, level: str = "info"):
        """Print log message if verbose mode is enabled."""
        if self.verbose or level in ["error", "warning", "success"]:
            prefix = {"info": "ℹ️", "error": "❌", "warning": "⚠️", "success": "✅"}.get(level, "ℹ️")
            print(f"{prefix} {message}")
    
    def clear_test_data(self):
        """Clear previous test data from database."""
        self.log("Clearing previous test data...")
        try:
            with self.db.conn.cursor() as cur:
                test_camera_id = "test_upload_001"
                # Delete detections for test camera
                cur.execute("""
                    DELETE FROM detections 
                    WHERE camera_id = %s
                """, (test_camera_id,))
                deleted_detections = cur.rowcount
                
                # Delete test videos
                cur.execute("""
                    DELETE FROM processed_videos 
                    WHERE camera_id = %s
                """, (test_camera_id,))
                deleted_videos = cur.rowcount
                
                self.db.conn.commit()
                self.log(f"Cleared {deleted_detections} detections and {deleted_videos} videos", "success")
        except Exception as e:
            self.log(f"Error clearing test data: {e}", "error")
    
    def run_upload_flow(self, video_path: str) -> bool:
        """Run the upload flow and wait for processing to complete."""
        self.log("=" * 60)
        self.log("RUNNING UPLOAD FLOW")
        self.log("=" * 60)
        
        camera_id = "test_upload_001"
        
        try:
            # 1. Upload video
            self.log(f"Uploading video: {video_path}")
            with open(video_path, "rb") as f:
                files = {"file": (os.path.basename(video_path), f, "video/mp4")}
                data = {"camera_id": camera_id, "label": "Test Upload Flow", "frame_skip": "5"}
                
                response = requests.post(
                    f"{self.base_url}/api/video/analyze/upload",
                    files=files,
                    data=data,
                    timeout=30
                )
            
            if response.status_code != 200:
                self.log(f"Upload failed: {response.text}", "error")
                return False
            
            result = response.json()
            video_id = result.get("video_id")
            self.log(f"Upload started. Video ID: {video_id}", "success")
            
            # 2. Wait for processing to complete
            self.log("Waiting for processing to complete...")
            max_wait = 300  # 5 minutes
            wait_interval = 5
            elapsed = 0
            
            while elapsed < max_wait:
                time.sleep(wait_interval)
                elapsed += wait_interval
                
                # Check video status
                with self.db.conn.cursor() as cur:
                    cur.execute(
                        "SELECT status FROM processed_videos WHERE id::text = %s",
                        (video_id,)
                    )
                    row = cur.fetchone()
                    if row:
                        status = row[0]
                        self.log(f"  Status: {status} ({elapsed}s elapsed)")
                        if status == "completed":
                            self.log("Processing completed!", "success")
                            break
                        elif status == "error":
                            self.log("Processing failed!", "error")
                            return False
            else:
                self.log("Timeout waiting for processing", "error")
                return False
            
            # 3. Collect results
            self.results["upload"] = self._collect_flow_data(camera_id, video_id)
            return True
            
        except Exception as e:
            self.log(f"Upload flow error: {e}", "error")
            import traceback
            traceback.print_exc()
            return False
    
    def run_realtime_flow(self, video_path: str) -> bool:
        """Run the realtime flow with save_to_db=true."""
        self.log("=" * 60)
        self.log("RUNNING REALTIME FLOW")
        self.log("=" * 60)
        
        try:
            # 1. Upload temp video first
            self.log(f"Uploading temp video: {video_path}")
            with open(video_path, "rb") as f:
                files = {"file": (os.path.basename(video_path), f, "video/mp4")}
                response = requests.post(
                    f"{self.base_url}/api/video/analyze/upload-temp",
                    files=files,
                    timeout=30
                )
            
            if response.status_code != 200:
                self.log(f"Temp upload failed: {response.text}", "error")
                return False
            
            temp_result = response.json()
            temp_path = temp_result.get("file_path")
            total_frames = temp_result.get("total_frames", 0)
            fps = temp_result.get("fps", 30.0)
            duration = total_frames / fps if fps > 0 else 0
            
            self.log(f"Temp video uploaded: {temp_path}", "success")
            self.log(f"Video info: {total_frames} frames, {fps:.2f} fps, ~{duration:.1f}s")
            
            # 2. Start stream analysis with save_to_db=true and matching camera_id
            realtime_camera_id = "test_upload_001"  # Same as upload flow for fair comparison
            self.log(f"Starting stream analysis with save_to_db=true, camera_id={realtime_camera_id}...")
            
            # This is an MJPEG stream that blocks until video ends
            # We need to consume the stream to let it process
            stream_response = requests.get(
                f"{self.base_url}/api/video/stream-analyze",
                params={
                    "video_path": temp_path,
                    "camera_id": realtime_camera_id,
                    "save_to_db": "true",
                    "frame_skip": "5",  # Match upload flow frame skip
                    "show_detector_bbox": "false",  # Less processing overhead
                    "show_detector_track_id": "false",
                    "show_classifier_class_name": "false"
                },
                stream=True,
                timeout=600  # 10 minutes for long videos
            )
            
            if stream_response.status_code != 200:
                self.log(f"Stream failed: {stream_response.text}", "error")
                return False
            
            # Consume the stream (we don't need the frames, just let it process)
            self.log("Consuming stream...")
            frame_count = 0
            for chunk in stream_response.iter_content(chunk_size=8192):
                frame_count += 1
                if frame_count % 100 == 0:
                    self.log(f"  Consumed {frame_count} frames...")
            
            self.log(f"Stream completed. Consumed ~{frame_count} MJPEG frames", "success")
            
            # 3. Wait a bit for database writes to complete
            self.log("Waiting for database writes to complete...")
            time.sleep(3)
            
            # 4. Find the stream camera_id and collect results
            self.log("Searching for stream data in database...")
            with self.db.conn.cursor() as cur:
                # First, check all recent detections to debug
                cur.execute("""
                    SELECT camera_id, video_id, timestamp
                    FROM detections 
                    ORDER BY timestamp DESC
                    LIMIT 5
                """)
                recent_rows = cur.fetchall()
                self.log(f"Recent detections in DB: {len(recent_rows)} rows")
                for r in recent_rows:
                    self.log(f"  camera_id={r[0]}, video_id={r[1]}, time={r[2]}")
                
                # Now search for stream data (using same camera_id as upload flow)
                cur.execute("""
                    SELECT camera_id, video_id, timestamp
                    FROM detections 
                    WHERE camera_id = %s
                    ORDER BY timestamp DESC
                    LIMIT 1
                """, (realtime_camera_id,))
                row = cur.fetchone()
                if row:
                    stream_camera_id = row[0]
                    stream_video_id = row[1]
                    self.log(f"Found stream data: camera_id={stream_camera_id}, video_id={stream_video_id}")
                else:
                    self.log("No stream data found in database!", "error")
                    # Check processed_videos table too
                    cur.execute("""
                        SELECT id, camera_id, label, status 
                        FROM processed_videos 
                        WHERE camera_id = %s
                        ORDER BY created_at DESC
                        LIMIT 5
                    """, (realtime_camera_id,))
                    videos = cur.fetchall()
                    self.log(f"Recent stream videos: {len(videos)}")
                    for v in videos:
                        self.log(f"  id={v[0]}, camera_id={v[1]}, status={v[3]}")
                    return False
            
            # 5. Collect results
            self.results["realtime"] = self._collect_flow_data(stream_camera_id, stream_video_id)
            
            # 6. Cleanup temp file
            try:
                temp_id = temp_path.split("temp_")[1].split("_")[0]
                requests.delete(f"{self.base_url}/api/video/analyze/temp/{temp_id}")
                self.log("Temp file cleaned up")
            except Exception as e:
                self.log(f"Temp cleanup failed (non-critical): {e}", "warning")
            
            return True
            
        except Exception as e:
            self.log(f"Realtime flow error: {e}", "error")
            import traceback
            traceback.print_exc()
            return False
    
    def _collect_flow_data(self, camera_id: str, video_id: Optional[str]) -> Dict[str, Any]:
        """Collect detection data for a flow."""
        self.log(f"Collecting data for camera_id={camera_id}, video_id={video_id}")
        
        data = {
            "camera_id": camera_id,
            "video_id": video_id,
            "detections": [],
            "row_count": 0,
            "track_ids": set(),
            "timestamps": [],
            "color_data": []
        }
        
        try:
            with self.db.conn.cursor() as cur:
                # Query all detections for this camera/video
                query = """
                    SELECT 
                        id, track_id, timestamp, video_time_offset,
                        detailed_colors, color_groups, 
                        primary_detailed_color, primary_color_group,
                        class_name, clothing_category, bbox
                    FROM detections
                    WHERE camera_id = %s
                """
                params = [camera_id]
                
                if video_id:
                    query += " AND video_id = %s"
                    params.append(str(video_id))
                
                query += " ORDER BY video_time_offset, track_id"
                
                cur.execute(query, params)
                rows = cur.fetchall()
                
                columns = [desc[0] for desc in cur.description]
                
                for row in rows:
                    row_dict = dict(zip(columns, row))
                    data["detections"].append(row_dict)
                    data["track_ids"].add(row_dict.get("track_id"))
                    data["timestamps"].append(row_dict.get("video_time_offset"))
                    data["color_data"].append({
                        "primary_detailed_color": row_dict.get("primary_detailed_color"),
                        "primary_color_group": row_dict.get("primary_color_group"),
                        "detailed_colors": row_dict.get("detailed_colors"),
                        "color_groups": row_dict.get("color_groups")
                    })
                
                data["row_count"] = len(rows)
                data["track_ids"] = sorted(list(data["track_ids"]))
                
        except Exception as e:
            self.log(f"Error collecting data: {e}", "error")
        
        self.log(f"Collected {data['row_count']} detections, {len(data['track_ids'])} unique tracks")
        return data
    
    def compare_results(self) -> bool:
        """Compare upload and realtime flow results."""
        self.log("=" * 60)
        self.log("COMPARING RESULTS")
        self.log("=" * 60)
        
        upload = self.results.get("upload", {})
        realtime = self.results.get("realtime", {})
        
        if not upload or not realtime:
            self.log("Missing data for comparison", "error")
            return False
        
        comparison = {
            "row_count_match": False,
            "track_count_match": False,
            "color_data_compared": 0,
            "color_mismatches": 0,
            "timestamp_range_upload": None,
            "timestamp_range_realtime": None,
            "differences": []
        }
        
        # 1. Row count comparison
        upload_count = upload.get("row_count", 0)
        realtime_count = realtime.get("row_count", 0)
        comparison["row_count_match"] = upload_count == realtime_count
        comparison["upload_row_count"] = upload_count
        comparison["realtime_row_count"] = realtime_count
        
        self.log(f"Row count - Upload: {upload_count}, Realtime: {realtime_count}")
        if not comparison["row_count_match"]:
            diff = abs(upload_count - realtime_count)
            comparison["differences"].append(f"Row count differs by {diff}")
            self.log(f"⚠️ Row count mismatch: {diff} difference", "warning")
        else:
            self.log("✅ Row count matches!", "success")
        
        # 2. Track ID comparison
        upload_tracks = set(upload.get("track_ids", []))
        realtime_tracks = set(realtime.get("track_ids", []))
        comparison["track_count_match"] = len(upload_tracks) == len(realtime_tracks)
        comparison["upload_track_count"] = len(upload_tracks)
        comparison["realtime_track_count"] = len(realtime_tracks)
        comparison["upload_track_ids"] = sorted(list(upload_tracks))
        comparison["realtime_track_ids"] = sorted(list(realtime_tracks))
        
        self.log(f"Track count - Upload: {len(upload_tracks)}, Realtime: {len(realtime_tracks)}")
        if not comparison["track_count_match"]:
            comparison["differences"].append(f"Track count differs")
            self.log(f"⚠️ Track count mismatch", "warning")
        else:
            self.log("✅ Track count matches!", "success")
        
        # 3. Timestamp range comparison
        upload_times = upload.get("timestamps", [])
        realtime_times = realtime.get("timestamps", [])
        if upload_times:
            comparison["timestamp_range_upload"] = (min(upload_times), max(upload_times))
        if realtime_times:
            comparison["timestamp_range_realtime"] = (min(realtime_times), max(realtime_times))
        
        # 4. Color data comparison (sample first 10)
        upload_colors = upload.get("color_data", [])
        realtime_colors = realtime.get("color_data", [])
        
        sample_size = min(10, len(upload_colors), len(realtime_colors))
        color_matches = 0
        
        for i in range(sample_size):
            u_color = upload_colors[i] if i < len(upload_colors) else {}
            r_color = realtime_colors[i] if i < len(realtime_colors) else {}
            
            comparison["color_data_compared"] += 1
            
            u_primary = u_color.get("primary_detailed_color")
            r_primary = r_color.get("primary_detailed_color")
            
            if u_primary == r_primary:
                color_matches += 1
            else:
                comparison["color_mismatches"] += 1
                if len(comparison["differences"]) < 5:  # Limit differences logged
                    comparison["differences"].append(
                        f"Color mismatch at index {i}: upload={u_primary}, realtime={r_primary}"
                    )
        
        comparison["color_matches"] = color_matches
        comparison["color_match_rate"] = (color_matches / sample_size * 100) if sample_size > 0 else 0
        
        self.log(f"Color comparison (sample {sample_size}): {color_matches}/{sample_size} match ({comparison['color_match_rate']:.1f}%)")
        
        # 5. Determine pass/fail
        # We consider it a pass if row counts are within 10% and track counts match
        row_diff_percent = abs(upload_count - realtime_count) / max(upload_count, 1) * 100
        passed = row_diff_percent <= 10 and comparison["track_count_match"]
        
        comparison["passed"] = passed
        comparison["row_diff_percent"] = row_diff_percent
        
        self.results["comparison"] = comparison
        self.results["passed"] = passed
        
        if passed:
            self.log("=" * 60)
            self.log("✅ PARITY TEST PASSED", "success")
            self.log("=" * 60)
        else:
            self.log("=" * 60)
            self.log("❌ PARITY TEST FAILED", "error")
            self.log("=" * 60)
            for diff in comparison["differences"]:
                self.log(f"  - {diff}", "warning")
        
        return passed
    
    def print_comparison_table(self):
        """Print a formatted comparison table."""
        print("\n" + "=" * 80)
        print("COMPARISON TABLE")
        print("=" * 80)
        
        upload = self.results.get("upload", {})
        realtime = self.results.get("realtime", {})
        comp = self.results.get("comparison", {})
        
        print(f"{'Metric':<30} {'Upload':<20} {'Realtime':<20} {'Match?'}")
        print("-" * 80)
        print(f"{'Row Count':<30} {upload.get('row_count', 0):<20} {realtime.get('row_count', 0):<20} {'✅' if comp.get('row_count_match') else '❌'}")
        print(f"{'Track Count':<30} {comp.get('upload_track_count', 0):<20} {comp.get('realtime_track_count', 0):<20} {'✅' if comp.get('track_count_match') else '❌'}")
        print(f"{'Color Match Rate':<30} {'-':<20} {'-':<20} {comp.get('color_match_rate', 0):.1f}%")
        print(f"{'Row Diff %':<30} {'-':<20} {'-':<20} {comp.get('row_diff_percent', 0):.1f}%")
        print("=" * 80)
        print(f"Overall Result: {'✅ PASSED' if self.results.get('passed') else '❌ FAILED'}")
        print("=" * 80)
    
    def export_json_report(self, output_path: str = "parity_test_report.json"):
        """Export detailed results to JSON."""
        report = {
            "test_timestamp": datetime.now().isoformat(),
            "base_url": self.base_url,
            "results": self.results
        }
        
        # Convert sets to lists for JSON serialization
        def convert_sets(obj):
            if isinstance(obj, set):
                return list(obj)
            elif isinstance(obj, dict):
                return {k: convert_sets(v) for k, v in obj.items()}
            elif isinstance(obj, list):
                return [convert_sets(i) for i in obj]
            return obj
        
        report = convert_sets(report)
        
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, ensure_ascii=False, default=str)
        
        self.log(f"Report exported to: {output_path}", "success")
        return output_path
    
    def run(self, video_path: str) -> bool:
        """Run the full parity test."""
        self.log("=" * 80)
        self.log("FLOW PARITY VERIFICATION TEST")
        self.log(f"Video: {video_path}")
        self.log(f"API URL: {self.base_url}")
        self.log("=" * 80)
        
        # Verify video exists
        if not os.path.exists(video_path):
            self.log(f"Video file not found: {video_path}", "error")
            return False
        
        # Clear previous test data
        self.clear_test_data()
        
        # Run upload flow
        if not self.run_upload_flow(video_path):
            self.log("Upload flow failed!", "error")
            return False
        
        # Run realtime flow
        if not self.run_realtime_flow(video_path):
            self.log("Realtime flow failed!", "error")
            return False
        
        # Compare results
        self.compare_results()
        
        # Print table
        self.print_comparison_table()
        
        # Export report
        report_path = self.export_json_report()
        
        return self.results.get("passed", False)


def main():
    parser = argparse.ArgumentParser(
        description="Verify Upload vs Realtime flow parity",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    python tests/verify_flow_parity.py --video-path temp_videos/test.mp4
    python tests/verify_flow_parity.py --video-path temp_videos/test.mp4 --verbose
    python tests/verify_flow_parity.py --video-path temp_videos/test.mp4 --base-url http://localhost:8000
        """
    )
    
    parser.add_argument(
        "--video-path",
        required=True,
        help="Path to test video file"
    )
    parser.add_argument(
        "--base-url",
        default="http://localhost:8000",
        help="Base URL for API (default: http://localhost:8000)"
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable verbose output"
    )
    parser.add_argument(
        "--output",
        default="parity_test_report.json",
        help="Output JSON report path (default: parity_test_report.json)"
    )
    
    args = parser.parse_args()
    
    # Run test
    tester = FlowParityTester(base_url=args.base_url, verbose=args.verbose)
    passed = tester.run(args.video_path)
    
    # Export report with custom name if specified
    if args.output != "parity_test_report.json":
        tester.export_json_report(args.output)
    
    # Exit with appropriate code
    sys.exit(0 if passed else 1)


if __name__ == "__main__":
    main()
