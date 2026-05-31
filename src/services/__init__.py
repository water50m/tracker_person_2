"""Lazy service exports.

Keeping these imports lazy prevents DB-only paths from loading MinIO/OpenCV
during FastAPI startup.
"""

__all__ = ["DatabaseService", "StorageService"]


def __getattr__(name: str):
    if name == "DatabaseService":
        from .database import DatabaseService

        return DatabaseService
    if name == "StorageService":
        from .storage import StorageService

        return StorageService
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
