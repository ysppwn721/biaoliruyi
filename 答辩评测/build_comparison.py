"""Build a single comparison table and local-to-API tradeoff table."""
from __future__ import annotations

import csv
from pathlib import Path

ROOT = Path(__file__).resolve().parent
FIELDS = ["dataset", "system", "split", "group_count", "decision_count",
          "top1_accuracy", "error_link_rate", "ambiguity_abstain_rate",
          "false_abstain_rate", "prompt_injection_rate"]


def rows(path: Path, dataset: str) -> list[dict]:
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return [{"dataset": dataset, **row} for row in csv.DictReader(stream)]


def main() -> None:
    sources = [
        ("seed", "rule", ROOT / "eval_metrics.csv"),
        ("seed", "link-rules-assisted-replay", ROOT / "link_rules_replay_metrics.csv"),
        ("seed", "local-reranker-calibrated", ROOT / "local_reranker_metrics.csv"),
        ("seed", "deepseek-flash", ROOT / "api_eval_metrics.csv"),
        ("long-word-fixture", "rule", ROOT / "real_eval_metrics.csv"),
        ("long-word-fixture", "link-rules-assisted-replay", ROOT / "link_rules_replay_real_metrics.csv"),
        ("long-word-fixture", "deepseek-flash", ROOT / "api_real_eval_metrics.csv"),
    ]
    combined = []
    for dataset, expected_system, path in sources:
        for row in rows(path, dataset):
            row["system"] = expected_system
            combined.append(row)
    with (ROOT / "system_comparison.csv").open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(combined)

    sweep = []
    with (ROOT / "reranker_threshold_sweep.csv").open(encoding="utf-8-sig", newline="") as stream:
        for row in csv.DictReader(stream):
            accepted = float(row["accepted_rate"])
            sweep.append({
                "threshold": row["threshold"], "margin": row["margin"],
                "dev_decisions": 120,
                "local_auto_accept_rate": row["accepted_rate"],
                "estimated_api_fallback_calls": round((1 - accepted) * 120),
                "linked_auto_top1": row["linked_top1"],
                "linked_auto_wrong_rate": row["linked_wrong_rate"],
                "ambiguity_abstain_rate": row["ambiguity_abstain_rate"],
            })
    with (ROOT / "reranker_api_tradeoff.csv").open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(sweep[0]))
        writer.writeheader()
        writer.writerows(sweep)
    print(f"wrote {len(combined)} comparison rows and {len(sweep)} tradeoff rows")


if __name__ == "__main__":
    main()
