from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any


WORKSPACE = Path(__file__).resolve().parents[1]
TARGET_CLASSES = ["short_sleeve", "long_sleeve", "shorts", "trousers", "skirt", "dress"]


def parse_json(text: str, fallback: Any) -> Any:
    if not text:
        return fallback
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return fallback


def parse_classes(text: str) -> list[str]:
    return [item for item in text.split("|") if item]


def path_as_uri(text: str) -> str:
    path = Path(text)
    try:
        return path.resolve().as_uri()
    except ValueError:
        return text


def load_csv_rows(path: Path) -> list[dict[str, Any]]:
    with path.open("r", newline="", encoding="utf-8") as file:
        rows = []
        for row in csv.DictReader(file):
            rows.append(
                {
                    "mode": row["mode"],
                    "frame": int(row["frame"]),
                    "timeSec": float(row["time_sec"]),
                    "detectionIndex": int(row["detection_index"]),
                    "personBox": parse_json(row["person_bbox"], []),
                    "personConfidence": float(row["person_confidence"] or 0),
                    "expectedClasses": parse_classes(row["expected_classes"]),
                    "predictedClasses": parse_classes(row["predicted_classes"]),
                    "correctLabels": parse_classes(row["correct_labels"]),
                    "missingLabels": parse_classes(row["missing_labels"]),
                    "extraLabels": parse_classes(row["extra_labels"]),
                    "exactMatch": row["exact_match"].lower() == "true",
                    "partialMatch": row["partial_match"].lower() == "true",
                    "confidenceMap": parse_json(row["confidence_map_json"], {}),
                    "rawDetections": parse_json(row["raw_detections_json"], []),
                    "finalDetections": parse_json(row["final_detections_json"], []),
                }
            )
        return rows


def build_data(output_dir: Path) -> dict[str, Any]:
    metrics_path = output_dir / "metrics.json"
    data = json.loads(metrics_path.read_text(encoding="utf-8"))
    videos = []
    for result in data.get("results", []):
        if result.get("status") != "completed":
            continue
        csv_path = output_dir / "videos" / result["name"] / "per_detection_predictions.csv"
        if not csv_path.exists():
            continue
        frames: dict[str, dict[str, list[dict[str, Any]]]] = {}
        for row in load_csv_rows(csv_path):
            frame_key = str(row.pop("frame"))
            mode = row.pop("mode")
            frames.setdefault(frame_key, {}).setdefault(mode, []).append(row)
        videos.append(
            {
                "name": result["name"],
                "videoPath": result["path"],
                "videoUri": path_as_uri(result["path"]),
                "expectedClasses": result["expected_classes"],
                "inputMode": result["input_mode"],
                "source": result["source"],
                "summary": result["modes"],
                "frames": frames,
            }
        )
    return {
        "metadata": data.get("metadata", {}),
        "targetClasses": TARGET_CLASSES,
        "videos": videos,
    }


