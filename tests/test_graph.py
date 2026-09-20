"""派生事实依赖图：表达式、拓扑序、环检测、级联重算与影响半径。"""
import pytest

from zhilian.graph import (OPERATIONS, DerivationError, Derivations, compute, eval_expr,
                           impact, parse_expr)


def fact(fid, metric, subject, period, value, unit='万元', scope='演示业务'):
    return {'id': fid, 'subject': subject, 'metric': metric, 'period': period,
            'value': value, 'unit': unit, 'scope': scope, 'sheet': 'Sheet1', 'cell': 'B2'}


@pytest.fixture
def base():
    """每个测试独立拿一份基础事实，避免相互污染。"""
    return [
        fact('sales_prev', '销售额', '总计', '上期', 100),
        fact('sales_cur', '销售额', '总计', '本期', 125),
        fact('sales_cur_2', '销售额', '总计', '本期', 130),
        fact('cost_prev', '成本', '总计', '上期', 40),
        fact('cost_cur', '成本', '总计', '本期', 50),
        fact('a_qty', '销量', 'A产品', '本期', 80, '件'),
        fact('b_qty', '销量', 'B产品', '本期', 60, '件'),
        fact('a_qty_prev', '销量', 'A产品', '上期', 70, '件'),
        fact('b_qty_prev', '销量', 'B产品', '上期', 40, '件'),
        # 与 a_qty 同主体、同指标、同期间，仅数值不同：用于构造"两个本期"这类非法组合
        fact('a_qty_other', '销量', 'A产品', '本期', 90, '件'),
    ]


# ---- 表达式解析 ----------------------------------------------------------

def test_parse_expr_accepts_whitelisted_operations():
    assert parse_expr('sum(a_qty, b_qty)') == {'op': 'sum', 'inputs': ['a_qty', 'b_qty']}
    assert parse_expr(' diff(sales_cur, cost_cur) ') == {'op': 'diff', 'inputs': ['sales_cur', 'cost_cur']}
    assert parse_expr('growth(sales_cur, sales_prev)')['op'] == 'growth'


@pytest.mark.parametrize('bad', [
    '',
    'sum(a)',
    'exec(sales_cur)',
    '__import__("os")',
    'diff(sales_cur)',
    'diff(sales_cur, sales_cur)',
    'sum(a_qty, "x")',
    'sum(a_qty, b_qty',
    'sum(a_qty, )',
])
def test_parse_expr_rejects_unsupported_forms(bad):
    with pytest.raises(DerivationError):
        parse_expr(bad)


def test_sum_accepts_two_or_more_operands():
    assert parse_expr('sum(a, b, c)')['inputs'] == ['a', 'b', 'c']
    assert OPERATIONS['sum']['note']


# ---- 数值与单位 ----------------------------------------------------------

def test_operations_compute_with_decimal_precision(base):
    d = Derivations([
        {'id': 'profit', 'expr': 'diff(sales_cur, cost_cur)'},
        {'id': 'total_qty', 'expr': 'sum(a_qty, b_qty)', 'unit': '件'},
        {'id': 'sales_growth', 'expr': 'growth(sales_cur, sales_prev)'},
        {'id': 'cost_margin', 'expr': 'ratio(cost_cur, sales_cur)', 'label': '成本占比'},
    ])
    out = compute(base, d)
    assert str(out['values']['profit']) == '75.00'
    assert str(out['values']['total_qty']) == '140.00'
    assert str(out['values']['sales_growth']) == '25.00'
    assert str(out['values']['cost_margin']) == '40.00'
    assert out['errors'] == {}
    assert '125 − 50' in out['details']['profit']
    # 派生事实带 derived 标记，可与基础事实区分
    derived = {f['id']: f for f in out['facts'] if f.get('derived')}
    assert derived['profit']['inputs'] == ['sales_cur', 'cost_cur']
    assert derived['cost_margin']['metric'] == '成本占比'


def test_unit_conversion_across_scales(base):
    facts = [fact('sales_cur', '销售额', '总计', '本期', 1.25, '亿元'),
             fact('cost_cur', '成本', '总计', '本期', 500, '万元')]
    out = compute(facts, Derivations([{'id': 'profit', 'expr': 'diff(sales_cur, cost_cur)'}]))
    # 1.25 亿元 − 500 万元 = 1.20 亿元
    assert str(out['values']['profit']) == '1.20'
    assert out['facts'][-1]['unit'] == '亿元'
    assert '亿元' in out['details']['profit']


@pytest.mark.parametrize('expr,reason', [
    ('sum(a_qty, sales_cur)', '统计口径'),
    ('growth(sales_prev, sales_cur)', '第二个是上期'),
    ('growth(a_qty, a_qty_other)', '第二个是上期'),
], ids=['sum_scope_mismatch', 'growth_period_order', 'growth_both_current'])
def test_incompatible_inputs_report_reason(base, expr, reason):
    out = compute(base, Derivations([{'id': 'bad', 'expr': expr}]))
    assert out['values']['bad'] is None
    assert reason in out['errors']['bad']
    # 派生事实无法计算时不应混进事实表，避免下游误用
    assert all(f['id'] != 'bad' for f in out['facts'])


def test_zero_and_negative_base_are_refused():
    facts = [fact('sales_prev', '销售额', '总计', '上期', 0), fact('sales_cur', '销售额', '总计', '本期', 10)]
    out = compute(facts, Derivations([{'id': 'g', 'expr': 'growth(sales_cur, sales_prev)'}]))
    assert '大于零' in out['errors']['g']

    out = compute(facts, Derivations([{'id': 'r', 'expr': 'ratio(sales_cur, sales_prev)'}]))
    assert '分母' in out['errors']['r']


