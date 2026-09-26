from __future__ import annotations
import json
import os
from collections import defaultdict
from pathlib import Path
import torch
from transformers import AutoModelForSequenceClassification, AutoTokenizer

ROOT = Path(__file__).resolve().parent
eval_file = Path(os.getenv('ZHILIAN_EVAL_FILE', str(ROOT / 'independent_synthetic_eval.jsonl')))
rows = [json.loads(line) for line in eval_file.open(encoding='utf-8') if line.strip()]
model_dir = Path(os.getenv('ZHILIAN_TRANSFORMER_MODEL', str(ROOT.parent / 'models' / 'zh_reranker_bert_ft')))
tok = AutoTokenizer.from_pretrained(model_dir)
model = AutoModelForSequenceClassification.from_pretrained(model_dir)
model.eval()
scores = []
with torch.no_grad():
    for start in range(0, len(rows), 16):
        batch = rows[start:start + 16]
        x = tok([r['claim_text'] for r in batch], [r['fact_text'] for r in batch],
                padding=True, truncation=True, max_length=128, return_tensors='pt')
        scores.extend(model(**x).logits[:, 1].tolist())
groups = defaultdict(list)
for row, score in zip(rows, scores):
    groups[row['claim_id']].append((score, int(row['label'])))
top1 = sum(max(items)[1] == 1 for items in groups.values()) / len(groups)
result = {'programmatic': 'external_programmatic_holdout' in eval_file.name,
          'synthetic': 'external_programmatic_holdout' not in eval_file.name,
          'file': str(eval_file), 'groups': len({r['group_id'] for r in rows}), 'claims': len(groups), 'rows': len(rows),
          'top1_accuracy': round(top1, 6), 'error_association_rate': round(1 - top1, 6)}
(ROOT / (eval_file.stem + '_bert_metrics.json')).write_text(
    json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps(result, ensure_ascii=False))
