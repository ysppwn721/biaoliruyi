"""审计自建中文训练对 reranker_training_pairs.jsonl。

这份数据与推理任务同分布（中文结论 → 中文事实元数据），
比公开英文数据更适合微调。审计重点：
  1. 正负平衡与负例类型
  2. 训练/留出是否按文档组隔离（防泄漏）
  3. fact_text 字段是否完整（subject/metric/period 缺一即为弱信号）
  4. 负例是否真的是"难负例"（与正例只差一个字段）
  5. 同一 claim 的正负对是否成组
"""
import json
import collections
from pathlib import Path

D = Path(r'C:\Users\Administrator\Desktop\华北五省设计\答辩评测')
rows = [json.loads(l) for l in (D / 'reranker_training_pairs.jsonl').open(encoding='utf-8') if l.strip()]

print(f'行数: {len(rows)}')
print(f'唯一 claim: {len(set(r["claim_id"] for r in rows))}')
print(f'label: {dict(collections.Counter(r["label"] for r in rows))}')
print(f'negative_type: {dict(collections.Counter(r.get("negative_type") for r in rows))}')
print(f'split: {dict(collections.Counter(r.get("split") for r in rows))}')
print()


def fields(ft):
    d = {}
    for part in ft.split('；'):
        if '=' in part:
            k, v = part.split('=', 1)
            d[k.strip()] = v.strip()
    return d


# 1. split 是否按组隔离
grp_split = collections.defaultdict(set)
for r in rows:
    grp_split[r['group_id']].add(r['split'])
leak = {g: s for g, s in grp_split.items() if len(s) > 1}
print(f'[组内跨 split 泄漏] {len(leak)} 组')
for g, s in list(leak.items())[:5]:
    print(f'    {g} -> {sorted(s)}')

# 2. fact_text 字段完整性
incomplete = collections.Counter()
for r in rows:
    f = fields(r['fact_text'])
    for k in ('subject', 'metric', 'period', 'scope'):
        if not f.get(k):
            incomplete[k] += 1
print(f'\n[字段缺失] ' + ', '.join(f'{k}={v}' for k, v in incomplete.items()))

# 3. 负例与正例的差异字段（判断是否真难负例）
by_claim = collections.defaultdict(list)
for r in rows:
    by_claim[r['claim_id']].append(r)
diffs = collections.Counter()
for cid, items in by_claim.items():
    pos = [i for i in items if i['label'] == 1]
    negs = [i for i in items if i['label'] == 0]
    if not pos:
        continue
    pf = fields(pos[0]['fact_text'])
    for n in negs:
        nf = fields(n['fact_text'])
        changed = tuple(sorted(k for k in ('subject', 'metric', 'period', 'scope')
                               if pf.get(k) != nf.get(k)))
        diffs[changed] += 1
print(f'\n[负例与正例的差异字段分布]')
for k, v in diffs.most_common(10):
    print(f'    {k or "(无差异!)"}: {v}')

# 4. 每个 claim 的正负配比
sizes = collections.Counter(len(v) for v in by_claim.values())
print(f'\n[每个 claim 的 pair 数分布] {dict(sorted(sizes.items()))}')

pos_per = collections.Counter(sum(1 for i in v if i['label'] == 1) for v in by_claim.values())
print(f'[每个 claim 的正例数] {dict(sorted(pos_per.items()))}')

# 5. 同一 claim 的负例中，是否存在与正例 fact_id 相同的情况（错标）
bad = []
for cid, items in by_claim.items():
    pos_ids = {i['fact_id'] for i in items if i['label'] == 1}
    for i in items:
        if i['label'] == 0 and i['fact_id'] in pos_ids:
            bad.append((cid, i['fact_id']))
print(f'\n[同一事实既标正例又标负例] {len(bad)} 条')
for b in bad[:5]:
    print('   ', b)

# 6. 负例来源是否多为"接近但不同"的事实
neg_ids = collections.Counter(i['fact_id'] for i in rows if i['label'] == 0)
print(f'\n[负例事实 ID 复用 Top5] {neg_ids.most_common(5)}')
