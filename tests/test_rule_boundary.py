"""Natural-language boundary checks for the deterministic rule matcher.

The ordinary workflow fixtures intentionally use fact-table vocabulary.  This
set changes only the wording (营收/销售收入/费用/出货量等), so a high score
cannot be obtained by copying the metric strings from the spreadsheet.
"""
from pathlib import Path

from zhilian import engine, office


ROOT = Path(__file__).resolve().parents[1]
FACTS = office.read_facts(ROOT / '长文Word测试' / '配套数据_初始.xlsx', 'facts')
CASES = [
    ('本期销售额为125万元', ['sales_current']),
    ('本期销售额累计125万元', ['sales_current']),
    ('本报告期销售额为125万元', ['sales_current']),
    ('报告期内销售金额为125万元', ['sales_current']),
    ('本期销售收入为125万元', ['sales_current']),
    ('本期营业总收入达125万元', ['sales_current']),
    ('公司本期实现营收125万元', ['sales_current']),
    ('本期销售业绩为125万元', ['sales_current']),
    ('A产品销售量为80件', ['product_a']),
    ('A产品出货量达80件', ['product_a']),
    ('本期开支为80万元', ['spending']),
    ('本期费用为80万元', ['spending']),
    ('本期计划金额为100万元', ['budget']),
    ('本期预算为100万元', ['budget']),
    ('本期销售额超过120万元', ['sales_current']),
    ('报告期销售额突破120万元', ['sales_current']),
    ('A产品销量最高', ['product_a', 'product_b']),
    ('A产品销售量为各产品之最', ['product_a', 'product_b']),
]


def test_rule_boundary_uses_rewritten_language_set():
    picks = [[f['id'] for f in engine.best_facts(text, FACTS)] for text, _ in CASES]
    gold = [expected for _, expected in CASES]
    recall = sum(bool(pick) for pick in picks) / len(CASES)
    top1 = sum(pick == expected for pick, expected in zip(picks, gold)) / len(CASES)
    # These are baseline measurements, not a claim that rules understand
    # synonyms.  A future alias table or semantic layer may improve them.
    assert round(recall, 4) == 0.3889
    assert round(top1, 4) == 0.3333


def test_period_synonym_is_deterministically_narrowed():
    assert [f['id'] for f in engine.best_facts('本报告期销售额为125万元', FACTS)] == ['sales_current']
    assert [f['id'] for f in engine.best_facts('报告期销售额突破120万元', FACTS)] == ['sales_current']
