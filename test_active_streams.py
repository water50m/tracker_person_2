#!/usr/bin/env python3
"""Debug script to check active streams from different modules"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from src.api.video_controller import _ACTIVE_STREAMS as video_controller_streams
from src.api.routes.dashboard_api import _ACTIVE_STREAMS as dashboard_streams

print("=== Active Streams Debug ===")
print(f"Video controller _ACTIVE_STREAMS: {list(video_controller_streams.keys())}")
print(f"Dashboard API _ACTIVE_STREAMS: {list(dashboard_streams.keys())}")
print(f"Are they the same object? {video_controller_streams is dashboard_streams}")
