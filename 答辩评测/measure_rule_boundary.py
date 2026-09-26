"""纯规则能力边界实测：同一批语义，换成人会写的说法。

背景：在项目夹具上"纯规则"与"分层路由"指标完全相同，容易得出"规则已经够了"的
结论。本脚本用**改写实验**把两者的分工测出来：

  规则 = engine.best_facts（词面/元数据匹配，硬门槛是 fact['metric'] in text）
  语义 = 本地 BGE reranker 对**整张事实表**打分后取 Top-1（不依赖词面命中）

改写只动措辞，不动语义，gold 不变。任何一条改写都是同一份事实表的正确引用。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parent))

from zhilian import engine, office, reranker  # noqa: E402

FACTS = office.read_facts(str(ROOT.parent / "长文Word测试" / "配套数据_初始.xlsx"), "facts")

# (改写文本, gold refs, 改写手法)
CASES = [
    ("本期销售额为125万元", ["sales_current"], "原句（词面完全一致）"),
    ("本期销售额累计125万元", ["sales_current"], "加动词「累计」"),
    ("本报告期销售额为125万元", ["sales_current"], "期间换说法：本期→本报告期"),
    ("报告期内销售金额为125万元", ["sales_current"], "指标换说法：销售额→销售金额"),
    ("本期销售收入为125万元", ["sales_current"], "指标换说法：销售额→销售收入"),
    ("本期营业总收入达125万元", ["sales_current"], "指标换说法：销售额→营业总收入"),
    ("公司本期实现营收125万元", ["sales_current"], "指标换说法：销售额→营收"),
    ("本期销售业绩为125万元", ["sales_current"], "指标换说法：销售额→销售业绩"),
    ("A产品销售量为80件", ["product_a"], "指标换说法：销量→销售量"),
    ("A产品出货量达80件", ["product_a"], "指标换说法：销量→出货量"),
    ("本期开支为80万元", ["spending"], "指标换说法：支出→开支"),
    ("本期费用为80万元", ["spending"], "指标换说法：支出→费用"),
    ("本期计划金额为100万元", ["budget"], "指标换说法：预算→计划"),
    ("本期预算为100万元", ["budget"], "原句（词面完全一致）"),
    ("本期销售额超过120万元", ["sales_current"], "原句（阈值）"),
    ("报告期销售额突破120万元", ["sales_current"], "阈值换说法：超过→突破"),
    ("A产品销量最高", ["product_a", "product_b"], "原句（排名，需两条）"),
    ("A产品销售量为各产品之最", ["product_a", "product_b"], "排名换说法"),
]


def rule_pick(text: str) -> list[str]:
    return [fact["id"] for fact in engine.best_facts(text, FACTS)]


def semantic_pick(text: str) -> list[dict]:
    scores = reranker.score_pairs(text, FACTS, batch_size=8)
    return scores


def main() -> None:
    rows = []
    for text, gold, how in CASES:
        picked = rule_pick(text)
        scores = semantic_pick(text)
        top = scores[0]
        rows.append({
            "text": text, "gold": gold, "how": how,
            "rule_refs": picked,
            "rule_recall": bool(picked),
            "rule_top1": picked == gold,
            "semantic_top1_id": top["fact_id"],
            "semantic_top1_raw": round(top["raw_score"], 3),
            "semantic_top1": top["fact_id"] in gold,
            "gold_rank": next((i + 1 for i, s in enumerate(scores) if s["fact_id"] in gold), None),
        })
        flag = "规则✓" if rows[-1]["rule_top1"] else ("规则认不出" if not picked else "规则选错")
        print(f"{flag:<10} 语义{'✓' if rows[-1]['semantic_top1'] else '✗'} "
              f"| {text:<24} 规则={picked or '[]'} 语义Top1={top['fact_id']}({top['raw_score']:.2f}) gold={gold}")

    total = len(rows)
    rule_recall = sum(r["rule_recall"] for r in rows) / total
    rule_top1 = sum(r["rule_top1"] for r in rows) / total
    sem_top1 = sum(r["semantic_top1"] for r in rows) / total
    sem_rank = sum(1 for r in rows if r["gold_rank"] and r["gold_rank"] <= 2) / total
    summary = {
        "cases": total,
        "rule_recall": round(rule_recall, 4),
        "rule_top1": round(rule_top1, 4),
        "semantic_top1": round(sem_top1, 4),
        "semantic_top2_recall": round(sem_rank, 4),
        "note": "改写只改措辞不改语义；规则硬门槛为 fact['metric'] in claim_text。",
    }
    print()
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    (ROOT / "rule_boundary_report.json").write_text(
        json.dumps({"summary": summary, "rows": rows}, ensure_ascii=False, indent=2), encoding="utf-8")
    (ROOT / "rule_boundary_pairs.jsonl").write_text(
        "\n".join(json.dumps(r, ensure_ascii=False, sort_keys=True) for r in rows) + "\n", encoding="utf-8")
    print("wrote rule_boundary_report.json / rule_boundary_pairs.jsonl")


if __name__ == "__main__":
    main()
