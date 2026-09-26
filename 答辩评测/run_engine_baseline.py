"""产品真实路径基线：直接运行引擎，而不是复刻一套启发式规则。

背景：`run_rule_baseline.py` 为了对合成数据集做快速回归，用固定指标名
（销售额/销量/支出/预算）复刻了一套启发式候选逻辑。那套逻辑在真实长文夹具上
会把全部 96 条阈值论断都判成"支出 vs 预算"，其中一半的真实来源其实是销售额，
并且顺序也与标签相反。因此它得到的 65.71% 是**脚本自身的分数**，不能当作
产品确定性层的准确率对外汇报。

本脚本走产品实际调用链：
    office.read_facts -> office.read_document -> engine.extract_claims
并把提取到的 refs 与数据集标签逐条比对，未匹配的条目单独计数，绝不静默计 0。
"""
from __future__ import annotations

import argparse
import collections
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parent))

from zhilian import engine, office  # noqa: E402


def load_jsonl(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as stream:
        return [json.loads(line) for line in stream if line.strip()]


def extract(document: Path, facts_path: Path) -> list[tuple[tuple, str, list]]:
    facts = office.read_facts(str(facts_path), "facts")
    blocks, charts, warnings = office.read_document(str(document), "doc", facts)
    index = engine.build_index(facts)
    claims = []
    for block in blocks:
        location = tuple(json.loads(block["location"]))
        for claim in engine.extract_claims(block, facts, index=index):
            claims.append((location, claim["original"], list(claim["refs"])))
    for chart in charts:
        claims.append((tuple(json.loads(chart["location"])), chart["original"], list(chart["refs"])))
    return claims, facts, warnings


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", type=Path, default=ROOT / "real_human_eval_dataset.jsonl")
    parser.add_argument("--document", type=Path, default=ROOT.parent / "长文Word测试" / "长文测试_原始报告.docx")
    parser.add_argument("--facts", type=Path, default=ROOT.parent / "长文Word测试" / "配套数据_初始.xlsx")
    parser.add_argument("--output", type=Path, default=ROOT / "predictions_human_engine.jsonl")
    args = parser.parse_args()

    rows = load_jsonl(args.dataset)
    claims, facts, warnings = extract(args.document, args.facts)
    by_key, by_text = {}, collections.defaultdict(list)
    for location, text, refs in claims:
        by_key.setdefault((location, text), []).append(refs)
        by_text[text].append(refs)

    stats = collections.Counter()
    per_kind = collections.defaultdict(lambda: collections.Counter())
    with args.output.open("w", encoding="utf-8") as stream:
        for row in rows:
            kind = row["kind"]
            per_kind[kind]["total"] += 1
            exact_key = by_key.get((tuple(row["source_location"]), row["claim_text"]))
            refs = (exact_key or by_text.get(row["claim_text"]) or [[]])[0]
            if not exact_key and not by_text.get(row["claim_text"]):
                # 未匹配必须显式统计：静默 abstain 会把提取缺失伪装成低准确率。
                stats["unmatched"] += 1
                per_kind[kind]["unmatched"] += 1
            else:
                stats["matched"] += 1
            action = "link" if refs else "abstain"
            if action == "link" and refs == list(row["gold_refs"]):
                stats["top1"] += 1
                per_kind[kind]["top1"] += 1
            stream.write(json.dumps({"claim_id": row["claim_id"], "action": action, "refs": refs},
                                    ensure_ascii=False, sort_keys=True) + "\n")

    total = len(rows)
    print(f"事实 {len(facts)} 条，提取论断 {len(claims)} 条，读取警告 {len(warnings)} 条")
    print(f"数据集 {total} 条：匹配 {stats['matched']}，未匹配 {stats['unmatched']}，Top-1 {stats['top1']} "
          f"（{stats['top1'] / total:.4f}）")
    for kind in sorted(per_kind):
        row = per_kind[kind]
        print(f"  {kind:<10} {row['top1']:>3}/{row['total']:<3} {row['top1'] / row['total']:.4f}"
              f"   未匹配 {row['unmatched']}")
    print(f"wrote {args.output}")


if __name__ == "__main__":
    main()
