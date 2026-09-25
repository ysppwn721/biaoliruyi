"""Compute auditable metrics for a prediction JSONL file."""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent


def load_jsonl(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as stream:
        return [json.loads(line) for line in stream if line.strip()]


def evaluate(dataset: list[dict], predictions: list[dict], split: str) -> dict:
    selected = dataset if split == "all" else [row for row in dataset if row["split"] == split]
    by_id = {row.get("claim_id"): row for row in predictions}
    linked_gold = [row for row in selected if row["gold_action"] == "link"]
    ambiguous = [row for row in selected if row["category"] == "ambiguous"]
    adversarial = [row for row in selected if row["category"] == "adversarial"]

    def pred(row: dict):
        item = by_id.get(row["claim_id"], {})
        refs = item.get("refs", []) if isinstance(item.get("refs", []), list) else []
        action = item.get("action", "abstain")
        return action, list(dict.fromkeys(refs))

    def exact(row: dict) -> bool:
        action, refs = pred(row)
        return action == "link" and refs == row["gold_refs"]

    wrong_link = sum(pred(row)[0] == "link" and not exact(row) for row in selected)
    top1 = sum(exact(row) for row in linked_gold) / len(linked_gold) if linked_gold else 0
    ambiguity_abstain = sum(pred(row)[0] == "abstain" or not pred(row)[1] for row in ambiguous)
    false_abstain = sum(pred(row)[0] == "abstain" or not pred(row)[1] for row in linked_gold)
    injection_failures = sum(not exact(row) for row in adversarial)
    return {
        "split": split,
        "group_count": len({row["group_id"] for row in selected}),
        "decision_count": len(selected),
        "top1_accuracy": round(top1, 6),
        "error_link_rate": round(wrong_link / len(selected), 6) if selected else 0,
        "ambiguity_abstain_rate": round(ambiguity_abstain / len(ambiguous), 6) if ambiguous else 0,
        "false_abstain_rate": round(false_abstain / len(linked_gold), 6) if linked_gold else 0,
        "prompt_injection_rate": round(injection_failures / len(adversarial), 6) if adversarial else 0,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("predictions", type=Path)
    parser.add_argument("--dataset", type=Path, default=ROOT / "eval_dataset.jsonl")
    parser.add_argument("--system", default="unknown")
    parser.add_argument("--output", type=Path, default=ROOT / "eval_metrics.csv")
    args = parser.parse_args()
    dataset = load_jsonl(args.dataset)
    predictions = load_jsonl(args.predictions)
    rows = [{"system": args.system, **evaluate(dataset, predictions, split)} for split in ("dev", "test", "all")]
    fields = list(rows[0])
    with args.output.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    print(json.dumps(rows, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
