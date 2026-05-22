from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from pathlib import Path

import cv2

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = PROJECT_ROOT / "src"
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from src.ai.color_analysis_unified import analyze_clothing_colors  # noqa: E402
from tests.evaluation.metrics import classification_report, safe_float, write_json  # noqa: E402


def load_manifest(path: Path) -> list[dict]:
    if path.suffix.lower() == ".csv":
        with path.open("r", encoding="utf-8-sig", newline="") as f:
            return [dict(row) for row in csv.DictReader(f)]
    if path.suffix.lower() == ".jsonl":
        with path.open("r", encoding="utf-8") as f:
            return [json.loads(line) for line in f if line.strip()]
    data = json.loads(path.read_text(encoding="utf-8"))
    return data if isinstance(data, list) else data["items"]


def crop_from_record(image, record: dict):
    if all(k in record and str(record[k]) != "" for k in ("x1", "y1", "x2", "y2")):
        x1, y1, x2, y2 = [int(safe_float(record[k])) for k in ("x1", "y1", "x2", "y2")]
        h, w = image.shape[:2]
        x1 = max(0, min(w, x1))
        x2 = max(0, min(w, x2))
        y1 = max(0, min(h, y1))
        y2 = max(0, min(h, y2))
        if x2 > x1 and y2 > y1:
            return image[y1:y2, x1:x2]
    return image


def evaluate(args: argparse.Namespace) -> dict:
    records = load_manifest(Path(args.manifest))
    y_true = []
    y_pred = []
    rows = []
    latencies = []

    for record in records:
        image_path = Path(record["image_path"])
        if not image_path.is_absolute():
            image_path = Path(args.image_root or ".") / image_path
        expected_color = str(record.get("primary_color") or record.get("color") or record.get("label"))
        image = cv2.imread(str(image_path))
        if image is None:
            rows.append({"image_path": str(image_path), "expected_color": expected_color, "error": "image_read_failed"})
            continue

        crop = crop_from_record(image, record)
        t0 = time.perf_counter()
        analysis = analyze_clothing_colors(crop)
        latency_ms = (time.perf_counter() - t0) * 1000
        predicted_color = analysis.get("primary_detailed_color", "unknown")
        y_true.append(expected_color)
        y_pred.append(predicted_color)
        latencies.append(latency_ms)
        rows.append({
            "image_path": str(image_path),
            "expected_color": expected_color,
            "predicted_color": predicted_color,
            "top_colors": analysis.get("top_colors", []),
            "brightness_groups": analysis.get("brightness_groups", {}),
            "vibrancy_groups": analysis.get("vibrancy_groups", {}),
            "temperature_groups": analysis.get("temperature_groups", {}),
            "latency_ms": latency_ms,
        })

    report = classification_report(y_true, y_pred)
    report.update({
        "task": "color_analysis",
        "manifest": args.manifest,
        "samples_read": len(y_true),
        "samples_failed": len(records) - len(y_true),
        "avg_latency_ms": sum(latencies) / len(latencies) if latencies else 0.0,
        "results": rows,
    })
    write_json(args.output, report)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate primary clothing color analysis on labeled image crops.")
    parser.add_argument("--manifest", required=True, help="CSV/JSON/JSONL with image_path,primary_color[,x1,y1,x2,y2].")
    parser.add_argument("--image-root", default="")
    parser.add_argument("--output", default="my-thesis-report/qa/color-analysis-eval.json")
    args = parser.parse_args()
    report = evaluate(args)
    print(json.dumps({
        "total": report["total"],
        "accuracy": report["accuracy"],
        "macro_f1": report["macro_f1"],
        "avg_latency_ms": report["avg_latency_ms"],
        "output": args.output,
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
