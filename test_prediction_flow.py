#!/usr/bin/env python3
"""
Test Controller for Prediction API Flow
Replicates the entire flow of /api/dashboard/prediction/{camera_id}/start
for step-by-step debugging and testing.
"""

import asyncio
import sys
import time
from pathlib import Path
from typing import Optional, Dict, Any
import threading

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

# Import required modules
from src.services.database import DatabaseService
from src.services.stream_manager import stream_manager
from src.api.video_controller import _ACTIVE_STREAMS, _register_stream, _unregister_stream

class PredictionFlowTester:
    """
    Step-by-step tester for prediction flow
    """
    
    def __init__(self):
        self.camera_id = "11"
        self.source_url = None
        self.stop_event = None
        self.processor_instance = None
        self.test_results = {}
    
    def log_step(self, step_name: str, status: str, details: Any = None):
        """Log test step results"""
        timestamp = time.strftime("%H:%M:%S", time.localtime())
        result = {
            "timestamp": timestamp,
            "status": status,
            "details": details
        }
        self.test_results[step_name] = result
        print(f"[{timestamp}] {step_name}: {status}")
        if details:
            print(f"    Details: {details}")
    
    async def step_1_test_camera_already_active(self):
        """Step 1: Check if camera is already processing"""
        print("\n=== STEP 1: Check Camera Status ===")
        
        try:
            if self.camera_id in _ACTIVE_STREAMS:
                self.log_step("camera_status_check", "ERROR", f"Camera {self.camera_id} is already processing")
                return False
            else:
                self.log_step("camera_status_check", "SUCCESS", f"Camera {self.camera_id} is available")
                return True
        except Exception as e:
            self.log_step("camera_status_check", "ERROR", str(e))
            return False
    
    async def step_2_get_rtsp_url(self):
        """Step 2: Get RTSP URL from database"""
        print("\n=== STEP 2: Get RTSP URL ===")
        
        try:
            db = DatabaseService()
            db._ensure_connection()
            
            with db.conn.cursor() as cur:
                cur.execute("SELECT source_url FROM cameras WHERE id = %s", (self.camera_id,))
                row = cur.fetchone()
            
            if row and row[0]:
                self.source_url = row[0]
                self.log_step("rtsp_url_retrieval", "SUCCESS", f"RTSP URL: {self.source_url}")
                return True
            else:
                self.log_step("rtsp_url_retrieval", "ERROR", f"No RTSP URL found for camera {self.camera_id}")
                return False
                
        except Exception as e:
            self.log_step("rtsp_url_retrieval", "ERROR", str(e))
            return False
    
    async def step_3_register_stream(self):
        """Step 3: Register stream in active streams"""
        print("\n=== STEP 3: Register Stream ===")
        
        try:
            self.stop_event = _register_stream(self.camera_id)
            self.log_step("stream_registration", "SUCCESS", f"Stream registered, stop_event: {self.stop_event}")
            return True
        except Exception as e:
            self.log_step("stream_registration", "ERROR", str(e))
            return False
    
    async def step_4_setup_detection_callbacks(self):
        """Step 4: Setup detection callbacks"""
        print("\n=== STEP 4: Setup Detection Callbacks ===")
        
        try:
            # Define callbacks that match the original API signature
            # But we need to create a wrapper since StreamProcessor calls different signature
            
            def on_detection_wrapper(person_detection, frame_number):
                """Wrapper that converts StreamProcessor signature to original API signature"""
                try:
                    print(f"[DEBUG] on_detection_wrapper called for camera {self.camera_id}, frame #{frame_number}")
                    print(f"[DEBUG] Person detection: {person_detection}")
                    
                    # Convert to list format like original API expects
                    detections_list = [person_detection] if person_detection else []
                    
                    # Get current frame bytes from stream manager if available
                    # We'll update this in the on_frame callback
                    if hasattr(self, '_current_frame_bytes'):
                        frame_bytes = self._current_frame_bytes
                    else:
                        frame_bytes = b''  # Empty bytes if not available
                    
                    # Call the original API style callback
                    self.on_detection(self.camera_id, detections_list, frame_number, frame_bytes)
                        
                except Exception as e:
                    print(f"Detection wrapper error: {e}")
            
            def on_detection(camera_id: str, detections: list, frame_number: int, frame_bytes: bytes):
                """Original API style detection callback"""
                try:
                    print(f"[DEBUG] on_detection called for camera {camera_id}, frame #{frame_number}, detections: {len(detections)}")
                    # Store in global cache for MJPEG streaming
                    stream_manager.update_frame(camera_id, frame_bytes, frame_number)
                    stream_manager.update_detections(camera_id, detections)
                    
                    # Log detection summary
                    person_count = 0
                    for d in detections:
                        if hasattr(d, 'items') and d.items:  # PersonDetection object
                            person_count += 1
                        elif isinstance(d, dict) and d.get('class_name') == 'person':
                            person_count += 1
                    
                    if person_count > 0:
                        timestamp = time.strftime("%H:%M:%S", time.localtime())
                        print(f"[{timestamp}] {person_count} person(s) detected in frame #{frame_number}")
                        
                except Exception as e:
                    print(f"Detection callback error: {e}")
            
            def on_frame(frame, frame_number):
                """Handle each frame"""
                try:
                    # Convert frame to bytes for MJPEG streaming
                    import cv2
                    _, buffer = cv2.imencode('.jpg', frame)
                    frame_bytes = buffer.tobytes()
                    
                    # Store for use in detection callback
                    self._current_frame_bytes = frame_bytes
                    
                    # Update frame in stream manager
                    stream_manager.update_frame(self.camera_id, frame_bytes, frame_number)
                    print(f"[DEBUG] Frame updated for camera {self.camera_id}, frame #{frame_number}")
                except Exception as e:
                    print(f"Frame callback error: {e}")
            
            self.on_detection = on_detection
            self.on_detection_wrapper = on_detection_wrapper  # This is what we'll pass to StreamProcessor
            self.on_frame = on_frame
            
            self.log_step("callback_setup", "SUCCESS", "Detection callbacks defined")
            return True
            
        except Exception as e:
            self.log_step("callback_setup", "ERROR", str(e))
            return False
    
    async def step_5_initialize_stream_processor(self):
        """Step 5: Initialize StreamProcessor singleton"""
        print("\n=== STEP 5: Initialize StreamProcessor ===")
        
        try:
            # Import and get stream processor singleton
            from services.stream_processor import get_stream_processor
            
            print(f"[DEBUG] Getting stream processor...")
            self.processor_instance = await get_stream_processor()
            
            self.log_step("stream_processor_init", "SUCCESS", f"StreamProcessor instance: {id(self.processor_instance)}")
            return True
            
        except Exception as e:
            self.log_step("stream_processor_init", "ERROR", str(e))
            return False
    
    async def step_6_start_stream_processing(self):
        """Step 6: Start actual stream processing"""
        print("\n=== STEP 6: Start Stream Processing ===")
        
        try:
            if not self.processor_instance:
                raise Exception("StreamProcessor not initialized")
            
            if not self.source_url:
                raise Exception("RTSP URL not available")
            
            print(f"[DEBUG] Starting stream for camera {self.camera_id}")
            print(f"[DEBUG] Source: {self.source_url}")
            
            processor = await self.processor_instance.start_stream(
                camera_id=self.camera_id,
                source=self.source_url,
                on_detection=self.on_detection_wrapper,
                on_frame=self.on_frame,
                stop_event=self.stop_event,
                frame_skip=5,
            )
            
            self.log_step("stream_start", "SUCCESS", f"Stream processor started: {id(processor)}")
            
            # Wait a bit to see if stream starts successfully
            await asyncio.sleep(2)
            
            # Check if stream is still in active streams
            if self.camera_id in _ACTIVE_STREAMS:
                self.log_step("stream_verification", "SUCCESS", "Stream is active in _ACTIVE_STREAMS")
            else:
                self.log_step("stream_verification", "WARNING", "Stream not found in _ACTIVE_STREAMS")
            
            return True
            
        except Exception as e:
            self.log_step("stream_start", "ERROR", str(e))
            return False
    
    async def step_7_monitor_stream(self, duration: int = 10):
        """Step 7: Monitor stream for a specified duration"""
        print(f"\n=== STEP 7: Monitor Stream for {duration} seconds ===")
        
        try:
            start_time = time.time()
            detection_count = 0
            
            while time.time() - start_time < duration:
                await asyncio.sleep(1)
                
                # Check if stream is still active
                if self.camera_id not in _ACTIVE_STREAMS:
                    self.log_step("stream_monitoring", "ERROR", "Stream stopped unexpectedly")
                    return False
                
                # You could add more monitoring logic here
                print(f"[MONITOR] Stream active... ({int(time.time() - start_time)}s)")
            
            self.log_step("stream_monitoring", "SUCCESS", f"Stream monitored for {duration} seconds, detections: {detection_count}")
            return True
            
        except Exception as e:
            self.log_step("stream_monitoring", "ERROR", str(e))
            return False
    
    async def step_8_cleanup(self):
        """Step 8: Cleanup and stop stream"""
        print("\n=== STEP 8: Cleanup ===")
        
        try:
            if self.camera_id in _ACTIVE_STREAMS:
                _unregister_stream(self.camera_id)
                self.log_step("cleanup", "SUCCESS", "Stream unregistered")
            else:
                self.log_step("cleanup", "WARNING", "Stream was not in active streams")
            
            return True
            
        except Exception as e:
            self.log_step("cleanup", "ERROR", str(e))
            return False
    
    async def run_full_test(self, monitor_duration: int = 10):
        """Run the complete test flow"""
        print("=" * 60)
        print("PREDICTION FLOW TEST STARTED")
        print(f"Camera ID: {self.camera_id}")
        print(f"Monitor Duration: {monitor_duration} seconds")
        print("=" * 60)
        
        steps = [
            ("camera_status_check", self.step_1_test_camera_already_active),
            ("rtsp_url_retrieval", self.step_2_get_rtsp_url),
            ("stream_registration", self.step_3_register_stream),
            ("callback_setup", self.step_4_setup_detection_callbacks),
            ("stream_processor_init", self.step_5_initialize_stream_processor),
            ("stream_start", self.step_6_start_stream_processing),
            ("stream_monitoring", lambda: self.step_7_monitor_stream(monitor_duration)),
            ("cleanup", self.step_8_cleanup),
        ]
        
        for step_name, step_func in steps:
            try:
                success = await step_func()
                if not success and step_name != "cleanup":
                    print(f"\n❌ FAILED at step: {step_name}")
                    break
            except Exception as e:
                print(f"\n💥 EXCEPTION at step {step_name}: {e}")
                self.log_step(step_name, "EXCEPTION", str(e))
                break
        
        print("\n" + "=" * 60)
        print("TEST SUMMARY")
        print("=" * 60)
        
        for step_name, result in self.test_results.items():
            status_symbol = "✅" if result["status"] == "SUCCESS" else "❌" if result["status"] == "ERROR" else "⚠️"
            print(f"{status_symbol} {step_name}: {result['status']}")
            if result["details"]:
                print(f"    {result['details']}")
        
        return self.test_results
    
    async def run_individual_step(self, step_name: str):
        """Run a specific step"""
        step_map = {
            "1": self.step_1_test_camera_already_active,
            "2": self.step_2_get_rtsp_url,
            "3": self.step_3_register_stream,
            "4": self.step_4_setup_detection_callbacks,
            "5": self.step_5_initialize_stream_processor,
            "6": self.step_6_start_stream_processing,
            "7": lambda: self.step_7_monitor_stream(5),
            "8": self.step_8_cleanup,
        }
        
        if step_name in step_map:
            print(f"\n--- Running Step {step_name} ---")
            success = await step_map[step_name]()
            return success
        else:
            print(f"Invalid step: {step_name}")
            print("Available steps: 1-8")
            return False


