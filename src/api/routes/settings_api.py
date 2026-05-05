import os
import json
import torch
from pathlib import Path
from fastapi import APIRouter, HTTPException, UploadFile, File
from pydantic import BaseModel
from src.config_loader import load_config as load_global_config, reload_config

router = APIRouter()

# ─── Cache CUDA info once at startup (torch init is slow) ─────
_CUDA_AVAILABLE: bool = torch.cuda.is_available()
_DEVICE_NAME: str    = torch.cuda.get_device_name(0) if _CUDA_AVAILABLE else "CPU"
_GPU_COUNT: int      = torch.cuda.device_count()    if _CUDA_AVAILABLE else 0


# Paths
MODELS_DIR = Path("models")
CONFIG_PATH = Path("config/system_settings.json")

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

class SettingsUpdate(BaseModel):
    paths: PathsUpdate | None = None
    models: ModelsUpdate | None = None
    detection: DetectionUpdate | None = None
    tracking: TrackingUpdate | None = None
    system: SystemUpdate | None = None


# ─── Endpoints ───────────────────────────────────────────────

@router.get("/settings")
async def get_settings():
    """Return current system configuration + hardware info."""
    cfg = load_config()

    cuda_available = _CUDA_AVAILABLE
    device_name    = _DEVICE_NAME
    gpu_count      = _GPU_COUNT

    detector_path = Path(cfg["models"]["detector_model"])
    classifier_path = Path(cfg["models"]["classifier_model"])
    reid_path = Path(cfg["models"]["reid_model_path"])

    return {
        "config": cfg,
        "hardware": {
            "device": "cuda" if cuda_available else "cpu",
            "device_name": device_name,
            "gpu_count": gpu_count,
            "cuda_available": cuda_available,
        },
        "models": {
            "detector": {
                "path": str(detector_path),
                "exists": detector_path.exists(),
                "size_mb": round(detector_path.stat().st_size / 1_048_576, 1) if detector_path.exists() else None,
            },
            "classifier": {
                "path": str(classifier_path),
                "exists": classifier_path.exists(),
                "size_mb": round(classifier_path.stat().st_size / 1_048_576, 1) if classifier_path.exists() else None,
            },
            "reid": {
                "path": str(reid_path),
                "exists": reid_path.exists(),
                "size_mb": round(reid_path.stat().st_size / 1_048_576, 1) if reid_path.exists() else None,
            },
        },
    }


@router.post("/settings")
async def update_settings(body: SettingsUpdate):
    """Partial-update system configuration."""
    cfg = load_config()
    update = body.model_dump(exclude_none=True)
    
    # Apply nested updates
    for section, values in update.items():
        if section in cfg and isinstance(cfg[section], dict) and values:
            cfg[section].update(values)
    
    save_config(cfg)
    return {"status": "saved", "config": cfg}






@router.get("/settings/models")
async def list_models():
    """List all .pt model files in the root and models/ directory."""
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
    return {"models": unique}


@router.post("/settings/models/upload")
async def upload_model(file: UploadFile = File(...)):
    """Upload a new .pt model file to the models/ directory."""
    if not file.filename or not file.filename.endswith(".pt"):
        raise HTTPException(status_code=400, detail="Only .pt model files are accepted")
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    dest = MODELS_DIR / file.filename
    try:
        contents = await file.read()
        dest.write_bytes(contents)
        size_mb = round(dest.stat().st_size / 1_048_576, 1)
        return {"status": "uploaded", "name": file.filename, "path": str(dest), "size_mb": size_mb}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
