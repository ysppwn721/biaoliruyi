"""Build the adjudicated human-label evaluation set from annotation batches."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
INPUTS = [ROOT / "real_annotation_batch_01_merged.jsonl",
          ROOT / "real_annotation_remaining_merged.jsonl"]
OUT = ROOT / "real_human_eval_dataset.jsonl"


def load(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as stream:
        return [json.loads(line) for line in stream if line.strip()]


def main() -> None:
    rows = [row for path in INPUTS for row in load(path)]
    by_id = {row["claim_id"]: row for row in rows}
    if len(by_id) != len(rows):
        raise SystemExit("duplicate claim_id across annotation batches")
    groups = sorted({row["group_id"] for row in rows})
    cutoff = max(1, round(len(groups) * 0.7))
    split = {group: ("dev" if index < cutoff else "test") for index, group in enumerate(groups)}
    output = []
    for row in sorted(rows, key=lambda item: item["claim_id"]):
        if not row.get("adjudicated"):
            raise SystemExit(f"not adjudicated: {row['claim_id']}")
        item = dict(row)
        item["split"] = split[row["group_id"]]
        item["label_basis"] = "two independent human annotators with adjudication"
        item["notes"] = ("人工双标一致；数据来自本地长文测试夹具，不代表外部行业泛化。"
                          "数值是否一致仍由确定性引擎单独判断。")
        output.append(item)
    with OUT.open("w", encoding="utf-8") as stream:
        for item in output:
            stream.write(json.dumps(item, ensure_ascii=False, sort_keys=True) + "\n")
    print(json.dumps({"rows": len(output), "groups": len(groups),
                      "dev": sum(item["split"] == "dev" for item in output),
                      "test": sum(item["split"] == "test" for item in output),
                      "output": str(OUT)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
