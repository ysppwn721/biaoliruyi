"""Audit public reranker pairs before any model training."""
from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent
INPUT = ROOT / "public_reranker_pairs.jsonl"
OUT = ROOT / "public_pairs_audit.json"


def main() -> None:
    rows = []
    errors = []
    for line_no, line in enumerate(INPUT.open(encoding="utf-8"), 1):
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            errors.append(f"line {line_no}: invalid JSON: {exc}")
            continue
        required = {"source", "source_id", "group_id", "split", "claim_text", "fact_id", "fact_text", "label"}
        missing = sorted(required - set(row))
        if missing:
            errors.append(f"line {line_no}: missing {missing}")
        if row.get("label") not in {0, 1}:
            errors.append(f"line {line_no}: invalid label")
        if row.get("label") == 1 and row.get("negative_type") == "hard_negative":
            errors.append(f"line {line_no}: positive marked hard_negative")
        rows.append(row)

    pair_keys = [(row.get("source"), row.get("source_id"), row.get("claim_text"), row.get("fact_id"), row.get("label")) for row in rows]
    duplicate_count = len(pair_keys) - len(set(pair_keys))
    groups = defaultdict(set)
    for row in rows:
        groups[row.get("group_id")].add(row.get("split"))
    split_leakage = {group: sorted(splits) for group, splits in groups.items() if len(splits) > 1}
    value_field_count = sum("value=" in row.get("fact_text", "") or "value" in row for row in rows)
    numeric_metadata_count = sum(bool(re.search(r"(?<![A-Za-z])\d+(?:\.\d+)?%?", row.get("fact_text", ""))) for row in rows)
    claims_by_group = defaultdict(set)
    for row in rows:
        claims_by_group[(row.get("source"), row.get("group_id"))].add(row.get("claim_text"))
    repeated_claim_groups = sum(len(values) < 2 for values in claims_by_group.values())
    summary = {
        "rows": len(rows),
        "errors": errors[:50],
        "error_count": len(errors),
        "sources": Counter(row.get("source") for row in rows),
        "splits": Counter(row.get("split") for row in rows),
        "labels": Counter(row.get("label") for row in rows),
        "negative_types": Counter(row.get("negative_type", "positive") for row in rows),
        "unique_groups": len(groups),
        "duplicate_pair_count": duplicate_count,
        "split_leakage_group_count": len(split_leakage),
        "split_leakage_examples": dict(list(split_leakage.items())[:20]),
        "numeric_metadata_count": numeric_metadata_count,
        "value_field_or_value_label_count": value_field_count,
        "single_claim_group_count": repeated_claim_groups,
        "ready_for_training": not errors and duplicate_count == 0 and not split_leakage and value_field_count == 0,
        "recommendation": "抽样复核后再训练；当前数据是弱标注候选，不能直接当最终测试集。",
    }
    OUT.write_text(json.dumps(summary, ensure_ascii=False, indent=2, default=dict), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2, default=dict))


if __name__ == "__main__":
    main()