# ---- 图算法 --------------------------------------------------------------

def test_topological_order_places_sources_first():
    d = Derivations([
        {'id': 'c', 'expr': 'diff(b, a)'},
        {'id': 'b', 'expr': 'sum(a, a2)'},
    ])
    assert d.order.index('b') < d.order.index('c')
    assert d.cycles == []


def test_cycle_dependency_is_detected_not_silently_sorted(base):
    d = Derivations([
        {'id': 'x', 'expr': 'diff(y, sales_cur)'},
        {'id': 'y', 'expr': 'diff(x, sales_cur)'},
    ])
    assert d.cycles
    problems = d.validate({f['id'] for f in base})
    assert any('循环依赖' in p for p in problems)


def test_validate_reports_missing_and_self_reference(base):
    d = Derivations([
        {'id': 'p', 'expr': 'diff(sales_cur, nope)'},
        {'id': 'q', 'expr': 'diff(q, sales_cur)'},
    ])
    problems = d.validate({f['id'] for f in base})
    assert any('不存在的事实' in p for p in problems)
    assert any('引用了自己' in p for p in problems)


def test_duplicate_definition_is_refused():
    with pytest.raises(DerivationError):
        Derivations([{'id': 'p', 'expr': 'diff(sales_cur, cost_cur)'},
                     {'id': 'p', 'expr': 'diff(sales_cur, cost_prev)'}])


def test_removing_in_use_or_missing_derivation_is_refused():
    d = Derivations([{'id': 'p', 'expr': 'diff(sales_cur, cost_cur)'}])
    with pytest.raises(DerivationError):
        d.remove('nope')


def test_derivation_built_on_failed_derivation_is_refused(base):
    """上游算不出来时，下游不能拿 None 继续算，必须一并转人工复核。"""
    d = Derivations([
        {'id': 'r', 'expr': 'ratio(sales_cur, sales_prev)', 'unit': '%'},
        {'id': 'profit', 'expr': 'diff(sales_cur, cost_cur)'},
        {'id': 'chain', 'expr': 'diff(profit, r)'},
    ])
    facts = [f for f in base if f['id'] != 'sales_prev']
    facts.append(fact('sales_prev', '销售额', '总计', '上期', 0))
    out = compute(facts, d)
    assert out['errors']['r']
    assert '一并转人工复核' in out['errors']['chain']


def test_removing_derivation_in_use_is_refused():
    d = Derivations([{'id': 'profit', 'expr': 'diff(sales_cur, cost_cur)'},
                     {'id': 'margin', 'expr': 'ratio(profit, sales_cur)'}])
    with pytest.raises(DerivationError):
        d.remove('profit')
    d.remove('margin')
    assert 'margin' not in d._index


def test_reachable_walks_transitive_dependencies():
    d = Derivations([
        {'id': 'profit', 'expr': 'diff(sales_cur, cost_cur)'},
        {'id': 'margin', 'expr': 'ratio(profit, sales_cur)'},
        {'id': 'unrelated', 'expr': 'sum(a_qty, b_qty)'},
    ])
    assert d.reachable(['sales_cur']) == ['profit', 'margin']
    assert 'unrelated' not in d.reachable(['sales_cur'])
    assert d.dependents_of('cost_cur') == ['profit']


# ---- 级联重算与影响半径 --------------------------------------------------

def test_change_cascades_through_derived_facts(base):
    d = Derivations([
        {'id': 'profit', 'expr': 'diff(sales_cur, cost_cur)'},
        {'id': 'margin', 'expr': 'ratio(profit, sales_cur)'},
    ])
    first = compute(base, d)
    assert str(first['values']['profit']) == '75.00'

    # 只改一个基础事实，下游两级派生事实应自动跟着变
    second = compute(base, d, changed=['cost_cur'], overrides={'cost_cur': 100},
                     previous=first['values'])
    assert str(second['values']['profit']) == '25.00'
    assert str(second['values']['margin']) == '20.00'
    assert second['affected'] == ['profit', 'margin']
    assert set(second['changed']) == {'profit', 'margin'}
    assert 0 < second['radius'] < 1


def test_unchanged_values_are_not_reported_as_changed(base):
    d = Derivations([{'id': 'total_qty', 'expr': 'sum(a_qty, b_qty)'}])
    first = compute(base, d)
    second = compute(base, d, previous=first['values'])
    assert second['changed'] == []


def test_sum_detects_subject_or_scope_mismatch(base):
    out = compute(base, Derivations([{'id': 'bad', 'expr': 'sum(a_qty, sales_cur)'}]))
    assert '统计口径' in out['errors']['bad']


# ---- 受影响论断分组 ------------------------------------------------------

def test_impact_separates_direct_and_indirect_claims(base):
    d = Derivations([{'id': 'profit', 'expr': 'diff(sales_cur, cost_cur)'}])
    claims = [
        {'id': 'c1', 'refs': ['cost_cur']},
        {'id': 'c2', 'refs': ['profit']},
        {'id': 'c3', 'refs': ['a_qty']},
    ]
    result = impact(d, claims, ['cost_cur'])
    assert result['direct'] == ['c1']
    assert result['indirect'] == ['c2']
    assert result['total'] == 2
    assert 'profit' in result['affected_facts']
