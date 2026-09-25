"""Measure the candidate budget before adding a local reranker."""
from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from zhilian.engine import best_facts


ROOT = Path(__file__).resolve().parent


def load(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as stream:
        return [json.loads(line) for line in stream if line.strip()]


def candidate_ids(row: dict) -> list[str]:
    return list(dict.fromkeys(f["id"] for f in best_facts(row["claim_text"], row["facts"])))


def analyze(rows: list[dict]) -> tuple[list[dict], dict]:
    details = []
    for row in rows:
        ids = candidate_ids(row)
        details.append({
            "claim_id": row["claim_id"],
            "group_id": row["group_id"],
            "split": row.get("split", "unknown"),
            "category": row.get("category", "unknown"),
            "kind": row.get("kind", "unknown"),
            "candidate_count": len(ids),
            "candidate_ids": ids,
            "pair_count": len(ids),
            "gold_count": len(row.get("gold_refs", [])),
        })
    counts = Counter(item["candidate_count"] for item in details)
    total = len(details)
    summary = {
        "decision_count": total,
        "zero_candidate_count": counts[0],
        "zero_candidate_rate": round(counts[0] / total, 6) if total else 0,
        "multi_candidate_count": sum(value for key, value in counts.items() if key > 1),
        "multi_candidate_rate": round(sum(value for key, value in counts.items() if key > 1) / total, 6) if total else 0,
        "one_candidate_count": counts[1],
        "candidate_count_distribution": dict(sorted(counts.items())),
        "total_pairs": sum(item["pair_count"] for item in details),
        "mean_pairs": round(sum(item["pair_count"] for item in details) / total, 3) if total else 0,
        "p95_pairs": sorted(item["pair_count"] for item in details)[max(0, int(total * .95) - 1)] if total else 0,
        "pairs_if_capped_at_5": sum(min(item["pair_count"], 5) for item in details),
        "single_candidate_link_rules_ceiling": round(counts[1] / total, 6) if total else 0,
    }
    return details, summary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", type=Path, default=ROOT / "eval_dataset.jsonl")
    parser.add_argument("--details", type=Path, default=ROOT / "candidate_budget_details.csv")
    parser.add_argument("--summary", type=Path, default=ROOT / "candidate_budget_summary.json")
    args = parser.parse_args()
    details, summary = analyze(load(args.dataset))
    with args.details.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(details[0]))
        writer.writeheader()
        writer.writerows(details)
    args.summary.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
