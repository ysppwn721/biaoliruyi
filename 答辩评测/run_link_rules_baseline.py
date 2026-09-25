"""Evaluate the persisted link_rules behavior as an online warm-start replay.

The dataset labels are used only after each decision to simulate a prior human
confirmation. This is deliberately a replay experiment, not an independent
generalization score: it answers whether remembered links can be reused safely
while ambiguous claims still abstain.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from run_rule_baseline import predict as rule_predict

ROOT = Path(__file__).resolve().parent


def load(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as stream:
        return [json.loads(line) for line in stream if line.strip()]


def key(claim: dict, fact: dict) -> str | None:
    values = [claim.get("kind"), fact.get("subject"), fact.get("metric"), fact.get("period")]
    return "|".join(values) if all(isinstance(value, str) and value for value in values) else None


def remembered_refs(row: dict, memory: dict[str, str]) -> list[str]:
    refs = []
    for fact in row.get("facts", []):
        remembered = memory.get(key(row, fact))
        if remembered and remembered not in refs:
            refs.append(remembered)
    return refs


def replay(rows: list[dict]) -> list[dict]:
    memory: dict[str, str] = {}
    current_group = None
    predictions = []
    for row in rows:
        # link_rules live inside one project/document group; never leak a
        # remembered fact ID into another group's fact table.
        if row.get("group_id") != current_group:
            memory = {}
            current_group = row.get("group_id")
        # Match the production behavior: link_rules annotate/prioritize an
        # existing deterministic option; they never replace it or bypass the
        # ambiguity/manual-confirmation gate.
        prediction = rule_predict(row)
        remembered = remembered_refs(row, memory)
        prediction["remembered"] = bool(
            remembered and prediction.get("action") == "link"
            and remembered == prediction.get("refs", [])
        )
        prediction["source"] = "link_rules" if prediction["remembered"] else "rule_fallback"
        predictions.append(prediction)

        # Online replay: only a confirmed human decision creates memory for
        # later claims in the same document group.
        if row.get("gold_action") == "link":
            by_id = {fact["id"]: fact for fact in row.get("facts", [])}
            for fact_id in row.get("gold_refs", []):
                fact = by_id.get(fact_id)
                if fact:
                    memory[key(row, fact)] = fact_id
    return predictions


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", type=Path, default=ROOT / "eval_dataset.jsonl")
    parser.add_argument("--output", type=Path, default=ROOT / "predictions_link_rules_replay.jsonl")
    args = parser.parse_args()
    rows = load(args.dataset)
    predictions = replay(rows)
    with args.output.open("w", encoding="utf-8") as stream:
        for row in predictions:
            stream.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
    remembered = sum(row.get("source") == "link_rules" for row in predictions)
    print(json.dumps({"rows": len(rows), "remembered_predictions": remembered,
                      "output": str(args.output)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
