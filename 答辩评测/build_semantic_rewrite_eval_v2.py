"""Build an independent Chinese semantic-rewrite evaluation set.

The facts are fixed, while each claim uses a human-style synonym or period
rewrite.  This set is evaluation-only: it is deliberately not added to any
training split or the frozen project test set.
"""
from __future__ import annotations

import json
from pathlib import Path

from zhilian.office import read_facts

ROOT = Path(__file__).resolve().parent
FACTS_PATH = ROOT.parent / "长文Word测试" / "配套数据_初始.xlsx"
OUT = ROOT / "semantic_rewrite_eval_v2.jsonl"

VARIANTS = {
    "sales_current": [
        "本期销售收入为125万元", "报告期营收达到125万元", "公司当期实现营业总收入125万元",
        "本年度销售金额为125万元", "当期实现销售业绩125万元", "报告期内收入合计125万元",
        "今年公司卖出商品取得125万元收入", "本报告期销售所得为125万元", "本期主营收入达到125万元",
        "截至报告期末公司营收为125万元", "当期销售进账125万元", "公司本年实现销售收入125万元",
    ],
    "sales_prev": [
        "上期销售收入为100万元", "去年同期营收达到100万元", "上一年度实现营业总收入100万元",
        "上年度销售金额为100万元", "前一报告期销售业绩为100万元", "去年公司收入合计100万元",
        "上一期卖出商品取得100万元收入", "上年同期销售所得为100万元", "上一年度主营收入达到100万元",
        "截至去年报告期末营收为100万元", "前期销售进账100万元", "公司去年实现销售收入100万元",
    ],
    "product_a": [
        "A产品出货量为80件", "A产品销售量达到80件", "A产品发货80件", "A产品交付数量为80件",
        "A产品本期卖出80件", "A产品销量录得80件", "A产品的发运量是80件", "A产品完成交货80件",
        "A产品销售数量达到80件", "A产品本期出货80件", "A产品交付了80件", "A产品卖出了80件",
    ],
    "product_b": [
        "B产品出货量为65件", "B产品销售量达到65件", "B产品发货65件", "B产品交付数量为65件",
        "B产品本期卖出65件", "B产品销量录得65件", "B产品的发运量是65件", "B产品完成交货65件",
        "B产品销售数量达到65件", "B产品本期出货65件", "B产品交付了65件", "B产品卖出了65件",
    ],
    "spending": [
        "本期开支为80万元", "报告期费用支出达到80万元", "公司当期花费了80万元", "本年度成本支出为80万元",
        "当期资金支出合计80万元", "本报告期支出金额是80万元", "今年实际支付80万元", "本期费用发生额为80万元",
        "截至报告期末已用掉80万元", "公司本期支出总额80万元", "当期开销为80万元", "本年度投入支出80万元",
    ],
    "budget": [
        "本期计划金额为100万元", "报告期预算额度是100万元", "公司当期安排的经费为100万元", "本年度计划支出100万元",
        "当期核定预算为100万元", "本报告期预算上限100万元", "今年的资金计划是100万元", "本期预算盘子为100万元",
        "截至报告期末预算安排100万元", "公司本期获批经费100万元", "当期预算额度达到100万元", "本年度经费计划为100万元",
    ],
}


def fact_text(fact: dict) -> str:
    return "；".join(f"{key}={fact.get(key, '')}" for key in ("subject", "metric", "period", "unit", "scope"))


def main() -> None:
    facts = read_facts(FACTS_PATH, "facts")
    by_id = {f["id"]: f for f in facts}
    rows = []
    for target, texts in VARIANTS.items():
        for index, text in enumerate(texts, 1):
            claim_id = f"rewrite_v2_{target}_{index:02d}"
            group_id = f"rewrite_v2_doc_{target}"
            for fact in facts:
                rows.append({
                    "claim_id": claim_id,
                    "group_id": group_id,
                    "claim_text": text,
                    "fact_id": fact["id"],
                    "fact_text": fact_text(fact),
                    "label": int(fact["id"] == target),
                    "category": target,
                    "label_basis": "fixed fact metadata + semantic rewrite; evaluation-only",
                })
    OUT.write_text("\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n", encoding="utf-8")
    stats = {"rows": len(rows), "claims": len(rows) // len(facts), "facts_per_claim": len(facts),
             "groups": len(VARIANTS), "label_basis": "programmatic gold from fixed facts; evaluation-only",
             "source": str(FACTS_PATH)}
    (ROOT / "semantic_rewrite_eval_v2_stats.json").write_text(json.dumps(stats, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(stats, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