HTML = r"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Clothing Video Prediction Viewer</title>
  <style>
    :root {
      color-scheme: light;
      font-family: Arial, Helvetica, sans-serif;
      --ink: #111827;
      --muted: #6b7280;
      --line: #d1d5db;
      --panel: #f8fafc;
      --accent: #2563eb;
    }
    * { box-sizing: border-box; }
    body { margin: 0; color: var(--ink); background: #ffffff; }
    header { padding: 16px 20px 8px; border-bottom: 1px solid var(--line); }
    h1 { margin: 0 0 8px; font-size: 20px; line-height: 1.25; }
    .sub { color: var(--muted); font-size: 13px; }
    main { display: grid; grid-template-columns: minmax(0, 1fr) 340px; gap: 16px; padding: 16px 20px 24px; }
    .stage { min-width: 0; }
    .videoWrap { position: relative; width: 100%; background: #0f172a; overflow: hidden; border: 1px solid #111827; }
    video, canvas { display: block; width: 100%; height: auto; }
    canvas { position: absolute; inset: 0; pointer-events: none; }
    aside { border-left: 1px solid var(--line); padding-left: 16px; }
    label { display: block; font-size: 12px; color: var(--muted); margin-bottom: 5px; }
    select, button { font: inherit; }
    select { width: 100%; min-height: 34px; border: 1px solid var(--line); border-radius: 6px; padding: 5px 8px; background: #fff; }
    button { min-height: 34px; border: 1px solid var(--line); border-radius: 6px; background: #fff; padding: 5px 10px; cursor: pointer; }
    button.primary { background: var(--accent); color: #fff; border-color: var(--accent); }
    .controls { display: grid; gap: 12px; }
    .row { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
    .field { display: grid; gap: 5px; }
    .chips { display: flex; gap: 6px; flex-wrap: wrap; }
    .chip { display: inline-flex; gap: 5px; align-items: center; border: 1px solid var(--line); border-radius: 999px; padding: 5px 9px; font-size: 13px; background: #fff; }
    .chip input { margin: 0; }
    .panel { background: var(--panel); border: 1px solid var(--line); border-radius: 8px; padding: 12px; }
    .stats { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 8px; font-size: 13px; }
    .stat strong { display: block; font-size: 16px; }
    .list { margin-top: 10px; max-height: 260px; overflow: auto; border-top: 1px solid var(--line); padding-top: 8px; font-size: 13px; line-height: 1.45; }
    .pill { display: inline-block; border-radius: 999px; padding: 2px 7px; margin: 2px 3px 2px 0; background: #e5e7eb; }
    .miss { background: #fee2e2; }
    .extra { background: #ffedd5; }
    .ok { background: #dcfce7; }
    @media (max-width: 980px) {
      main { grid-template-columns: 1fr; }
      aside { border-left: 0; padding-left: 0; }
    }
  </style>
</head>
<body>
  <header>
    <h1>Clothing Video Prediction Viewer</h1>
    <div class="sub">Use Before for raw model output, After for current tuned prediction rules.</div>
  </header>
  <main>
    <section class="stage">
      <div class="videoWrap">
        <video id="video" controls></video>
        <canvas id="overlay"></canvas>
      </div>
    </section>
    <aside>
      <div class="controls">
        <div class="field">
          <label for="videoSelect">Video</label>
          <select id="videoSelect"></select>
        </div>
        <div class="field">
          <label for="modeSelect">Prediction mode</label>
          <select id="modeSelect">
            <option value="before_raw">Before: raw model output</option>
            <option value="after_tuned" selected>After: tuned rules</option>
          </select>
        </div>
        <div class="row">
          <button class="primary" id="playPause">Play / Pause</button>
          <button id="stopBtn">Stop</button>
        </div>
        <div class="field">
          <label for="boxMode">Box display</label>
          <select id="boxMode">
            <option value="person" selected>Person only</option>
            <option value="clothing">Clothing only</option>
            <option value="both">Person + clothing</option>
          </select>
        </div>
        <div class="chips">
          <label class="chip"><input type="checkbox" id="showLabels" checked> labels</label>
          <label class="chip"><input type="checkbox" id="showDots" checked> bottom dots</label>
        </div>
        <div class="field">
          <label>Class filter</label>
          <div class="chips" id="classFilters"></div>
        </div>
        <div class="panel">
          <div class="stats">
            <div class="stat"><span>Frame</span><strong id="frameStat">0</strong></div>
            <div class="stat"><span>Predictions</span><strong id="predStat">0</strong></div>
            <div class="stat"><span>Exact</span><strong id="exactStat">-</strong></div>
            <div class="stat"><span>Expected</span><strong id="expectedStat">-</strong></div>
          </div>
          <div class="list" id="details"></div>
        </div>
      </div>
    </aside>
  </main>
  <script src="video_eval_viewer_data.js"></script>
  <script>
    const data = window.VIDEO_EVAL_DATA;
    const video = document.getElementById('video');
    const canvas = document.getElementById('overlay');
    const ctx = canvas.getContext('2d');
    const videoSelect = document.getElementById('videoSelect');
    const modeSelect = document.getElementById('modeSelect');
    const boxMode = document.getElementById('boxMode');
    const classFilters = document.getElementById('classFilters');
    const showLabels = document.getElementById('showLabels');
    const showDots = document.getElementById('showDots');
    const frameStat = document.getElementById('frameStat');
    const predStat = document.getElementById('predStat');
    const exactStat = document.getElementById('exactStat');
    const expectedStat = document.getElementById('expectedStat');
    const details = document.getElementById('details');
    const colors = {
      short_sleeve: '#2563eb',
      long_sleeve: '#0891b2',
      shorts: '#16a34a',
      trousers: '#9333ea',
      skirt: '#ea580c',
      dress: '#dc2626',
      person: '#facc15'
    };

    data.videos.forEach((item, index) => {
      const opt = document.createElement('option');
      opt.value = String(index);
      opt.textContent = `${item.name} (${item.expectedClasses.join(', ')})`;
      videoSelect.appendChild(opt);
    });

    data.targetClasses.forEach((name) => {
      const label = document.createElement('label');
      label.className = 'chip';
      label.innerHTML = `<input type="checkbox" value="${name}" checked> ${name}`;
      classFilters.appendChild(label);
    });

    function currentVideoData() {
      return data.videos[Number(videoSelect.value || 0)];
    }

    function activeClasses() {
      return new Set(Array.from(classFilters.querySelectorAll('input:checked')).map((el) => el.value));
    }

    function setupVideo() {
      const item = currentVideoData();
      video.src = item.videoUri;
      video.currentTime = 0;
      resizeCanvas();
      draw();
    }

    function resizeCanvas() {
      const rect = video.getBoundingClientRect();
      canvas.width = Math.max(1, Math.round(rect.width));
      canvas.height = Math.max(1, Math.round(rect.height));
      draw();
    }

    function frameRows(item, frame, mode) {
      const frames = item.frames;
      if (frames[String(frame)] && frames[String(frame)][mode]) return frames[String(frame)][mode];
      for (let i = 1; i <= 3; i += 1) {
        const prev = frames[String(frame - i)];
        if (prev && prev[mode]) return prev[mode];
        const next = frames[String(frame + i)];
        if (next && next[mode]) return next[mode];
      }
      return [];
    }

    function scaleBox(box, item) {
      const source = item.source;
      const sx = canvas.width / source.width;
      const sy = canvas.height / source.height;
      return [box[0] * sx, box[1] * sy, box[2] * sx, box[3] * sy];
    }

    function drawBox(box, color, label) {
      const [x1, y1, x2, y2] = box;
      const w = Math.max(1, x2 - x1);
      const h = Math.max(1, y2 - y1);
      ctx.strokeStyle = color;
      ctx.lineWidth = 2;
      ctx.strokeRect(x1, y1, w, h);
      if (showDots.checked) {
        ctx.fillStyle = color;
        ctx.beginPath();
        ctx.arc(x1 + w / 2, y2, 4, 0, Math.PI * 2);
        ctx.fill();
      }
      if (showLabels.checked && label) {
        ctx.font = '12px Arial';
        const textWidth = ctx.measureText(label).width + 8;
        const top = Math.max(0, y1 - 18);
        ctx.fillStyle = color;
        ctx.fillRect(x1, top, textWidth, 18);
        ctx.fillStyle = '#ffffff';
        ctx.fillText(label, x1 + 4, top + 13);
      }
    }

    function renderDetails(rows, frame) {
      const expected = currentVideoData().expectedClasses.join(', ');
      frameStat.textContent = String(frame);
      predStat.textContent = String(rows.length);
      expectedStat.textContent = expected || '-';
      exactStat.textContent = rows.length ? `${rows.filter((row) => row.exactMatch).length}/${rows.length}` : '-';
      details.innerHTML = rows.map((row) => {
        const predicted = row.predictedClasses.map((x) => `<span class="pill">${x}</span>`).join('') || '-';
        const missing = row.missingLabels.map((x) => `<span class="pill miss">${x}</span>`).join('');
        const extra = row.extraLabels.map((x) => `<span class="pill extra">${x}</span>`).join('');
        const ok = row.correctLabels.map((x) => `<span class="pill ok">${x}</span>`).join('');
        return `<div><strong>#${row.detectionIndex}</strong> predicted ${predicted}<br>${ok}${missing}${extra}</div>`;
      }).join('');
    }

    function draw() {
      const item = currentVideoData();
      if (!item) return;
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      const fps = item.source.fps || 30;
      const frame = Math.round(video.currentTime * fps);
      const rows = frameRows(item, frame, modeSelect.value);
      const filters = activeClasses();
      const mode = boxMode.value;
      for (const row of rows) {
        if (mode === 'person' || mode === 'both') {
          drawBox(scaleBox(row.personBox, item), colors.person, `person ${row.personConfidence.toFixed(2)}`);
        }
        if (mode === 'clothing' || mode === 'both') {
          for (const det of row.finalDetections) {
            if (!filters.has(det.class)) continue;
            const conf = Number(det.confidence || 0).toFixed(2);
            drawBox(scaleBox(det.bbox, item), colors[det.class] || '#111827', `${det.class} ${conf}`);
          }
        }
      }
      renderDetails(rows, frame);
    }

    document.getElementById('playPause').addEventListener('click', () => video.paused ? video.play() : video.pause());
    document.getElementById('stopBtn').addEventListener('click', () => { video.pause(); video.currentTime = 0; draw(); });
    [videoSelect, modeSelect, boxMode, showLabels, showDots].forEach((el) => el.addEventListener('change', () => {
      if (el === videoSelect) setupVideo();
      draw();
    }));
    classFilters.addEventListener('change', draw);
    video.addEventListener('loadedmetadata', resizeCanvas);
    video.addEventListener('timeupdate', draw);
    video.addEventListener('play', function loop() {
      draw();
      if (!video.paused && !video.ended) requestAnimationFrame(loop);
    });
    window.addEventListener('resize', resizeCanvas);
    setupVideo();
  </script>
</body>
</html>
"""


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", default="track_result/clothing_video_before_after_eval")
    args = parser.parse_args()

    output_dir = (WORKSPACE / args.output_dir).resolve()
    viewer_data = build_data(output_dir)
    (output_dir / "video_eval_viewer_data.js").write_text(
        "window.VIDEO_EVAL_DATA = " + json.dumps(viewer_data, ensure_ascii=False) + ";\n",
        encoding="utf-8",
    )
    (output_dir / "video_eval_viewer.html").write_text(HTML, encoding="utf-8")
    print(output_dir / "video_eval_viewer.html")


if __name__ == "__main__":
    main()
