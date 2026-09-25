"""Create a small stratified manual audit sample before training."""
from __future__ import annotations

import csv
import json
import random
from pathlib import Path

ROOT = Path(__file__).resolve().parent
INPUT = ROOT / "public_reranker_pairs.jsonl"
OUT = ROOT / "public_pairs_sample_for_review.csv"


def main() -> None:
    random.seed(20260925)
    buckets = {}
    for line in INPUT.open(encoding="utf-8"):
        row = json.loads(line)
        buckets.setdefault((row["source"], row["split"], row["label"]), []).append(row)
    sample = []
    for bucket, rows in buckets.items():
        take = min(25, len(rows))
        sample.extend(random.sample(rows, take))
    fields = ["source", "split", "source_id", "group_id", "claim_text", "fact_id", "fact_text",
              "label", "manual_label", "manual_note"]
    with OUT.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for row in sample:
            writer.writerow({key: row.get(key, "") for key in fields})
    print(json.dumps({"rows": len(sample), "output": str(OUT),
                      "buckets": {str(key): min(25, len(value)) for key, value in buckets.items()}},
                     ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
