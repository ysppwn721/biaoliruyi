"""Create a leakage-safe Chinese fine-tuning split from the adjudicated pairs.

The source file contains the current development groups and a frozen test
partition. Only the former is divided into train/dev. Rows in the source
test partition are copied unchanged and are never used for training.
"""
from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path


def load(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.open(encoding="utf-8") if line.strip()]


def write(path: Path, rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8") as stream:
        for row in rows:
            stream.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, default=Path(__file__).with_name("reranker_training_pairs.jsonl"))
    parser.add_argument("--output", type=Path, default=Path(__file__).with_name("cn_finetune"))
    parser.add_argument("--dev-groups", type=int, default=4)
    args = parser.parse_args()

    rows = load(args.input)
    source_dev = [row for row in rows if row.get("split") == "dev"]
    frozen_test = [row for row in rows if row.get("split") == "test"]
    groups = sorted({row["group_id"] for row in source_dev})
    if len(groups) <= args.dev_groups:
        raise ValueError("开发组数量不足，不能划分 train/dev")

    # Stable sorted group holdout. The original source test groups remain
    # untouched and are copied to final_test.jsonl.
    dev_groups = set(groups[-args.dev_groups:])
    train = [row for row in source_dev if row["group_id"] not in dev_groups]
    dev = [row for row in source_dev if row["group_id"] in dev_groups]

    train_groups = {row["group_id"] for row in train}
    dev_group_set = {row["group_id"] for row in dev}
    test_groups = {row["group_id"] for row in frozen_test}
    if train_groups & dev_group_set or train_groups & test_groups or dev_group_set & test_groups:
        raise AssertionError("文档组泄漏")
    args.output.mkdir(parents=True, exist_ok=True)
    write(args.output / "train.jsonl", train)
    write(args.output / "dev.jsonl", dev)
    write(args.output / "final_test.jsonl", frozen_test)
    manifest = {
        "source": str(args.input),
        "train_rows": len(train), "dev_rows": len(dev), "final_test_rows": len(frozen_test),
        "train_groups": sorted(train_groups), "dev_groups": sorted(dev_group_set),
        "final_test_groups": sorted(test_groups),
        "note": "final_test copied from the original test partition and must remain frozen",
    }
    (args.output / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
