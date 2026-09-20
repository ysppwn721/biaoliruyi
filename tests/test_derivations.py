"""事实依赖图在工作区中的完整闭环：定义派生事实、级联重算、间接影响、撤销。"""
import pytest
from fastapi.testclient import TestClient
from zhilian.app import create_app
from zhilian.demo import create_demo
from zhilian.store import Store

DERIVATIONS = [
    {'id': 'spending_ratio', 'expr': 'ratio(spending, budget)', 'label': '预算执行率', 'unit': '%'},
    {'id': 'sales_diff', 'expr': 'diff(sales_current, sales_prev)', 'label': '销售额差额', 'unit': '万元'},
]


@pytest.fixture
def project(tmp_path):
    store = Store(tmp_path / 'data')
    w = store.create('测试项目', create_demo(tmp_path / 'files'), True)
    w = store.confirm(w['id'], w['revision'],
                      [{'claim_id': c['id'], 'refs': c['refs']} for c in w['claims']])
    return store, w


def fact(w, fid):
    return next(f for f in w['facts'] if f['id'] == fid)


def test_derived_facts_join_the_fact_table(project):
    store, w = project
    assert w['summary']['facts'] == 6          # 演示数据只有基础事实
    w = store.set_derivations(w['id'], w['revision'], DERIVATIONS)
    assert w['summary']['facts'] == 8
    assert w['summary']['derived'] == 2
    assert w['summary']['errors'] == 0
    # 80 ÷ 100 × 100 = 80%；125 − 100 = 25
    assert fact(w, 'spending_ratio')['value'] == 80.0
    assert fact(w, 'sales_diff')['value'] == 25.0
    assert fact(w, 'sales_diff')['derived'] is True
    assert fact(w, 'spending_ratio')['unit'] == '%'
    # 既有论断不受影响
    assert w['summary']['inconsistent'] == 0
    assert w['graph']['details']['spending_ratio'] == '80 ÷ 100 × 100 = 80%（同期占比）'


def test_change_identifies_only_derived_facts_that_moved(project):
    store, w = project
    w = store.set_derivations(w['id'], w['revision'], DERIVATIONS)
    w = store.change(w['id'], w['revision'], {'sales_current': 90})
    # 只改销售额：差额变了，与销售额无关的占比不应被报成变化
    assert w['cascade']['changed_derived'] == ['sales_diff']
    assert w['cascade']['affected_facts'] == ['sales_diff']
    assert fact(w, 'sales_diff')['value'] == -10.0
    assert fact(w, 'spending_ratio')['value'] == 80.0
    assert w['cascade']['radius'] > 0
    assert w['cascade']['direct_claims']
    assert w['summary']['inconsistent'] == 7


def test_claims_referencing_derived_facts_are_reported_as_indirect(project):
    store, w = project
    # 两个事实必须同口径：演示数据里 销售额/预算/支出 的口径并不相同，
    # 因此这里用上期与本期销售额（同为「演示业务」）派生差额。
    w = store.set_derivations(w['id'], w['revision'], [
        {'id': 'spending_ratio', 'expr': 'ratio(spending, budget)', 'label': '预算执行率', 'unit': '%'},
        {'id': 'sales_diff', 'expr': 'diff(sales_current, sales_prev)', 'label': '销售额差额', 'unit': '万元'},
    ])
    assert fact(w, 'sales_diff')['value'] == 25.0
    # 把已确认的阈值论断改绑到派生事实：模拟结论引用的是推导值而非原始数据
    source = next(c for c in w['claims'] if c['kind'] == 'threshold' and c['refs'] == ['sales_current'])
    w = store.confirm(w['id'], w['revision'], [{'claim_id': source['id'], 'refs': ['sales_diff']}])
    rebound = next(c for c in w['claims'] if c['id'] == source['id'])
    assert rebound['refs'] == ['sales_diff']
    assert rebound['confirmed'] is True
    # 25 万元未超过 120 万元，因此改绑后可核验且当前不一致
    assert next(r for r in w['checks'] if r['claim_id'] == source['id'])['status'] == 'inconsistent'

    w = store.change(w['id'], w['revision'], {'sales_current': 90})
    # 论断引用的是派生事实：基础事实变化经依赖图传播后才影响到它
    assert source['id'] in w['cascade']['indirect_claims']
    assert source['id'] not in w['cascade']['direct_claims']
    assert w['cascade']['changed_derived'] == ['sales_diff']
    assert w['cascade']['affected_facts'] == ['sales_diff']


