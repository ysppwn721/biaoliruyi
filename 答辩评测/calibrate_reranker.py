"""Sweep local reranker gates on the development split."""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from zhilian.engine import best_facts
from zhilian.reranker import score_pairs


ROOT = Path(__file__).resolve().parent


def load(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as stream:
        return [json.loads(line) for line in stream if line.strip()]


def score_rows(rows: list[dict]) -> list[dict]:
    scored = []
    for index, row in enumerate(rows, 1):
        candidates = best_facts(row["claim_text"], row["facts"])
        scores = score_pairs(row["claim_text"], candidates, batch_size=16)
        top = scores[0] if scores else {"fact_id": None, "raw_score": -999.0}
        second = scores[1]["raw_score"] if len(scores) > 1 else -999.0
        gold = set(row.get("gold_refs", []))
        scored.append({"claim_id": row["claim_id"], "category": row.get("category"),
                       "top_id": top["fact_id"], "top_score": top["raw_score"],
                       "margin": top["raw_score"] - second, "gold": gold,
                       "has_gold": bool(gold & {item["fact_id"] for item in scores})})
        if index % 20 == 0:
            print(f"scored {index}/{len(rows)}")
    return scored


def metrics(scored: list[dict], threshold: float, margin: float) -> dict:
    linked = [row for row in scored if row["category"] != "ambiguous"]
    ambiguous = [row for row in scored if row["category"] == "ambiguous"]
    accepted = [row for row in scored if row["top_score"] >= threshold and row["margin"] >= margin]
    correct = sum(row["top_id"] in row["gold"] for row in accepted if row["gold"])
    wrong = sum(row["top_id"] not in row["gold"] for row in accepted if row["gold"])
    accepted_linked = [row for row in accepted if row in linked]
    return {
        "threshold": threshold,
        "margin": margin,
        "accepted_rate": round(len(accepted) / len(scored), 6) if scored else 0,
        "linked_accept_rate": round(len(accepted_linked) / len(linked), 6) if linked else 0,
        "linked_top1": round(correct / len(accepted_linked), 6) if accepted_linked else 0,
        "linked_wrong_rate": round(wrong / len(accepted_linked), 6) if accepted_linked else 0,
        "ambiguity_abstain_rate": round(sum(row not in accepted for row in ambiguous) / len(ambiguous), 6) if ambiguous else None,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", type=Path, default=ROOT / "eval_dataset.jsonl")
    parser.add_argument("--output", type=Path, default=ROOT / "reranker_threshold_sweep.csv")
    args = parser.parse_args()
    rows = [row for row in load(args.dataset) if row.get("split") == "dev"]
    scored = score_rows(rows)
    results = [metrics(scored, threshold, margin)
               for threshold in (-3.5, -3.0, -2.5, -2.0, -1.8, -1.6, -1.4, -1.2)
               for margin in (0.0, 0.05, 0.10, 0.20, 0.30)]
    with args.output.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(results[0]))
        writer.writeheader()
        writer.writerows(results)
    best = sorted(results, key=lambda row: (-row["linked_top1"], row["linked_wrong_rate"], -row["linked_accept_rate"]))[:10]
    print(json.dumps({"rows": len(rows), "best": best}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
