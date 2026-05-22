from __future__ import annotations

import argparse
import json
from collections import Counter

from tests.evaluation.metrics import read_records, write_json


REQUIRED_FIELDS = [
    "camera_id",
    "track_id",
    "class_name",
    "bbox",
    "image_path",
    "video_time_offset",
]


def has_embedding(row: dict) -> bool:
    emb = row.get("embedding")
    return emb not in (None, "", [], "[]")


def evaluate(args: argparse.Namespace) -> dict:
    rows = read_records(args.input)
    missing_counter = Counter()
    duplicate_counter = Counter()
    image_paths = Counter()
    embedding_lengths = Counter()

    for row in rows:
        for field in REQUIRED_FIELDS:
            if row.get(field) in (None, ""):
                missing_counter[field] += 1
        key = (
            str(row.get("camera_id")),
            str(row.get("track_id")),
            str(row.get("video_time_offset")),
            str(row.get("bbox")),
        )
        duplicate_counter[key] += 1
        if row.get("image_path"):
            image_paths[str(row["image_path"])] += 1
        if has_embedding(row):
            emb = row.get("embedding")
            if isinstance(emb, str):
                try:
                    emb = json.loads(emb)
                except json.JSONDecodeError:
                    emb = [v for v in emb.replace(";", ",").split(",") if v.strip()]
            embedding_lengths[len(emb) if hasattr(emb, "__len__") else -1] += 1

    duplicates = {str(k): v for k, v in duplicate_counter.items() if v > 1}
    duplicate_image_paths = {k: v for k, v in image_paths.items() if v > 1}
    report = {
        "task": "detection_export_audit",
        "input": args.input,
        "rows": len(rows),
        "required_fields": REQUIRED_FIELDS,
        "missing_fields": dict(missing_counter),
        "duplicate_detection_keys": duplicates,
        "duplicate_image_paths": duplicate_image_paths,
        "embedding_rows": sum(embedding_lengths.values()),
        "embedding_lengths": dict(embedding_lengths),
        "passed": not missing_counter and not duplicates,
    }
    write_json(args.output, report)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit exported detection rows for DB/storage correctness.")
    parser.add_argument("--input", required=True, help="CSV/JSON/JSONL detection export.")
    parser.add_argument("--output", default="my-thesis-report/qa/detection-export-audit.json")
    args = parser.parse_args()
    report = evaluate(args)
    print(json.dumps({
        "rows": report["rows"],
        "passed": report["passed"],
        "missing_fields": report["missing_fields"],
        "duplicate_detection_count": len(report["duplicate_detection_keys"]),
        "embedding_lengths": report["embedding_lengths"],
        "output": args.output,
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
