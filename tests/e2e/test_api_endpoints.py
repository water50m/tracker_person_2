"""
E2E Tests for API Endpoints
Tests that all API endpoints work after Re-ID integration
"""
import unittest
import requests
import time

BASE_URL = "http://localhost:8000"


class TestAPIEndpoints(unittest.TestCase):
    """ทดสอบ API endpoints หลัง integrate Re-ID"""
    
    @classmethod
    def setUpClass(cls):
        """Check if server is running"""
        try:
            response = requests.get(f"{BASE_URL}/api/dashboard/cameras", timeout=5)
            cls.server_running = response.status_code == 200
        except:
            cls.server_running = False
            print("⚠️ Server not running - skipping API tests")
    
    def skip_if_server_down(self):
        """Skip test if server is not running"""
        if not self.server_running:
            self.skipTest("Server not running")
    
    def test_dashboard_cameras(self):
        """GET /api/dashboard/cameras"""
        self.skip_if_server_down()
        response = requests.get(f"{BASE_URL}/api/dashboard/cameras")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIsInstance(data, list)
        print(f"✅ Dashboard cameras: {len(data)} cameras")
    
    def test_video_detections(self):
        """GET /api/video/detections"""
        self.skip_if_server_down()
        response = requests.get(f"{BASE_URL}/api/video/detections?limit=10")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIsInstance(data, list)
        print(f"✅ Video detections: {len(data)} detections")
    
    def test_search_persons(self):
        """GET /api/search/persons"""
        self.skip_if_server_down()
        response = requests.get(f"{BASE_URL}/api/search/persons?clothing=Shirt")
        self.assertIn(response.status_code, [200, 404])  # 404 if no results
        print(f"✅ Search persons: status {response.status_code}")
    
    def test_active_streams(self):
        """GET /api/video/active-streams"""
        self.skip_if_server_down()
        response = requests.get(f"{BASE_URL}/api/video/active-streams")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIsInstance(data, list)
        print(f"✅ Active streams: {len(data)} streams")
    
    def test_events_stream_connect(self):
        """GET /api/events/stream (SSE connection)"""
        self.skip_if_server_down()
        response = requests.get(f"{BASE_URL}/api/events/stream", stream=True)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers.get('content-type'), 'text/event-stream')
        
        # Read first few events
        events = []
        for line in response.iter_lines():
            if line:
                events.append(line.decode('utf-8'))
            if len(events) >= 2:
                break
        
        self.assertGreater(len(events), 0)
        print(f"✅ SSE stream connected, received {len(events)} events")


if __name__ == "__main__":
    unittest.main(verbosity=2)
