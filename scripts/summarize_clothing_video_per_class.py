from __future__ import annotations

import csv
import json
import argparse
from pathlib import Path


CLASSES = ["short_sleeve", "long_sleeve", "shorts", "trousers", "skirt", "dress"]
MODES = ["before_raw", "after_tuned"]


def safe_div(a: float, b: float) -> float:
    return a / b if b else 0.0


def pct(value: float) -> str:
    return f"{value * 100:.2f}%"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default=r"E:\ALL_CODE\my-project\track_result\clothing_video_before_after_eval_full")
    args = parser.parse_args()
    base = Path(args.base)
    data = json.loads((base / "metrics.json").read_text(encoding="utf-8"))
    rows: list[dict[str, object]] = []

    for mode in MODES:
        agg = {
            label: {"support": 0, "predicted": 0, "tp": 0, "fp": 0, "fn": 0, "conf_sum": 0.0}
            for label in CLASSES
        }
        for result in data["results"]:
            per_class = result["modes"][mode]["per_class"]
            for label in CLASSES:
                item = per_class[label]
                agg[label]["support"] += item["support"]
                agg[label]["predicted"] += item["predicted"]
                agg[label]["tp"] += item["tp"]
                agg[label]["fp"] += item["fp"]
                agg[label]["fn"] += item["fn"]
                agg[label]["conf_sum"] += item.get("avg_confidence_when_predicted", 0.0) * item["predicted"]

        for label in CLASSES:
            item = agg[label]
            precision = safe_div(item["tp"], item["tp"] + item["fp"])
            recall = safe_div(item["tp"], item["tp"] + item["fn"])
            f1 = safe_div(2 * precision * recall, precision + recall)
            rows.append(
                {
                    "scope": "overall",
                    "video": "ALL",
                    "mode": mode,
                    "class": label,
                    "support": item["support"],
                    "predicted": item["predicted"],
                    "tp": item["tp"],
                    "fp_extra": item["fp"],
                    "fn_missing": item["fn"],
                    "precision": precision,
                    "recall": recall,
                    "f1": f1,
                    "avg_confidence_when_predicted": safe_div(item["conf_sum"], item["predicted"]),
                }
            )

    for result in data["results"]:
        for mode in MODES:
            for label, item in result["modes"][mode]["per_class"].items():
                rows.append(
                    {
                        "scope": "per_video",
                        "video": result["name"],
                        "mode": mode,
                        "class": label,
                        "support": item["support"],
                        "predicted": item["predicted"],
                        "tp": item["tp"],
                        "fp_extra": item["fp"],
                        "fn_missing": item["fn"],
                        "precision": item["precision"],
                        "recall": item["recall"],
                        "f1": item["f1"],
                        "avg_confidence_when_predicted": item.get("avg_confidence_when_predicted", 0.0),
                    }
                )

    with (base / "per_class_summary.csv").open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    lines = [
        "# สรุปผลแยก Class: ก่อนจูน vs หลังจูน",
        "",
        "## ภาพรวมทุกวิดีโอ",
        "",
        "| Class | Mode | GT/support | Predicted | TP | Extra/FP | Missing/FN | Precision | Recall | F1 | Avg conf |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for label in CLASSES:
        for mode in MODES:
            row = next(item for item in rows if item["scope"] == "overall" and item["class"] == label and item["mode"] == mode)
            mode_label = "ก่อนจูน raw" if mode == "before_raw" else "หลังจูน tuned"
            lines.append(
                f"| {label} | {mode_label} | {row['support']} | {row['predicted']} | {row['tp']} | "
                f"{row['fp_extra']} | {row['fn_missing']} | {pct(float(row['precision']))} | "
                f"{pct(float(row['recall']))} | {float(row['f1']):.4f} | "
                f"{float(row['avg_confidence_when_predicted']):.4f} |"
            )
        before = next(item for item in rows if item["scope"] == "overall" and item["class"] == label and item["mode"] == "before_raw")
        after = next(item for item in rows if item["scope"] == "overall" and item["class"] == label and item["mode"] == "after_tuned")
        lines.append(
            f"| {label} | เปลี่ยนแปลง |  | {int(after['predicted']) - int(before['predicted']):+d} | "
            f"{int(after['tp']) - int(before['tp']):+d} | {int(after['fp_extra']) - int(before['fp_extra']):+d} | "
            f"{int(after['fn_missing']) - int(before['fn_missing']):+d} | "
            f"{float(after['precision']) - float(before['precision']):+.4f} | "
            f"{float(after['recall']) - float(before['recall']):+.4f} | "
            f"{float(after['f1']) - float(before['f1']):+.4f} | "
            f"{float(after['avg_confidence_when_predicted']) - float(before['avg_confidence_when_predicted']):+.4f} |"
        )

    lines.extend(
        [
            "",
            "## อ่านผลแบบเร็ว",
            "",
            "- Precision สูงขึ้น = class นั้นทายเกินน้อยลง",
            "- Recall สูงขึ้น = class นั้นทายขาดน้อยลง",
            "- F1 สูงขึ้น = โดยรวม class นั้นดีขึ้นเมื่อบาลานซ์ทายเกินและทายขาด",
            "",
            "## สรุปสั้นราย Class",
            "",
        ]
    )
    for label in CLASSES:
        before = next(item for item in rows if item["scope"] == "overall" and item["class"] == label and item["mode"] == "before_raw")
        after = next(item for item in rows if item["scope"] == "overall" and item["class"] == label and item["mode"] == "after_tuned")
        direction = "ดีขึ้น" if after["f1"] > before["f1"] else "ลดลง" if after["f1"] < before["f1"] else "ใกล้เคียงเดิม"
        lines.extend(
            [
                f"### {label}",
                f"- F1: {float(before['f1']):.4f} -> {float(after['f1']):.4f} ({direction})",
                f"- Precision: {pct(float(before['precision']))} -> {pct(float(after['precision']))}",
                f"- Recall: {pct(float(before['recall']))} -> {pct(float(after['recall']))}",
                f"- Extra/FP: {before['fp_extra']} -> {after['fp_extra']}; Missing/FN: {before['fn_missing']} -> {after['fn_missing']}",
                "",
            ]
        )

    lines.extend(
        [
            "## ไฟล์ข้อมูลละเอียด",
            "",
            "- `per_class_summary.csv` มีทั้งภาพรวมและแยกตามวิดีโอ",
            "- `videos/<video_name>/per_detection_predictions.csv` มีข้อมูลรายเฟรม ราย bbox",
        ]
    )
    (base / "summary_by_class_th.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(base / "summary_by_class_th.md")
    print(base / "per_class_summary.csv")


if __name__ == "__main__":
    main()
