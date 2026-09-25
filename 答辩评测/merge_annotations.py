"""Merge two independent JSONL annotation files without hiding disagreements."""
from __future__ import annotations

import argparse
import json
from pathlib import Path


VALID_ACTIONS = {"link", "abstain"}
VALID_CATEGORIES = {"ordinary", "ambiguous", "adversarial"}


def load(path: Path) -> dict[str, dict]:
    rows = {}
    with path.open(encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, 1):
            if not line.strip():
                continue
            row = json.loads(line)
            claim_id = row.get("claim_id")
            if not claim_id or claim_id in rows:
                raise ValueError(f"{path}:{line_number} claim_id 缺失或重复")
            rows[claim_id] = row
    return rows


def decision(row: dict) -> tuple:
    action = row.get("gold_action")
    refs = tuple(sorted(dict.fromkeys(row.get("gold_refs") or [])))
    category = row.get("category")
    if action not in VALID_ACTIONS:
        raise ValueError(f"{row.get('claim_id')}: gold_action 必须是 link 或 abstain")
    if category not in VALID_CATEGORIES:
        raise ValueError(f"{row.get('claim_id')}: category 无效")
    if action == "abstain" and refs:
        raise ValueError(f"{row.get('claim_id')}: abstain 不应填写 gold_refs")
    if action == "link" and not refs:
        raise ValueError(f"{row.get('claim_id')}: link 必须填写 gold_refs")
    allowed = {fact.get("id") for fact in row.get("facts", [])}
    unknown = set(refs) - allowed
    if unknown:
        raise ValueError(f"{row.get('claim_id')}: gold_refs 包含未知事实 {sorted(unknown)}")
    return action, refs, category


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--a", type=Path, required=True, help="标注者 A 的 JSONL")
    parser.add_argument("--b", type=Path, required=True, help="标注者 B 的 JSONL")
    parser.add_argument("--output", type=Path, required=True, help="合并结果 JSONL")
    args = parser.parse_args()
    a, b = load(args.a), load(args.b)
    if set(a) != set(b):
        raise SystemExit(f"两份文件 claim_id 集合不同：A={len(a)}，B={len(b)}")

    merged = []
    counts = {"agreed": 0, "needs_adjudication": 0}
    for claim_id in a:
        left, right = a[claim_id], b[claim_id]
        if left.get("claim_text") != right.get("claim_text"):
            raise ValueError(f"{claim_id}: 两份文件的 claim_text 不一致")
        left_decision, right_decision = decision(left), decision(right)
        row = dict(left)
        row["annotators"] = [left.get("annotator_id", "annotator_A"),
                              right.get("annotator_id", "annotator_B")]
        if left_decision == right_decision:
            row["gold_action"], refs, row["category"] = left_decision
            # Keep a stable semantic order when both annotators selected the
            # same set. The extractor uses previous→current for growth and
            # source-table order for other multi-fact claims; list order is
            # representation, not a substantive disagreement.
            candidate_order = list(left.get("candidate_refs") or [])
            row["gold_refs"] = (candidate_order
                                 if set(candidate_order) == set(refs)
                                 else list(refs))
            row["adjudicated"] = True
            row["adjudication_note"] = "双人独立标注一致。A：{}；B：{}".format(
                left.get("annotation_note", ""), right.get("annotation_note", ""))
            counts["agreed"] += 1
        else:
            row["gold_action"] = "unresolved"
            row["gold_refs"] = []
            row["category"] = "unreviewed"
            row["adjudicated"] = False
            row["adjudication_status"] = "needs_adjudication"
            row["adjudication_note"] = json.dumps({
                "annotator_A": {"decision": left_decision, "note": left.get("annotation_note", "")},
                "annotator_B": {"decision": right_decision, "note": right.get("annotation_note", "")},
            }, ensure_ascii=False, sort_keys=True)
            counts["needs_adjudication"] += 1
        merged.append(row)

    with args.output.open("w", encoding="utf-8") as stream:
        for row in merged:
            stream.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
    print(json.dumps({"rows": len(merged), **counts, "output": str(args.output)},
                     ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
