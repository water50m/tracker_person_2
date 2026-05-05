import sys
import os

# Ensure src in path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.api.main import app

for route in app.routes:
    method = getattr(route, "methods", "")
    path = getattr(route, "path", "")
    if "video" in path or "active" in path:
        print(f"{method} {path}")
