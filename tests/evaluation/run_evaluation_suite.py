from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def run_step(name: str, command: list[str], skip: bool) -> dict:
    if skip:
        return {"name": name, "skipped": True, "returncode": None}
    print(f"\n[evaluation] running {name}")
    print(" ".join(command))
    proc = subprocess.run(command, cwd=PROJECT_ROOT, text=True, capture_output=True)
    if proc.stdout:
        print(proc.stdout)
    if proc.stderr:
        print(proc.stderr, file=sys.stderr)
    return {
        "name": name,
        "skipped": False,
        "returncode": proc.returncode,
        "stdout": proc.stdout[-4000:],
        "stderr": proc.stderr[-4000:],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run configured evaluation scripts.")
    parser.add_argument("--config", default="tests/evaluation/evaluation_config.example.json")
    parser.add_argument("--only", nargs="*", default=[], help="Optional subset: clothing color tracking search database_audit")
    parser.add_argument("--skip-missing", action="store_true", help="Skip steps whose configured inputs do not exist.")
    parser.add_argument("--output", default="my-thesis-report/qa/evaluation-suite-summary.json")
    args = parser.parse_args()

    config = json.loads((PROJECT_ROOT / args.config).read_text(encoding="utf-8"))
    only = set(args.only)
    results = []

    def should_run(step: str) -> bool:
        return not only or step in only

    def exists(path_value: str) -> bool:
        return bool(path_value) and (PROJECT_ROOT / path_value).exists()

    if should_run("clothing"):
        c = config["clothing"]
        skip = args.skip_missing and not exists(c["manifest"])
        results.append(run_step("clothing", [
            sys.executable, "tests/evaluation/evaluate_clothing_model.py",
            "--manifest", c["manifest"],
            "--image-root", c.get("image_root", ""),
            "--model", c.get("model", ""),
            "--output", c.get("output", "my-thesis-report/qa/clothing-model-eval.json"),
        ], skip))

    if should_run("color"):
        c = config["color"]
        skip = args.skip_missing and not exists(c["manifest"])
        results.append(run_step("color", [
            sys.executable, "tests/evaluation/evaluate_color_analysis.py",
            "--manifest", c["manifest"],
            "--image-root", c.get("image_root", ""),
            "--output", c.get("output", "my-thesis-report/qa/color-analysis-eval.json"),
        ], skip))

    if should_run("tracking"):
        c = config["tracking"]
        command = [
            sys.executable, "tests/evaluation/evaluate_tracking_reid.py",
            "--video", c["video"],
            "--output-dir", c.get("output_dir", "my-thesis-report/qa/tracking-reid"),
            "--frame-skip", str(c.get("frame_skip", 5)),
            "--camera-id", c.get("camera_id", "EVAL-CAM-01"),
            "--mode", c.get("mode", "both"),
        ]
        if c.get("ground_truth"):
            command.extend(["--ground-truth", c["ground_truth"]])
        skip = args.skip_missing and not exists(c["video"])
        results.append(run_step("tracking", command, skip))

    if should_run("search"):
        c = config["search"]
        skip = args.skip_missing and (not exists(c["queries"]) or not exists(c["results"]))
        results.append(run_step("search", [
            sys.executable, "tests/evaluation/evaluate_search_results.py",
            "--queries", c["queries"],
            "--results", c["results"],
            "--output", c.get("output", "my-thesis-report/qa/search-eval.json"),
        ], skip))

    if should_run("database_audit"):
        c = config["database_audit"]
        skip = args.skip_missing and not exists(c["input"])
        results.append(run_step("database_audit", [
            sys.executable, "tests/evaluation/audit_detection_export.py",
            "--input", c["input"],
            "--output", c.get("output", "my-thesis-report/qa/detection-export-audit.json"),
        ], skip))

    summary = {
        "config": args.config,
        "results": results,
        "passed": all(r["skipped"] or r["returncode"] == 0 for r in results),
    }
    out = PROJECT_ROOT / args.output
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"passed": summary["passed"], "output": args.output}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
