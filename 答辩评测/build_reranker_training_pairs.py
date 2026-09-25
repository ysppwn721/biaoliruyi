"""Create auditable reranker pair candidates from adjudicated labels.

This only prepares pairs; it does not train. Values are intentionally omitted
from fact text so the model learns metadata matching rather than memorizing
numeric answers.
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATASET = ROOT / "real_human_eval_dataset.jsonl"
OUT = ROOT / "reranker_training_pairs.jsonl"


def fact_text(fact: dict) -> str:
    return "；".join(f"{key}={fact.get(key, '')}" for key in
                     ("subject", "metric", "period", "unit", "scope"))


def hard_negative(gold: dict, candidate: dict) -> bool:
    if candidate["id"] == gold["id"]:
        return False
    # Prefer close metadata negatives: same metric, same subject, or same
    # period. They are more useful than unrelated facts.
    return any(candidate.get(key) == gold.get(key) for key in ("metric", "subject", "period"))


def main() -> None:
    rows = [json.loads(line) for line in DATASET.open(encoding="utf-8") if line.strip()]
    pairs = []
    for row in rows:
        gold_ids = set(row.get("gold_refs") or [])
        facts = row.get("facts", [])
        gold_facts = [fact for fact in facts if fact["id"] in gold_ids]
        negatives = [fact for fact in facts if fact["id"] not in gold_ids]
        for fact in gold_facts:
            pairs.append({"claim_id": row["claim_id"], "group_id": row["group_id"],
                          "split": row["split"], "claim_text": row["claim_text"],
                          "fact_id": fact["id"], "fact_text": fact_text(fact),
                          "label": 1, "negative_type": "positive"})
        for gold in gold_facts:
            for fact in negatives:
                if hard_negative(gold, fact):
                    pairs.append({"claim_id": row["claim_id"], "group_id": row["group_id"],
                                  "split": row["split"], "claim_text": row["claim_text"],
                                  "fact_id": fact["id"], "fact_text": fact_text(fact),
                                  "label": 0, "negative_type": "hard_negative"})
    with OUT.open("w", encoding="utf-8") as stream:
        for pair in pairs:
            stream.write(json.dumps(pair, ensure_ascii=False, sort_keys=True) + "\n")
    print(json.dumps({"pairs": len(pairs), "positive": sum(p["label"] == 1 for p in pairs),
                      "hard_negative": sum(p["label"] == 0 for p in pairs),
                      "groups": len({p["group_id"] for p in pairs}),
                      "dev_pairs": sum(p["split"] == "dev" for p in pairs),
                      "test_pairs": sum(p["split"] == "test" for p in pairs),
                      "output": str(OUT)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
