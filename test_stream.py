import cv2
import time
import os
import sys

# Add src to path if needed so imports work
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.ai.detector import PersonDetector
from src.services.database import DatabaseService
from src.api.routes.dashboard_api import _get_rtsp_url
from src.api.video_controller import _extract_youtube_stream, YOUTUBE_PATTERN

def run_test_stream(camera_id="8"):
    print(f"--- Starting Local Stream Test for Camera {camera_id} ---")
    
    # Get Stream Source URL
    source = _get_rtsp_url(camera_id)
    if not source:
        print(f"❌ Camera {camera_id} not found or has no source URL.")
        return
        
    print(f"Original Source: {source}")
    stream_url = source
    if YOUTUBE_PATTERN.search(source):
        print("Extracting YouTube stream...")
        try:
            info = _extract_youtube_stream(source)
            stream_url = info["stream_url"]
            print("YouTube extraction successful!")
        except Exception as e:
            print(f"❌ yt-dlp extraction failed: {e}")
            return
            
    print(f"Opening VideoCapture...")
    # Add FFmpeg options for m3u8 YouTube streams
    os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = "http_persistent;0|reconnect;1|reconnect_at_eof;1|reconnect_streamed;1|reconnect_delay_max;2|multiple_requests;1"
    cap = cv2.VideoCapture(stream_url)
    
    if not cap.isOpened():
        print(f"❌ Failed to open stream: {stream_url}")
        return
        
    fps_target = cap.get(cv2.CAP_PROP_FPS) or 30.0
    print(f"Video Source Target FPS: {fps_target:.2f}")
    
    # Initialize YOLO Model
    print("Initializing YOLO Detector (this takes a moment)...")
    detector = PersonDetector()
    print("Detector ready.")
    
    frame_count = 0
    inference_times = []
    start_main_loop = time.time()
    
    print("\n--- TEST RUNNING: Press 'q' to quit ---")
    while True:
        # Read frame
        ret, frame = cap.read()
        if not ret:
            print("❌ Failed to read frame from stream. End of stream?")
            break
            
        frame_count += 1
        
        # Track Time
        t1 = time.time()
        results = detector.track_people(frame)
        t2 = time.time()
        
        inference_time_ms = (t2 - t1) * 1000
        inference_times.append(inference_time_ms)
        if len(inference_times) > 30:
            inference_times.pop(0)
            
        avg_infer_ms = sum(inference_times) / len(inference_times)
        
        # Draw bounding boxes
        if results and hasattr(results, 'boxes') and results.boxes is not None:
            for box in results.boxes:
                x1, y1, x2, y2 = map(int, box.xyxy[0])
                cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 255), 2)
                
        # Calculate overall FPS
        elapsed = time.time() - start_main_loop
        actual_fps = frame_count / elapsed if elapsed > 0 else 0
        
        # Overlay text
        stats = f"Overall FPS: {actual_fps:.1f} | YOLO Time: {avg_infer_ms:.1f}ms / frame"
        cv2.putText(frame, stats, (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
        
        # Determine the bottleneck constraint (if 1ms is 1 frame, etc)
        max_possible_fps = 1000.0 / avg_infer_ms if avg_infer_ms > 0 else 999
        cv2.putText(frame, f"Max Possible FPS on this CPU: {max_possible_fps:.1f}", (10, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
        
        # Show window natively (bypasses browser and network entirely)
        # Resize if too large for screen
        h, w = frame.shape[:2]
        if h > 720:
             scale = 720 / h
             frame = cv2.resize(frame, (int(w * scale), 720))
             
        cv2.imshow("Direct Python OpenCV Test", frame)
        
        # Limit to 30fps natively so we don't spin uncontrollably 
        # (1ms is basically run as fast as possible, but gives UI event loop time to draw)
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

    cap.release()
    cv2.destroyAllWindows()
    print("--- Test Complete ---")

if __name__ == "__main__":
    run_test_stream("8")
