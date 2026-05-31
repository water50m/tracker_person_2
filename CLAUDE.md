# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

### Running the system

Start all services together (interactive, prompts for Docker DB):
```
python start_dev.py
```

Or start individually:
```bash
# Backend (FastAPI)
python -m uvicorn src.api.main:app --host 0.0.0.0 --port 8000 --reload

# Frontend (Next.js)
cd ui && npm run dev

# Docker services (PostgreSQL + MinIO + Redis)
cd docker && docker-compose up -d
```

### Package management

This project uses **uv** (not pip directly). PyTorch is pulled from a custom CUDA 12.4 index.
```bash
uv sync              # install all dependencies
uv run python ...    # run scripts inside venv
```

### Tests
```bash
uv run pytest                          # all tests
uv run pytest tests/unit/              # unit tests only
uv run pytest -m "not integration"    # skip tests that need DB/MinIO
uv run pytest tests/path/test_file.py::TestClass::test_func  # single test
```

### Frontend
```bash
cd ui
npm install
npm run dev    # dev server at http://localhost:3000
npm run build  # production build
npm run lint
```

---

## Architecture

### Storage modes (critical concept)

Every API endpoint branches on `get_storage_mode()` from `src/config_loader.py`:

- **`"json"` mode** (current default): Results are stored as local JSON files under `track_result/`. No PostgreSQL or MinIO needed. `JsonInvestigationService` handles all queries.
- **`"db"` mode**: Uses PostgreSQL (via SQLAlchemy in `src/services/database.py`) and MinIO for image blobs. `DetectionController` (`src/api/controllers.py`) handles queries.

Switch modes in `config/system_settings.json` → `storage.mode`. The JSON root path is `storage.json_root`.

### Request flow

```
HTTP request → src/api/main.py
  └─ branches on get_storage_mode()
       ├─ json  → JsonInvestigationService (src/services/json_investigation_service.py)
       └─ db    → DetectionController (src/api/controllers.py) → DatabaseService
```

Routers are registered in `main.py` with these prefixes:
- `/api/video` — video upload & processing queue
- `/api/dashboard` — camera feeds, live detections
- `/api/logs` — log viewer
- `/api` — cameras, relationships, settings, search
- WebSocket routes (no prefix) — real-time streaming

### Video processing pipeline

`src/services/video_processor.py` is the main pipeline:
1. **Detection**: `src/ai/detector.py` (YOLOv11) — detects persons per frame
2. **Tracking**: `src/ai/tracker.py` (ByteTrack) — assigns/maintains track IDs
3. **Classification**: `src/ai/classifier.py` — YOLO-based clothing classification
4. **Color analysis**: `src/ai/color_system.py` — 63 discrete colors + 22 groups
5. **Output**: Writes to JSON (`track_result/`) or database depending on storage mode

Real-time streaming uses `src/services/stream_processor.py` + WebSocket route at `src/api/routes/realtime.py`.

### Configuration

All runtime config lives in `config/system_settings.json` and is loaded once via a singleton in `src/config_loader.py`. The helper functions (`get_storage_mode()`, `get_detector_model_path()`, etc.) are used throughout — do not read the JSON directly.

**Feature flags** (env-var controlled, for gradual refactoring rollout):
- `USE_REFACTORED_IMAGE_ANALYZER`
- `USE_REFACTORED_VIDEO_PROCESSOR`
- `USE_REFACTORED_STREAM_PROCESSOR`
- `ROLLOUT_PERCENTAGE` (0–100, for camera-level gradual rollout)

Set via `$env:USE_REFACTORED_VIDEO_PROCESSOR = "true"` before running.

### Model files

Model `.pt` files are gitignored and must be placed locally:
- `yolo11n.pt` or `yolo11s.pt` — person detector (path from config `models.detector_model`)
- `models/prepare_dataset.pt` — clothing classifier
- `osnet_x0_25_msmt17.pt` — Re-ID model

YOLO auto-downloads to `.ultralytics/` (set in `main.py` lifespan).

### Frontend (ui/)

Next.js 15 / React 19 app. Key areas:
- `ui/src/app/` — page routes
- `ui/src/components/` — React components; uses `@xyflow/react` for relationship graphs and `hls.js` for video streaming
- API calls go to `http://localhost:8000`

### Docker services

`docker/docker-compose.yml` runs PostgreSQL, MinIO, and Redis for local development. Only needed for `"db"` storage mode. Staging deployment is in `deploy/staging/`.
