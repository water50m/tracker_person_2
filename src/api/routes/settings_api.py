import os
import json
import time
from pathlib import Path
from fastapi import APIRouter, HTTPException, UploadFile, File
from pydantic import BaseModel
from src.config_loader import load_config as load_global_config, reload_config

router = APIRouter()

# Paths
MODELS_DIR = Path("models")
CONFIG_PATH = Path("config/system_settings.json")
_MODELS_CACHE: dict | None = None
_MODELS_CACHE_TIME = 0.0
_MODELS_CACHE_TTL_SEC = 10.0

# ─── Config loader (uses global config_loader module) ──────────
def load_config() -> dict:
    """Load configuration from system_settings.json using global config_loader."""
    return load_global_config()


def save_config(cfg: dict):
    """Save configuration to system_settings.json and reload global cache."""
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(json.dumps(cfg, indent=2))
    reload_config()  # Reload global cache after saving


# ─── Pydantic schemas ──────────────────────────────────────────
class PathsUpdate(BaseModel):
    upload_dir: str | None = None
    output_dir: str | None = None
    temp_dir: str | None = None
    log_dir: str | None = None

class ModelsUpdate(BaseModel):
    detector_model: str | None = None
    classifier_model: str | None = None
    reid_model_path: str | None = None

class DetectionUpdate(BaseModel):
    detection_confidence: float | None = None
    iou_threshold: float | None = None
    detection_enabled: bool | None = None

class TrackingUpdate(BaseModel):
    max_tracks: int | None = None
    frame_skip: int | None = None
    classification_enabled: bool | None = None

class SystemUpdate(BaseModel):
    device: str | None = None
    batch_size: int | None = None
    num_workers: int | None = None

class StorageUpdate(BaseModel):
    mode: str | None = None
    json_root: str | None = None
    json_index: str | None = None

class ProcessingUpdate(BaseModel):
    color_remove_background: bool | None = None

class StreamUpdate(BaseModel):
    frame_skip_mode: str | None = None   # "none" | "fixed" | "auto"
    frame_skip_n: int | None = None
    target_fps: int | None = None
    buffer_size: int | None = None
    ai_frame_skip: int | None = None

class SettingsUpdate(BaseModel):
    paths: PathsUpdate | None = None
    models: ModelsUpdate | None = None
    detection: DetectionUpdate | None = None
    tracking: TrackingUpdate | None = None
    system: SystemUpdate | None = None
    storage: StorageUpdate | None = None
    processing: ProcessingUpdate | None = None
    stream: StreamUpdate | None = None


# ─── Endpoints ───────────────────────────────────────────────

@router.get("/settings")
async def get_settings():
    """Return current system configuration + hardware info."""
    start = time.perf_counter()
    cfg = load_config()

    configured_device = str(cfg.get("system", {}).get("device", "cpu")).lower()
    cuda_configured = configured_device == "cuda"

    detector_path = Path(cfg["models"]["detector_model"])
    classifier_path = Path(cfg["models"]["classifier_model"])
    reid_path = Path(cfg["models"]["reid_model_path"])
    detector_exists = detector_path.exists()
    classifier_exists = classifier_path.exists()
    reid_exists = reid_path.exists()
    duration_ms = (time.perf_counter() - start) * 1000
    print(f"[SETTINGS-TIME] GET /settings config+stat={duration_ms:.1f}ms", flush=True)

    return {
        "config": cfg,
        "hardware": {
            "device": "cuda" if cuda_configured else "cpu",
            "device_name": "CUDA (configured)" if cuda_configured else "CPU",
            "gpu_count": 1 if cuda_configured else 0,
            "cuda_available": cuda_configured,
        },
        "models": {
            "detector": {
                "path": str(detector_path),
                "exists": detector_exists,
                "size_mb": round(detector_path.stat().st_size / 1_048_576, 1) if detector_exists else None,
            },
            "classifier": {
                "path": str(classifier_path),
                "exists": classifier_exists,
                "size_mb": round(classifier_path.stat().st_size / 1_048_576, 1) if classifier_exists else None,
            },
            "reid": {
                "path": str(reid_path),
                "exists": reid_exists,
                "size_mb": round(reid_path.stat().st_size / 1_048_576, 1) if reid_exists else None,
            },
        },
    }


@router.post("/settings")
async def update_settings(body: SettingsUpdate):
    """Partial-update system configuration."""
    cfg = load_config()
    update = body.model_dump(exclude_none=True)

    storage_update = update.get("storage")
    if storage_update and "mode" in storage_update:
        mode = str(storage_update["mode"]).lower()
        if mode not in {"db", "json"}:
            raise HTTPException(status_code=400, detail="storage.mode must be 'db' or 'json'")
        storage_update["mode"] = mode
    
    # Apply nested updates — create section if it doesn't exist yet
    for section, values in update.items():
        if not values:
            continue
        if isinstance(values, dict):
            if section not in cfg or not isinstance(cfg[section], dict):
                cfg[section] = {}
            cfg[section].update(values)
        else:
            cfg[section] = values

    save_config(cfg)
    return {"status": "saved", "config": cfg}






@router.get("/settings/models")
async def list_models():
    """List all .pt model files in the root and models/ directory."""
    global _MODELS_CACHE, _MODELS_CACHE_TIME
    start = time.perf_counter()
    if _MODELS_CACHE and time.time() - _MODELS_CACHE_TIME < _MODELS_CACHE_TTL_SEC:
        print("[SETTINGS-TIME] GET /settings/models cache=hit duration=0.0ms", flush=True)
        return _MODELS_CACHE

    files = []
    search_dirs = [MODELS_DIR, Path(".")]  # models/ first, root as fallback
    for d in search_dirs:
        if d.exists() and d.is_dir():
            # glob only the immediate directory (no recursive) for speed
            for f in d.glob("*.pt"):
                files.append({
                    "name": f.name,
                    "path": str(f.resolve()),
                    "size_mb": round(f.stat().st_size / 1_048_576, 1),
                })
    seen: set[str] = set()
    unique = []
    for f in files:
        if f["path"] not in seen:
            seen.add(f["path"])
            unique.append(f)
    _MODELS_CACHE = {"models": unique}
    _MODELS_CACHE_TIME = time.time()
    duration_ms = (time.perf_counter() - start) * 1000
    print(f"[SETTINGS-TIME] GET /settings/models cache=miss files={len(unique)} duration={duration_ms:.1f}ms", flush=True)
    return _MODELS_CACHE


@router.post("/settings/models/upload")
async def upload_model(file: UploadFile = File(...)):
    """Upload a new .pt model file to the models/ directory."""
    global _MODELS_CACHE, _MODELS_CACHE_TIME
    if not file.filename or not file.filename.endswith(".pt"):
        raise HTTPException(status_code=400, detail="Only .pt model files are accepted")
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    dest = MODELS_DIR / file.filename
    try:
        contents = await file.read()
        dest.write_bytes(contents)
        _MODELS_CACHE = None
        _MODELS_CACHE_TIME = 0.0
        size_mb = round(dest.stat().st_size / 1_048_576, 1)
        return {"status": "uploaded", "name": file.filename, "path": str(dest), "size_mb": size_mb}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
