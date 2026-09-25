from zhilian import reranker


def test_local_reranker_is_opt_in(monkeypatch):
    monkeypatch.delenv('ZHILIAN_LOCAL_RERANKER_PATH', raising=False)
    monkeypatch.delenv('ZHILIAN_LOCAL_RERANKER_ENABLED', raising=False)
    assert reranker.status()['enabled'] is False


def test_reranker_abstains_when_margin_is_small():
    scores = [
        {'fact_id': 'a', 'score': 0.2, 'raw_score': -1.0},
        {'fact_id': 'b', 'score': 0.19, 'raw_score': -1.2},
    ]
    result = reranker.choose(scores, min_score=-2.0, min_margin=0.3)
    assert result['action'] == 'abstain'


def test_reranker_accepts_calibrated_candidate():
    scores = [
        {'fact_id': 'a', 'score': 0.2, 'raw_score': -1.0},
        {'fact_id': 'b', 'score': 0.1, 'raw_score': -1.4},
    ]
    result = reranker.choose(scores, min_score=-2.0, min_margin=0.3)
    assert result['action'] == 'link'
    assert result['refs'] == ['a']
