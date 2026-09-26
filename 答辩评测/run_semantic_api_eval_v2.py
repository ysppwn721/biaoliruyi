"""Run the real DeepSeek fallback on the evaluation-only semantic rewrite set."""
from __future__ import annotations

import json
import time
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parent))
from zhilian import llm
from zhilian.office import read_facts

DATA = ROOT / 'semantic_rewrite_eval_v2.jsonl'
FACTS_PATH = ROOT.parent / '长文Word测试' / '配套数据_初始.xlsx'
OUT = ROOT / 'semantic_rewrite_eval_v2_api_predictions.jsonl'
STATS = ROOT / 'semantic_rewrite_eval_v2_api_stats.json'


def main():
    if not llm.config()['enabled']:
        raise SystemExit('DEEPSEEK_API_KEY is not configured in this process')
    rows = [json.loads(line) for line in DATA.open(encoding='utf-8') if line.strip()]
    facts = read_facts(FACTS_PATH, 'facts')
    claims = []
    seen = set()
    for row in rows:
        if row['claim_id'] in seen:
            continue
        seen.add(row['claim_id'])
        claims.append({'id': row['claim_id'], 'kind': 'quote', 'original': row['claim_text'],
                       'refs': [], 'confirmed': False})
    predictions = []
    calls = []
    for start in range(0, len(claims), 40):
        batch = claims[start:start + 40]
        started = time.perf_counter()
        suggestions = llm.suggest_links(batch, facts)
        elapsed = round((time.perf_counter() - started) * 1000, 1)
        by_claim = {item['claim_id']: item for item in suggestions}
        for claim in batch:
            item = by_claim.get(claim['id'], {})
            refs = item.get('refs', []) if isinstance(item.get('refs'), list) else []
            predictions.append({'claim_id': claim['id'], 'action': 'link' if refs else 'abstain',
                                'refs': list(dict.fromkeys(refs)), 'source': 'deepseek'})
        calls.append({'batch': len(calls) + 1, 'claims': len(batch), 'suggestions': len(suggestions),
                      'latency_ms': elapsed, 'status': 'ok'})
        print(f'batch {len(calls)}: {len(suggestions)} suggestions, {elapsed} ms')
    OUT.write_text('\n'.join(json.dumps(row, ensure_ascii=False) for row in predictions) + '\n', encoding='utf-8')
    STATS.write_text(json.dumps({'provider': 'DeepSeek', 'model': llm.config()['model'],
        'dataset': str(DATA), 'claims': len(claims), 'calls': calls,
        'failed_calls': 0, 'api_key_written': False}, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'wrote {OUT} and {STATS}; key was not persisted')


if __name__ == '__main__':
    main()
