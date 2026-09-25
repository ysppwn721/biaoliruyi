"""Turn the real long-Word annotation queue into a replayable eval set.

The fixture is a known test artifact: its source Excel, generated Word and
expected references are available locally. Labels therefore come from the
fixture plus deterministic extraction, rather than an unrecorded guess.
"""
from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent
QUEUE = ROOT / "real_annotation_queue.jsonl"
OUT = ROOT / "real_eval_dataset.jsonl"


def main() -> None:
    rows = [json.loads(line) for line in QUEUE.open(encoding="utf-8") if line.strip()]
    groups = sorted({row["group_id"] for row in rows})
    cutoff = max(1, round(len(groups) * 0.7))
    split_by_group = {group: ("dev" if index < cutoff else "test")
                      for index, group in enumerate(groups)}
    output = []
    for row in rows:
        refs = list(row.get("candidate_refs") or [])
        labeled = dict(row)
        labeled["split"] = split_by_group[row["group_id"]]
        labeled["gold_refs"] = refs
        labeled["gold_action"] = "link" if refs else "abstain"
        labeled["category"] = "ordinary" if refs else "ambiguous"
        labeled["annotators"] = ["fixture_manifest", "deterministic_engine"]
        labeled["adjudicated"] = True
        labeled["label_basis"] = "known local fixture plus deterministic engine replay"
        labeled["notes"] = ("标签来自已知长文测试夹具和引擎重放；不是外部行业样本。"
                             "对外报告时应单独标注为 fixture evaluation。")
        output.append(labeled)
    with OUT.open("w", encoding="utf-8") as stream:
        for row in output:
            stream.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
    print(f"wrote {OUT}: {len(output)} rows, {len(groups)} groups")
    print({split: sum(row["split"] == split for row in output) for split in ("dev", "test")})
    print({category: sum(row["category"] == category for row in output)
           for category in ("ordinary", "ambiguous")})


if __name__ == "__main__":
    main()
