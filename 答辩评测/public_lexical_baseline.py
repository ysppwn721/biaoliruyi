"""Evaluate a dependency-free lexical fact matcher on public pairs."""
from __future__ import annotations

import json
import re
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent
INPUT = ROOT / "public_reranker_pairs.jsonl"
OUT = ROOT / "public_lexical_baseline_metrics.json"


def tokens(text: str) -> set[str]:
    return {token.lower() for token in re.findall(r"[A-Za-z]+|\d+(?:\.\d+)?|[\u4e00-\u9fff]", text or "")}


def score(claim: str, fact: str) -> float:
    c, f = tokens(claim), tokens(fact)
    if not c or not f:
        return 0.0
    return len(c & f) / max(1, len(c | f))


def evaluate(rows: list[dict], split: str) -> dict:
    groups = defaultdict(list)
    for row in rows:
        if row["split"] == split:
            groups[(row["source"], row["source_id"], row["claim_text"])].append(row)
    decisions = 0
    correct = 0
    wrong = 0
    abstain = 0
    for candidates in groups.values():
        positives = {row["fact_id"] for row in candidates if row["label"] == 1}
        ranked = sorted(candidates, key=lambda row: score(row["claim_text"], row["fact_text"]), reverse=True)
        if not positives:
            continue
        decisions += 1
        if not ranked or score(ranked[0]["claim_text"], ranked[0]["fact_text"]) == 0:
            abstain += 1
        elif ranked[0]["fact_id"] in positives:
            correct += 1
        else:
            wrong += 1
    return {"split": split, "decisions": decisions,
            "top1_accuracy": round(correct / decisions, 6) if decisions else 0,
            "wrong_link_rate": round(wrong / decisions, 6) if decisions else 0,
            "abstain_rate": round(abstain / decisions, 6) if decisions else 0}


def main() -> None:
    rows = [json.loads(line) for line in INPUT.open(encoding="utf-8") if line.strip()]
    result = {split: evaluate(rows, split) for split in ("train", "dev")}
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
