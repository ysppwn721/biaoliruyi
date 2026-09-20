import json
from copy import deepcopy

import httpx
import pytest

from zhilian.demo import create_demo
from zhilian.store import Store
from zhilian.engine import check, extract_claims
from zhilian import llm


def test_qualitative_growth_preserved_and_invalidated(tmp_path):
    store = Store(tmp_path/'data')
    w = store.create('test', create_demo(tmp_path/'files'))
    text = '本期销售额较上期增长。'
    c = extract_claims({'file_id':'f','location':'x','label':'test','text':text}, w['facts'])[0]
    assert c['spec']['qualitative']
    facts = deepcopy(w['facts'])
    fact = next(f for f in facts if f['id']=='sales_current')
    fact['value'] = 120
    assert check(c,facts)['status']=='consistent'
    fact['value'] = 90
    assert check(c,facts)['expected']=='本期销售额较上期下降'


def test_model_disabled(monkeypatch):
    monkeypatch.delenv('ZHILIAN_LLM_BASE_URL', raising=False)
    monkeypatch.delenv('ZHILIAN_LLM_MODEL', raising=False)
    assert not llm.config()['enabled']
    with pytest.raises(ValueError, match='尚未配置'):
        llm.suggest_links([],[])


def test_model_suggestions_validated_without_key_leak(monkeypatch,tmp_path):
    monkeypatch.setenv('ZHILIAN_LLM_BASE_URL','http://127.0.0.1:11434/v1')
    monkeypatch.setenv('ZHILIAN_LLM_MODEL','test-local-model')
    monkeypatch.setenv('ZHILIAN_LLM_API_KEY','test-secret')
    store=Store(tmp_path/'data')
    w=store.create('test',create_demo(tmp_path/'files'))
    first=w['claims'][0]
    def fake_post(url,**kwargs):
        assert url.endswith('/v1/chat/completions')
        assert kwargs['headers']['Authorization']=='Bearer test-secret'
        # Fact values are not needed for semantic linking and are not sent.
        user=json.loads(kwargs['json']['messages'][1]['content'])
        assert 'value' not in user['facts'][0]
        content={'suggestions':[
            {'claim_id':first['id'],'refs':first['refs'],'reason':'match'},
            {'claim_id':first['id'],'refs':['invented-id'],'reason':'bad'},
            {'claim_id':'nonexistent','refs':[],'reason':'bad'}]}
        return httpx.Response(200,json={'choices':[{'message':{'content':json.dumps(content)}}]})
    monkeypatch.setattr(httpx,'post',fake_post)
    result=llm.suggest_links(w['claims'],w['facts'])
    assert len(result)==1
    assert first['confirmed'] is False
    assert 'test-secret' not in json.dumps(llm.config())


def test_model_error_does_not_expose_provider_body(monkeypatch):
    monkeypatch.setenv('ZHILIAN_LLM_BASE_URL','https://example.test/v1')
    monkeypatch.setenv('ZHILIAN_LLM_MODEL','model')
    monkeypatch.setattr(httpx,'post',lambda *args,**kwargs:httpx.Response(401,text='secret-body'))
    c={'id':'c','kind':'quote','original':'x','refs':[],'confirmed':False}
    with pytest.raises(ValueError) as exc:
        llm.suggest_links([c],[])
    assert 'secret-body' not in str(exc.value)
