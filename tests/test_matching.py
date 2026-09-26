"""事实定位索引：语义与旧实现等价，且句中没有期间时仍能匹配。"""
import pytest

from zhilian.engine import build_index, best_facts, extract_claims, facts_index


def fact(fid, subject, metric, period, value=100, unit='万元', scope='口径A'):
    return {'id': fid, 'subject': subject, 'metric': metric, 'period': period,
            'value': value, 'unit': unit, 'scope': scope, 'sheet': 'S', 'cell': 'A1'}


BASE = [
    fact('sales_prev', '总计', '销售额', '上期', 100),
    fact('sales_current', '总计', '销售额', '本期', 125),
    fact('product_a', 'A产品', '销量', '本期', 80, '件'),
    fact('product_b', 'B产品', '销量', '本期', 65, '件'),
]


def ids(found):
    return [f['id'] for f in found]


def test_fact_without_period_in_text_still_matches():
    """句子没写期间时必须仍能定位。

    期间只参与加分、不参与"能否匹配"；把它当成必需描述符会让
    「A产品销量最高」这类常见句子匹配不到任何事实。
    """
    assert ids(best_facts('A产品销量最高', BASE)) == ['product_a']
    assert ids(best_facts('本期销售额为125万元', BASE)) == ['sales_current']
    assert ids(best_facts('支出未超过预算', BASE)) == []


def test_subject_narrows_candidates_when_metric_is_shared():
    assert ids(best_facts('B产品销量为65件', BASE)) == ['product_b']
    assert ids(best_facts('A产品销量最高', BASE)) == ['product_a']
    # 主体写了但指标没写：定位不到，应保持无来源而不是乱猜
    assert best_facts('A产品的情况', BASE) == []
    # 两个主体的名字都没出现在句子里时，它们不会进入候选
    assert best_facts('本期销量情况', BASE) == []


def test_period_argument_filters_explicitly():
    assert ids(best_facts('销售额', BASE, period='本期')) == ['sales_current']
    assert ids(best_facts('销售额', BASE, period='上期')) == ['sales_prev']


def test_period_written_in_text_decides_between_tied_facts():
    """句中写了期间时应唯一命中；没写期间则并列返回。

    并列只可能出现在"期间未写"的情形：主体不同时，主体名必须命中文本
    才算候选，所以不同主体的事实不会互相并列。
    """
    assert ids(best_facts('本期销售额为125万元', BASE)) == ['sales_current']
    assert ids(best_facts('上期销售额为100万元', BASE)) == ['sales_prev']
    assert set(ids(best_facts('销售额为125万元', BASE))) == {'sales_prev', 'sales_current'}


def test_generic_subject_is_not_treated_as_a_locator():
    """泛指主体不作为定位依据：它不该让「A产品」的事实参与竞争。"""
    assert ids(best_facts('本期销售额为125万元', BASE)) == ['sales_current']
    assert 'product_a' not in ids(best_facts('销售额为125万元', BASE))


def test_empty_and_unmatched_text_return_nothing():
    assert best_facts('', BASE) == []
    assert best_facts('本段是背景说明', BASE) == []


def test_index_matches_direct_scan_for_every_case():
    index = build_index(BASE)
    texts = ['A产品销量最高', '本期销售额为125万元', '销售额', '上期销售额',
             '销量为80件', '本段是背景说明', '本期销售额超过120万元']
    for text in texts:
        for period in (None, '本期', '上期'):
            assert ids(best_facts(text, BASE, period=period, index=index)) == \
                   ids(best_facts(text, BASE, period=period)), (text, period)


def test_cached_index_is_reused_and_still_correct():
    first = facts_index(BASE)
    second = facts_index([dict(f) for f in BASE])
    assert first is second
    assert ids(best_facts('A产品销量最高', BASE, index=second)) == ['product_a']
    # 描述符变化后必须重建，不能沿用旧索引
    changed = BASE + [fact('product_c', 'C产品', '销量', '本期', 70, '件')]
    assert ids(best_facts('C产品销量最高', changed, index=facts_index(changed))) == ['product_c']


def test_extract_claims_accepts_shared_index():
    block = {'file_id': 'F', 'location': ['p', 1], 'label': '正文第1段',
             'text': '本期销售额为125万元。A产品销量最高。'}
    index = build_index(BASE)
    with_index = extract_claims(block, BASE, index=index)
    without = extract_claims(block, BASE)
    assert [c['kind'] for c in with_index] == [c['kind'] for c in without]
    assert [c['refs'] for c in with_index] == [c['refs'] for c in without]
    assert len(with_index) == 2


def test_many_facts_do_not_change_matching_result():
    """规模变化不应改变匹配结果（索引只是缩小候选）。"""
    many = BASE + [fact(f'extra{i}', f'主体{i}', f'指标{i}', '本期') for i in range(300)]
    for text in ['A产品销量最高', '本期销售额为125万元', '销量为80件']:
        assert ids(best_facts(text, many)) == ids(best_facts(text, BASE))


def test_period_synonyms_disambiguate_current_vs_previous():
    """期间同义写法必须能区分本期与上期，否则两条事实同分并列。

    真实文档写「报告期内/本年度/去年同期」，事实表只写「本期/上期」。不归一化时
    上期与本期同为 5 分，一条普通数值引用会被判成"口径不唯一"而返回两条。
    """
    for text in ('本报告期销售额为125万元', '报告期内销售额为125万元',
                 '本年度销售额为125万元', '当期销售额为125万元'):
        assert ids(best_facts(text, BASE)) == ['sales_current'], text
    for text in ('去年同期销售额为100万元', '上年销售额为100万元'):
        assert ids(best_facts(text, BASE)) == ['sales_prev'], text


def test_period_synonyms_do_not_break_growth_pairing():
    """含两期表述的句子仍应同时命中两期，不能被同义词规则收窄成一条。"""
    assert set(ids(best_facts('本期销售额较上期增长', BASE))) == {'sales_prev', 'sales_current'}