def test_editing_a_derived_fact_directly_is_refused(project):
    store, w = project
    w = store.set_derivations(w['id'], w['revision'], DERIVATIONS)
    with pytest.raises(ValueError, match='派生事实'):
        store.change(w['id'], w['revision'], {'sales_diff': 999})


def test_invalid_derivations_are_refused_without_writing(project):
    store, w = project
    w = store.set_derivations(w['id'], w['revision'], DERIVATIONS)
    revision = w['revision']
    for bad, reason in [
        ([{'id': 'x', 'expr': 'diff(sales_current, nope)'}], '不存在的事实'),
        ([{'id': 'x', 'expr': 'diff(x, sales_current)'}], '引用了自己'),
        ([{'id': 'x', 'expr': 'sum(budget)'}], '至少需要两个'),
        ([{'id': 'a', 'expr': 'diff(b, sales_current)'},
          {'id': 'b', 'expr': 'diff(a, sales_current)'}], '循环依赖'),
        ([{'id': 'x', 'expr': 'exec(sales_current)'}], '不支持的运算'),
    ]:
        with pytest.raises(ValueError, match=reason):
            store.set_derivations(w['id'], revision, bad)
    # 非法定义不得写入：revision 与派生定义都应保持原样
    state = store.read(w['id'])
    assert state['revision'] == revision
    assert [d['id'] for d in state['derivations']] == ['spending_ratio', 'sales_diff']


def test_removing_a_dependency_in_use_is_refused(project):
    store, w = project
    w = store.set_derivations(w['id'], w['revision'], [
        {'id': 'profit', 'expr': 'diff(sales_current, spending)'},
        {'id': 'margin', 'expr': 'ratio(profit, sales_current)'},
    ])
    with pytest.raises(ValueError, match='被派生事实引用'):
        store.remove_derivation(w['id'], w['revision'], 'profit')
    w = store.remove_derivation(w['id'], w['revision'], 'margin')
    w = store.remove_derivation(w['id'], w['revision'], 'profit')
    assert w['summary']['derived'] == 0
    assert w['summary']['facts'] == 6


def test_undo_restores_derivations_and_values(project):
    store, w = project
    w = store.set_derivations(w['id'], w['revision'], DERIVATIONS)
    w = store.change(w['id'], w['revision'], {'sales_current': 90})
    assert fact(w, 'sales_diff')['value'] == -10.0
    w = store.undo(w['id'], w['revision'])
    assert fact(w, 'sales_diff')['value'] == 25.0
    assert w['summary']['derived'] == 2
    assert w['summary']['inconsistent'] == 0


def test_derivations_endpoints_over_http(tmp_path):
    data = create_demo(tmp_path / 'files')
    client = TestClient(create_app(str(tmp_path / 'data')))
    project = client.post('/api/projects/demo').json()
    wid = project['id']
    revision = project['revision']

    listed = client.get(f'/api/projects/{wid}/derivations').json()
    assert listed['derivations'] == []

    body = {'revision': revision, 'derivations': DERIVATIONS}
    created = client.post(f'/api/projects/{wid}/derivations', json=body)
    assert created.status_code == 200
    payload = created.json()
    assert payload['summary']['derived'] == 2
    assert payload['graph']['errors'] == {}

    listed = client.get(f'/api/projects/{wid}/derivations').json()
    assert [d['id'] for d in listed['derivations']] == ['spending_ratio', 'sales_diff']
    assert listed['cycles'] == []

    bad = client.post(f'/api/projects/{wid}/derivations',
                      json={'revision': payload['revision'],
                            'derivations': [{'id': 'x', 'expr': 'diff(sales_current, nope)'}]})
    assert bad.status_code == 400
    assert '不存在的事实' in bad.json()['detail']

    removed = client.delete(f"/api/projects/{wid}/derivations/sales_diff?revision={payload['revision']}")
    assert removed.status_code == 200
    assert removed.json()['summary']['derived'] == 1


def test_export_and_report_still_work_with_derivations(project):
    store, w = project
    w = store.set_derivations(w['id'], w['revision'], DERIVATIONS)
    archive = store.archive(w['id'])
    assert archive.exists()
    assert archive.stat().st_size > 0
