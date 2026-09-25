"""Run the real DeepSeek source-linking evaluation without storing the key."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from zhilian import llm


ROOT = Path(__file__).resolve().parent


def load(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as stream:
        return [json.loads(line) for line in stream if line.strip()]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", type=Path, default=ROOT / "eval_dataset.jsonl")
    parser.add_argument("--split", choices=("dev", "test", "all"), default="all")
    parser.add_argument("--output", type=Path, default=ROOT / "predictions_api.jsonl")
    parser.add_argument("--stats", type=Path, default=ROOT / "api_eval_stats.json")
    args = parser.parse_args()
    if not llm.config()["enabled"]:
        raise SystemExit("DEEPSEEK_API_KEY is not configured in this process")
    rows = load(args.dataset)
    if args.split != "all":
        rows = [row for row in rows if row["split"] == args.split]
    groups = {}
    for row in rows:
        groups.setdefault(row["group_id"], []).append(row)
    predictions = []
    calls = []
    for group_id, group in groups.items():
        claims = [{"id": row["claim_id"], "kind": row["kind"], "original": row["claim_text"],
                   "refs": [], "confirmed": False} for row in group]
        facts = group[0]["facts"]
        started = time.perf_counter()
        error = None
        suggestions = []
        try:
            suggestions = llm.suggest_links(claims, facts)
        except Exception as exc:
            error = str(exc)
        elapsed = round((time.perf_counter() - started) * 1000, 1)
        by_claim = {item.get("claim_id"): item for item in suggestions if isinstance(item, dict)}
        for row in group:
            item = by_claim.get(row["claim_id"], {})
            refs = item.get("refs", []) if isinstance(item.get("refs"), list) else []
            predictions.append({"claim_id": row["claim_id"], "action": "link" if refs else "abstain",
                                "refs": list(dict.fromkeys(refs))})
        calls.append({"group_id": group_id, "decision_count": len(group), "suggestion_count": len(suggestions),
                      "latency_ms": elapsed, "status": "error" if error else "ok", "error": error})
        print(f"{group_id}: {len(suggestions)} suggestions, {elapsed} ms" + (f"; {error}" if error else ""))
    with args.output.open("w", encoding="utf-8") as stream:
        for row in predictions:
            stream.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
    stats = {"provider": "DeepSeek", "model": llm.config()["model"], "split": args.split,
             "groups": len(groups), "decisions": len(rows), "calls": calls,
             "failed_calls": sum(call["status"] == "error" for call in calls),
             "api_key_written": False}
    args.stats.write_text(json.dumps(stats, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"wrote {args.output} and {args.stats}; key was not persisted")


if __name__ == "__main__":
    main()
