"""真实中文语料表达方式：年报用词、千分位数值、动词变体。

背景：引擎在项目自建的合成语料上识别率 100%，但在真实上市公司年报上
识别率约 0.5%（580 条含数字句子中仅 3 条）。本文件锁定已补齐的那部分能力，
并明确记录仍未覆盖的部分，避免再次出现「合成语料 100% = 真实泛化能力」的误判。
"""
import pytest

from zhilian.engine import extract_claims, number


def kinds(text, facts=()):
    return [c['kind'] for c in extract_claims(
        {'file_id': 'F', 'location': ['p', 0], 'label': 't', 'text': text}, list(facts))]


# ---- 千分位数值 ----------------------------------------------------------

@pytest.mark.parametrize('raw,expected', [
    ('3,379.37', '3379.37'),
    ('1,234,567.89', '1234567.89'),
    ('-1,000', '-1000'),
    ('125', '125'),
    ('0.5', '0.5'),
])
def test_thousand_separator_is_parsed(raw, expected):
    assert str(number(raw)) == expected


@pytest.mark.parametrize('bad', ['1,23', ',123', '1,', '12,3456'])
def test_malformed_separator_is_rejected(bad):
    """逗号不按三位分组时不剥离，避免把异常输入悄悄改成一个别的数。"""
    with pytest.raises(ValueError):
        number(bad)


def test_quote_with_thousand_separator_is_extracted():
    assert kinds('报告期内投资收益为3,379.37万元') == ['quote']
    claim = extract_claims(
        {'file_id': 'F', 'location': ['p', 0], 'label': 't', 'text': '投资收益为3,379.37万元'}, [])[0]
    assert claim['spec']['reported'] == pytest.approx(3379.37)


# ---- 增长率用词 ----------------------------------------------------------

@pytest.mark.parametrize('text', [
    '较上期增长25%',          # 原有表达，必须保持可用
    '较上期下降10%',
    '营业收入同比增长25%',     # 年报常用「同比」
    '营业收入较上年增加553.21%',  # 年报用「较上年」+「增加」
    '营业成本较上年减少12.5%',
    '营业收入比上年上升8%',
])
def test_growth_vocabulary_variants_are_recognized(text):
    assert kinds(text) == ['growth']


@pytest.mark.parametrize('text,direction', [
    ('营业收入同比增长25%', 1),
    ('营业收入较上年增加553.21%', 1),
    ('营业收入比上年上升8%', 1),
    ('营业成本较上年减少12.5%', -1),
    ('较上期下降10%', -1),
    ('较上期持平', 0),
])
def test_growth_direction_is_mapped_from_vocabulary(text, direction):
    """方向词可能是否定含义的动词，必须映射正确，否则会把下降读成增长。"""
    spec = extract_claims(
        {'file_id': 'F', 'location': ['p', 0], 'label': 't', 'text': text}, [])[0]['spec']
    assert spec['direction'] == direction


def test_negative_direction_reports_negative_value():
    spec = extract_claims(
        {'file_id': 'F', 'location': ['p', 0], 'label': 't',
         'text': '营业成本较上年减少12.5%'}, [])[0]['spec']
    assert spec['reported'] < 0


def test_qualitative_growth_still_supported():
    spec = extract_claims(
        {'file_id': 'F', 'location': ['p', 0], 'label': 't',
         'text': '营业收入同比增长'}, [])[0]['spec']
    assert spec['qualitative'] is True


# ---- 阈值用词 ------------------------------------------------------------

@pytest.mark.parametrize('text', [
    '支出未超过预算',
    '本期销售额超过120万元',
    '营业收入占比超过50%',
    '支出不少于100万元',
    '本期支出低于100万元',
])
def test_threshold_variants_are_recognized(text):
    assert kinds(text) == ['threshold']


def test_threshold_limit_with_separator():
    spec = extract_claims(
        {'file_id': 'F', 'location': ['p', 0], 'label': 't',
         'text': '本期销售额超过1,200万元'}, [])[0]['spec']
    assert spec['limit'] == pytest.approx(1200.0)


# ---- 已知缺口：明确记录为「尚未支持」------------------------------------

@pytest.mark.parametrize('text,reason', [
    ('营业收入占比已超过公司全部营业收入的50%以上', '算子与数值之间隔着较长定语'),
    ('公司产品长链二元酸产量增加179.79%', '无期间限定词的裸「增加」'),
    ('本期毛利率低于去年同期', '与历史期间比较但无数值'),
    ('生物基、淀粉基新材增加187.44', '表格残片，无单位'),
])
def test_known_gaps_are_documented_not_silently_wrong(text, reason):
    """这些是真实年报里的表达，当前引擎识别不到。

    这里断言「识别不到」而非「识别对了」，是为了把缺口固定在测试里：
    一旦后续补齐，本测试会失败，从而提醒同步更新文档与评测口径。
    """
    assert kinds(text) == [], f'缺口已变化（{reason}），请更新文档与评测口径'
