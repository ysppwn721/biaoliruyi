"""Summarize adjudicated human annotations and compare model predictions."""
from __future__ import annotations

import csv
import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def load(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as stream:
        return [json.loads(line) for line in stream if line.strip()]


def main() -> None:
    rows = load(ROOT / "real_human_eval_dataset.jsonl")
    summary = {
        "rows": len(rows),
        "groups": len({row["group_id"] for row in rows}),
        "dev": sum(row["split"] == "dev" for row in rows),
        "test": sum(row["split"] == "test" for row in rows),
        "actions": Counter(row["gold_action"] for row in rows),
        "categories": Counter(row["category"] for row in rows),
        "kinds": Counter(row["kind"] for row in rows),
        "all_adjudicated": all(row.get("adjudicated") for row in rows),
        "annotators": sorted({name for row in rows for name in row.get("annotators", [])}),
        "numeric_conflict_notes": sum("不一致" in (row.get("annotation_note", "") + row.get("adjudication_note", ""))
                                   for row in rows),
    }
    (ROOT / "human_annotation_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, default=dict), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2, default=dict))


if __name__ == "__main__":
    main()
