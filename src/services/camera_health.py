"""
Camera reachability monitor.

Uses the cheapest possible check — a raw TCP connect to the camera's host:port —
instead of opening the video stream (which is slow and decodes frames). Runs on a
background loop every CHECK_INTERVAL seconds and exposes the latest status.

Status shape per camera_id:
    {
        "reachable": bool,
        "latency_ms": float | None,
        "checked_at": iso8601 str,
        "error": str | None,
    }
"""
from __future__ import annotations

import asyncio
import socket
import time
from datetime import datetime
from urllib.parse import urlparse
from typing import Optional

CHECK_INTERVAL = 600  # 10 minutes
CONNECT_TIMEOUT = 3.0  # seconds — fast fail for unreachable hosts

_DEFAULT_PORTS = {
    "rtsp": 554,
    "rtmp": 1935,
    "http": 80,
    "https": 443,
}

# camera_id → status dict
_STATUS: dict[str, dict] = {}
_lock = asyncio.Lock()


def _parse_host_port(url: str) -> tuple[Optional[str], Optional[int]]:
    """Extract (host, port) from a stream URL, applying scheme defaults."""
    if not url:
        return None, None
    # urlparse needs a scheme; webcam indices ("0","1") aren't network sources
    if url.isdigit():
        return None, None
    try:
        parsed = urlparse(url)
        host = parsed.hostname
        port = parsed.port or _DEFAULT_PORTS.get((parsed.scheme or "").lower())
        return host, port
    except Exception:
        return None, None


def _tcp_check(host: str, port: int, timeout: float = CONNECT_TIMEOUT) -> tuple[bool, float, Optional[str]]:
    """Blocking TCP connect. Returns (reachable, latency_ms, error)."""
    start = time.perf_counter()
    sock = None
    try:
        sock = socket.create_connection((host, port), timeout=timeout)
        latency = (time.perf_counter() - start) * 1000
        return True, latency, None
    except Exception as e:
        latency = (time.perf_counter() - start) * 1000
        return False, latency, str(e)
    finally:
        if sock is not None:
            try:
                sock.close()
            except Exception:
                pass


async def check_camera(camera_id: str, url: str) -> dict:
    """Check one camera's reachability and store the result. Returns the status dict."""
    host, port = _parse_host_port(url)
    if not host or not port:
        status = {
            "reachable": False,
            "latency_ms": None,
            "checked_at": datetime.now().isoformat(),
            "error": "Unsupported or local source (no host:port)",
        }
    else:
        loop = asyncio.get_running_loop()
        reachable, latency, error = await loop.run_in_executor(None, _tcp_check, host, port)
        status = {
            "reachable": reachable,
            "latency_ms": round(latency, 1),
            "checked_at": datetime.now().isoformat(),
            "error": None if reachable else error,
        }
    async with _lock:
        _STATUS[camera_id] = status
    return status


def _list_cameras() -> list[tuple[str, str]]:
    """Return [(camera_id, url), ...] from the active storage backend."""
    from src.config_loader import get_storage_mode
    pairs: list[tuple[str, str]] = []
    try:
        if get_storage_mode() == "json":
            from src.api.routes.dashboard_api import _load_json_streams
            for s in _load_json_streams():
                url = s.get("rtsp_url") or ""
                if url:
                    pairs.append((s["camera_id"], url))
        else:
            from src.services.database import DatabaseService
            db = DatabaseService()
            db._ensure_connection()
            with db.conn.cursor() as cur:
                cur.execute("SELECT id, source_url FROM cameras")
                for row in cur.fetchall():
                    if row[1]:
                        pairs.append((str(row[0]), row[1]))
    except Exception as e:
        print(f"[CameraHealth] Failed to list cameras: {e}")
    return pairs


async def check_all() -> dict[str, dict]:
    """Check every configured camera concurrently."""
    pairs = _list_cameras()
    if not pairs:
        return {}
    await asyncio.gather(*(check_camera(cid, url) for cid, url in pairs))
    async with _lock:
        return dict(_STATUS)


def get_status(camera_id: str) -> Optional[dict]:
    return _STATUS.get(camera_id)


def get_all_status() -> dict[str, dict]:
    return dict(_STATUS)


async def monitor_loop(stop: asyncio.Event):
    """Background loop — checks all cameras every CHECK_INTERVAL until stopped."""
    print(f"[CameraHealth] Monitor started (interval={CHECK_INTERVAL}s)")
    # Initial check shortly after startup
    try:
        await check_all()
        print(f"[CameraHealth] Initial check done: {get_all_status()}")
    except Exception as e:
        print(f"[CameraHealth] Initial check error: {e}")

    while not stop.is_set():
        try:
            await asyncio.wait_for(stop.wait(), timeout=CHECK_INTERVAL)
        except asyncio.TimeoutError:
            pass  # interval elapsed → recheck
        if stop.is_set():
            break
        try:
            await check_all()
        except Exception as e:
            print(f"[CameraHealth] Periodic check error: {e}")
    print("[CameraHealth] Monitor stopped")
