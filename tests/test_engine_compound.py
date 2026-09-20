from zhilian.engine import check, extract_claims


FACTS = [
    {'id': 'sales_prev', 'subject': '总计', 'metric': '销售额', 'period': '上期', 'value': 100,
     'unit': '万元', 'scope': '演示业务'},
    {'id': 'sales_current', 'subject': '总计', 'metric': '销售额', 'period': '本期', 'value': 90,
     'unit': '万元', 'scope': '演示业务'},
]


def claims_for(text):
    return extract_claims({'file_id': 'file', 'location': ['p', 0], 'label': '正文', 'text': text}, FACTS)


def test_compound_sentence_checks_each_assertion():
    claims = claims_for('本期销售额为999万元，较上期增长25%。')

    assert [c['kind'] for c in claims] == ['quote', 'growth']
    assert [check(c, FACTS)['status'] for c in claims] == ['inconsistent', 'inconsistent']
    assert claims[0]['end'] <= claims[1]['start']


def test_compound_threshold_does_not_hide_value_quote():
    claims = claims_for('本期销售额为999万元且超过120万元。')

    assert {c['kind'] for c in claims} == {'quote', 'threshold'}
    assert all(check(c, FACTS)['status'] == 'inconsistent' for c in claims)
