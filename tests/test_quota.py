"""模型调用限额：按访客与全局双闸门，超限降级为规则模式而不是报错。"""
import json
from datetime import date, timedelta

import httpx
import pytest
from fastapi.testclient import TestClient

from zhilian import agent, quota
from zhilian.app import create_app
from zhilian.demo import create_demo
from zhilian.store import Store


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setenv('DEEPSEEK_API_KEY', '')
    monkeypatch.setenv('DEEPSEEK_MODEL', 'deepseek-flash')
    monkeypatch.setattr('zhilian.app.load_environment', lambda: None)
    quota.configure(tmp_path / 'quota.json')
    token = quota.identify('测试访客')
    yield
    quota.release(token)


@pytest.fixture
def project(tmp_path):
    store = Store(tmp_path / 'data')
    return store, store.create('限额测试', create_demo(tmp_path / 'files'), True)


def force_hard_claims(monkeypatch):
    """把全部论断当作困难样本，确保走到远程模型这一段。"""
    routing = agent._candidate_buckets
    def all_hard(ws, rules):
        unique, multi, zero = routing(ws, rules)
        return [], [], unique + multi + zero
    monkeypatch.setattr(agent, '_candidate_buckets', all_hard)


def fake_api(monkeypatch, calls):
    def post(url, **kwargs):
        calls.append(url)
        payload = {'suggestions': [{'claim_id': kwargs['json']['messages'][1]['content'][:0] or 'x',
                                    'refs': [], 'reason': ''}]}
        return httpx.Response(200, json={'choices': [{'message': {'content': json.dumps(payload)}}]})
    monkeypatch.setattr(httpx, 'post', post)


def test_per_client_limit_degrades_to_rules(project, tmp_path, monkeypatch):
    store, ws = project
    monkeypatch.setenv('DEEPSEEK_API_KEY', 'test-secret')
    monkeypatch.setenv('ZHILIAN_QUOTA_PER_CLIENT', '1')
    monkeypatch.setenv('ZHILIAN_QUOTA_GLOBAL', '50')
    force_hard_claims(monkeypatch)
    calls = []
    fake_api(monkeypatch, calls)

    ws = agent.run_agent(store, ws['id'], ws['revision'])
    assert len(calls) == 1, '首次应调用模型'
    assert ws['agent']['model_routing']['model_quota']['client_used'] == 1
    assert ws['agent']['model_routing']['api_batches'] == 1

    # 同一访客再开一个新项目：额度已用尽，必须降级但仍走完流程。
    # （对同一项目重复 run 本来就会复用已有候选，不会重新路由。）
    second = store.create('限额测试·第二个项目', create_demo(tmp_path / 'files2'), True)
    before = len(calls)
    ws = agent.run_agent(store, second['id'], second['revision'])
    assert len(calls) == before, '额度用尽后不应再发起外部请求'
    assert any(a['event'] == '模型额度用尽' for a in ws['audit'])
    assert any(t['node'] == 'model_skipped' and '额度' in t['summary'] for t in ws['agent']['trace'])
    assert ws['agent']['model_routing']['model_quota']['client_remaining'] == 0
    assert ws['agent']['model_routing']['api_batches'] == 0
    assert ws['agent']['pending'], '仍应把候选交给人工确认，而不是卡住'


def test_global_limit_blocks_every_visitor(project, monkeypatch):
    store, ws = project
    monkeypatch.setenv('DEEPSEEK_API_KEY', 'test-secret')
    monkeypatch.setenv('ZHILIAN_QUOTA_PER_CLIENT', '100')
    monkeypatch.setenv('ZHILIAN_QUOTA_GLOBAL', '1')
    force_hard_claims(monkeypatch)
    calls = []
    fake_api(monkeypatch, calls)

    ws = agent.run_agent(store, ws['id'], ws['revision'])
    assert len(calls) == 1
    # 换一个访客也应被全局预算拦住
    token = quota.identify('另一个访客')
    try:
        ws = agent.run_agent(store, ws['id'], ws['revision'])
        assert len(calls) == 1, '全局预算用尽后任何访客都不应再发起请求'
        assert quota.check()['code'] == 'global_exhausted'
    finally:
        quota.release(token)


def test_quota_counts_per_visitor_and_resets_next_day(tmp_path, monkeypatch):
    monkeypatch.setenv('ZHILIAN_QUOTA_PER_CLIENT', '2')
    quota.consume('访客甲')
    quota.consume('访客甲')
    assert quota.check('访客甲')['code'] == 'client_exhausted'
    assert quota.check('访客乙')['allowed'] is True, '额度必须按访客隔离'
    assert quota.snapshot('访客甲')['global_used'] == 2

    # 模拟跨天：把日期改成昨天，计数应清零
    path = tmp_path / 'quota.json'
    data = json.loads(path.read_text(encoding='utf-8'))
    data['day'] = (date.today() - timedelta(days=1)).isoformat()
    path.write_text(json.dumps(data), encoding='utf-8')
    assert quota.snapshot('访客甲')['client_used'] == 0
    assert quota.snapshot('访客甲')['global_used'] == 0


def test_quota_file_is_never_a_single_point_of_failure(tmp_path, monkeypatch):
    """文件损坏或不可写时按零消耗处理，绝不能影响演示。"""
    monkeypatch.setenv('ZHILIAN_QUOTA_PER_CLIENT', '5')
    quota.configure(tmp_path / 'quota.json')
    (tmp_path / 'quota.json').write_text('{ 这不是 JSON', encoding='utf-8')
    assert quota.check('访客')['allowed'] is True
    quota.consume('访客')
    assert quota.snapshot('访客')['client_used'] == 1


def test_quota_endpoint_and_health_expose_limits(tmp_path, monkeypatch):
    monkeypatch.delenv('ZHILIAN_ACCESS_PASSWORD', raising=False)
    monkeypatch.setenv('ZHILIAN_QUOTA_PER_CLIENT', '30')
    monkeypatch.setenv('ZHILIAN_QUOTA_GLOBAL', '300')
    app = create_app(tmp_path / 'api')
    client = TestClient(app)
    health = client.get('/api/health').json()
    assert health['quota']['per_client_limit'] == 30 and health['quota']['global_limit'] == 300
    state = client.get('/api/quota').json()
    assert state['client_remaining'] == 30 and state['global_remaining'] == 300


def test_visitor_identity_follows_cloudflare_header():
    """演示环境在 Cloudflare 之后，必须用 CF-Connecting-IP 而不是边缘节点地址。"""
    headers = {'cf-connecting-ip': '203.0.113.9', 'x-forwarded-for': '198.51.100.7'}
    assert quota.client_key(headers, '10.0.0.1') == '203.0.113.9'
    assert quota.client_key({'x-forwarded-for': '198.51.100.7, 10.0.0.1'}, '10.0.0.1') == '198.51.100.7'
    assert quota.client_key({}, '127.0.0.1') == '127.0.0.1'
