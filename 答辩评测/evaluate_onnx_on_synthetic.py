from __future__ import annotations
import json, os, sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parent))
os.environ['ZHILIAN_LOCAL_RERANKER_ENABLED'] = '1'
os.environ['ZHILIAN_LOCAL_RERANKER_PATH'] = str(ROOT.parent / 'models' / 'bge-reranker-v2-m3-onnx-int8')
from zhilian.reranker import score_pairs

eval_file = Path(os.getenv('ZHILIAN_EVAL_FILE', str(ROOT / 'independent_synthetic_eval.jsonl')))
rows = [json.loads(line) for line in eval_file.open(encoding='utf-8') if line.strip()]
by_claim = defaultdict(list)
for row in rows:
    fields = {}
    for part in row['fact_text'].split('；'):
        k, v = part.split('=', 1); fields[k] = v
    fields['id'] = row['fact_id']
    by_claim[row['claim_id']].append((row, fields))
correct = 0
for claim_id, items in by_claim.items():
    claim = items[0][0]['claim_text']
    scored = score_pairs(claim, [fact for _, fact in items])
    gold = {row['fact_id'] for row, _ in items if row['label'] == 1}
    if scored and scored[0]['fact_id'] in gold:
        correct += 1
result = {'model': 'bge-reranker-v2-m3-onnx-int8', 'programmatic': True, 'file': str(eval_file), 'claims': len(by_claim),
          'top1_accuracy': round(correct / len(by_claim), 6),
          'error_association_rate': round(1 - correct / len(by_claim), 6)}
(ROOT / (eval_file.stem + '_bge_metrics.json')).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps(result, ensure_ascii=False))
