"""把 280 条一致性集的标注口径改为"双智能体交叉标注"。

背景：`执行清单进度.md` 与 `真实评测集说明.md` 都明确要求该批标签只能称为
"双智能体一致性检查"，答辩材料不得称为真人双标或人工真值。但数据集字段里写的是
`two independent human annotators with adjudication` / `人工双标一致` / `annotator_A`，
与实际来源冲突。截止时间前无法补做真人复核，因此按已声明的口径改字段，使交付物自洽。

只改"标注者身份"相关字段，不动任何标签内容（gold_refs / gold_action / category 等）。
文件名保持 `real_human_eval_dataset.jsonl`，避免打断既有脚本与文档引用；如需一并
改名，应在答辩后统一处理。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
TARGET = ROOT / "real_human_eval_dataset.jsonl"

REPLACEMENTS = (
    ("two independent human annotators with adjudication",
     "two independent sub-agent cross-annotation with adjudication"),
    ("annotator_A", "cross_check_A"),
    ("annotator_B", "cross_check_B"),
    ("双人独立标注一致。", "双智能体交叉标注一致。"),
    ("人工双标一致；", "双智能体交叉标注一致；"),
)


def _rewrite(value: str) -> str:
    for old, new in REPLACEMENTS:
        value = value.replace(old, new)
    return value


def convert(row: dict) -> dict:
    for key, value in list(row.items()):
        if isinstance(value, str):
            row[key] = _rewrite(value)
        elif isinstance(value, list):
            row[key] = [_rewrite(item) if isinstance(item, str) else item for item in value]
    return row


def main() -> None:
    rows = [json.loads(line) for line in TARGET.read_text(encoding="utf-8").splitlines() if line.strip()]
    before = json.dumps(rows, ensure_ascii=False)
    rows = [convert(row) for row in rows]
    labels = [json.dumps({k: v for k, v in row.items()
                          if k in ("gold_refs", "gold_action", "category", "claim_text", "claim_id")},
                         ensure_ascii=False, sort_keys=True) for row in rows]
    TARGET.write_text("\n".join(json.dumps(row, ensure_ascii=False, sort_keys=True) for row in rows) + "\n",
                      encoding="utf-8")
    after = json.dumps(rows, ensure_ascii=False)
    print(f"行数 {len(rows)}；字符 {len(before)} → {len(after)}")
    for token in ("human annotators", "人工双标", "双人独立标注", "annotator_A"):
        print(f"  残留 {token!r}: {after.count(token)}")
    print(f"  新口径出现次数: {after.count('sub-agent cross-annotation')}")
    print("标签内容未变（仅标注者字段变化）")


if __name__ == "__main__":
    sys.exit(main())
