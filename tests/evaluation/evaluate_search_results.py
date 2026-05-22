from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path

from tests.evaluation.metrics import read_records, write_json


def precision_at_k(relevant_ids: set[str], returned_ids: list[str], k: int) -> float:
    if k <= 0:
        return 0.0
    top = returned_ids[:k]
    if not top:
        return 0.0
    return sum(item in relevant_ids for item in top) / len(top)


def recall_at_k(relevant_ids: set[str], returned_ids: list[str], k: int) -> float:
    if not relevant_ids:
        return 0.0
    top = returned_ids[:k]
    return sum(item in relevant_ids for item in top) / len(relevant_ids)


def average_precision(relevant_ids: set[str], returned_ids: list[str]) -> float:
    if not relevant_ids:
        return 0.0
    hits = 0
    total = 0.0
    for idx, item in enumerate(returned_ids, 1):
        if item in relevant_ids:
            hits += 1
            total += hits / idx
    return total / len(relevant_ids)


def evaluate(args: argparse.Namespace) -> dict:
    queries = read_records(args.queries)
    results = read_records(args.results)
    by_query = defaultdict(list)
    for row in results:
        query_id = str(row.get("query_id"))
        result_id = str(row.get("result_id") or row.get("track_id") or row.get("detection_id"))
        if query_id and result_id:
            by_query[query_id].append(result_id)

    query_reports = []
    for query in queries:
        query_id = str(query.get("query_id") or query.get("id"))
        relevant_raw = query.get("relevant_ids") or query.get("expected_ids") or ""
        if isinstance(relevant_raw, str):
            relevant_ids = {v.strip() for v in relevant_raw.replace(";", ",").split(",") if v.strip()}
        else:
            relevant_ids = {str(v) for v in relevant_raw}
        returned_ids = by_query.get(query_id, [])
        query_reports.append({
            "query_id": query_id,
            "criteria": query.get("criteria") or query.get("description") or "",
            "relevant_count": len(relevant_ids),
            "returned_count": len(returned_ids),
            "precision_at_5": precision_at_k(relevant_ids, returned_ids, 5),
            "precision_at_10": precision_at_k(relevant_ids, returned_ids, 10),
            "recall_at_10": recall_at_k(relevant_ids, returned_ids, 10),
            "average_precision": average_precision(relevant_ids, returned_ids),
            "returned_ids": returned_ids,
        })

    report = {
        "task": "search_accuracy",
        "queries": args.queries,
        "results": args.results,
        "query_count": len(query_reports),
        "mean_precision_at_5": sum(q["precision_at_5"] for q in query_reports) / len(query_reports) if query_reports else 0.0,
        "mean_precision_at_10": sum(q["precision_at_10"] for q in query_reports) / len(query_reports) if query_reports else 0.0,
        "mean_recall_at_10": sum(q["recall_at_10"] for q in query_reports) / len(query_reports) if query_reports else 0.0,
        "map": sum(q["average_precision"] for q in query_reports) / len(query_reports) if query_reports else 0.0,
        "query_reports": query_reports,
    }
    write_json(args.output, report)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate search results against expected relevant IDs.")
    parser.add_argument("--queries", required=True, help="CSV/JSON/JSONL with query_id,relevant_ids.")
    parser.add_argument("--results", required=True, help="CSV/JSON/JSONL with query_id,result_id in returned order.")
    parser.add_argument("--output", default="my-thesis-report/qa/search-eval.json")
    args = parser.parse_args()
    report = evaluate(args)
    print(json.dumps({
        "query_count": report["query_count"],
        "mean_precision_at_5": report["mean_precision_at_5"],
        "mean_precision_at_10": report["mean_precision_at_10"],
        "mean_recall_at_10": report["mean_recall_at_10"],
        "map": report["map"],
        "output": args.output,
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
