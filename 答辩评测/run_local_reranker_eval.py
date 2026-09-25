"""Evaluate the local reranker on single-fact candidate decisions."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from zhilian.engine import best_facts
from zhilian.reranker import choose, score_pairs, status


ROOT = Path(__file__).resolve().parent


def load(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as stream:
        return [json.loads(line) for line in stream if line.strip()]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", type=Path, default=ROOT / "eval_dataset.jsonl")
    parser.add_argument("--split", choices=("dev", "test", "all"), default="all")
    parser.add_argument("--output", type=Path, default=ROOT / "predictions_local_reranker.jsonl")
    args = parser.parse_args()
    if not status()["enabled"]:
        raise SystemExit("local reranker is not enabled; set ZHILIAN_LOCAL_RERANKER_PATH or ENABLED=1")
    rows = load(args.dataset)
    if args.split != "all":
        rows = [row for row in rows if row.get("split") == args.split]
    predictions = []
    timings = []
    for row in rows:
        candidates = best_facts(row["claim_text"], row["facts"])
        started = time.perf_counter()
        scores = score_pairs(row["claim_text"], candidates)
        choice = choose(scores)
        timings.append((time.perf_counter() - started) * 1000)
        # Group claims need multiple refs and stay on the deterministic path.
        if len(row.get("gold_refs", [])) > 1:
            choice = {"action": "abstain", "refs": []}
        predictions.append({"claim_id": row["claim_id"], "action": choice["action"],
                            "refs": choice["refs"]})
    with args.output.open("w", encoding="utf-8") as stream:
        for row in predictions:
            stream.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
    ordered = sorted(timings)
    p95 = ordered[max(0, int(len(ordered) * .95) - 1)] if ordered else 0
    print(json.dumps({"rows": len(rows), "status": status(), "avg_ms": round(sum(timings) / len(timings), 2),
                      "p95_ms": round(p95, 2), "output": str(args.output)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