async def run_continuous():
    """Run stream continuously in background"""
    tester = PredictionFlowTester()
    
    print("=" * 60)
    print("CONTINUOUS STREAM MODE")
    print(f"Camera ID: {tester.camera_id}")
    print("Press Ctrl+C to stop")
    print("=" * 60)
    
    try:
        # Run steps 1-6 to start the stream
        steps = [
            ("camera_status_check", tester.step_1_test_camera_already_active),
            ("rtsp_url_retrieval", tester.step_2_get_rtsp_url),
            ("stream_registration", tester.step_3_register_stream),
            ("callback_setup", tester.step_4_setup_detection_callbacks),
            ("stream_processor_init", tester.step_5_initialize_stream_processor),
            ("stream_start", tester.step_6_start_stream_processing),
        ]
        
        for step_name, step_func in steps:
            success = await step_func()
            if not success:
                print(f"\n❌ FAILED at step: {step_name}")
                return
        
        print("\n✅ Stream started successfully!")
        print(f"📹 MJPEG Stream available at: http://localhost:8000/api/dashboard/mjpeg/{tester.camera_id}")
        print(f"🔍 Detections API: http://localhost:8000/api/dashboard/latest-detections/{tester.camera_id}")
        print("\n🔄 Stream running... Press Ctrl+C to stop")
        
        # Keep running indefinitely
        while True:
            await asyncio.sleep(5)
            # Check if stream is still active
            if tester.camera_id not in _ACTIVE_STREAMS:
                print("❌ Stream stopped unexpectedly")
                break
            print(f"📡 Stream active... ({time.strftime('%H:%M:%S')})")
            
    except KeyboardInterrupt:
        print("\n🛑 Stopping stream...")
    except Exception as e:
        print(f"\n💥 Error: {e}")
    finally:
        # Cleanup
        try:
            await tester.step_8_cleanup()
            print("✅ Cleanup completed")
        except Exception as e:
            print(f"❌ Cleanup error: {e}")


async def main():
    """Main test runner"""
    import sys
    
    if len(sys.argv) > 1:
        if sys.argv[1] == "continuous":
            # Run continuous mode
            await run_continuous()
            return
        elif sys.argv[1] in ["1", "2", "3", "4", "5", "6", "7", "8"]:
            # Run individual step
            tester = PredictionFlowTester()
            await tester.run_individual_step(sys.argv[1])
            return
    
    # Default: run full test
    tester = PredictionFlowTester()
    monitor_duration = int(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1].isdigit() else 10
    await tester.run_full_test(monitor_duration)


if __name__ == "__main__":
    asyncio.run(main())
