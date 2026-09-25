"""对 280 条复核清单做程序化审计。

审计的是"来源是否唯一"这一判据本身是否成立，而不是重复引擎已有的结论：
  1. 引用的每个事实 ID 是否真的存在于该行 facts 中
  2. 同一 (主体, 指标, 期间, 统计口径) 是否在事实表中出现多次 —— 这才是"来源不唯一"
  3. 论断类型与引用个数是否自洽（增长率需 2 个、排名需完整比较集合）
  4. 文本中的期间/主体是否与所引事实一致
  5. 两个子智能体（candidate / consensus）分歧的行
  6. 应判 ambiguous 但被标成 ordinary 的行（漏判歧义）
"""
import csv
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(r'C:\Users\Administrator\Desktop\华北五省设计')
D = ROOT / '答辩评测'

rows = list(csv.DictReader((D / '双智能体标注复核清单.csv').open(encoding='utf-8-sig')))
print(f'清单行数: {len(rows)}\n')

# ---- 事实表：读取真实事实（用引擎自己的读取器，保证与运行时一致） ----
import sys
sys.path.insert(0, str(ROOT))
from zhilian.office import read_facts

xlsx = ROOT / '长文Word测试' / '配套数据_初始.xlsx'
facts = read_facts(xlsx, 'F')
fact_by_id = {f['id']: f for f in facts}
print(f'事实表: {len(facts)} 条')

# 关键：找出描述符重复的事实组 —— 重复即"来源不唯一"
buckets = defaultdict(list)
for f in facts:
    buckets[(f['subject'], f['metric'], f['period'], f['scope'])].append(f['id'])
dupes = {k: v for k, v in buckets.items() if len(v) > 1}
print(f'描述符完全重复的组: {len(dupes)}')
for k, v in dupes.items():
    print(f'   {k} -> {sorted(v)}')

# 按 (指标, 期间) 分组，用于判断某论断是否本质歧义
by_metric_period = defaultdict(list)
for f in facts:
    by_metric_period[(f['metric'], f['period'])].append(f)
print()
for k, v in sorted(by_metric_period.items()):
    if len(v) > 1:
        print(f'  同指标同期多口径 {k}: ' + ', '.join(f'{x["id"]}({x["subject"]}/{x["scope"]})' for x in v))

problems = defaultdict(list)
kinds = Counter()
actions = Counter()
cats = Counter()

for r in rows:
    cid = r['claim_id']
    kinds[r['kind']] += 1
    actions[r['gold_action']] += 1
    cats[r['category']] += 1
    cand = [x for x in (r['candidate_refs'] or '').split(',') if x]
    cons = [x for x in (r['consensus_refs'] or '').split(',') if x]
    text = r['claim_text']

    # 1. 引用是否存在
    for x in set(cand + cons):
        if x not in fact_by_id:
            problems['引用不存在的事实'].append((cid, x))

    # 2. 两个子智能体分歧
    if set(cand) != set(cons):
        problems['双子智能体分歧'].append((cid, r['kind'], r['candidate_refs'], r['consensus_refs'], text))

    # 3. 类型与引用数自洽
    refs = cons or cand
    if r['kind'] == 'growth' and len(refs) != 2:
        problems['增长率引用数不为2'].append((cid, refs, text))
    if r['kind'] == 'ranking' and len(refs) < 2:
        problems['排名引用不足2个'].append((cid, refs, text))
    if r['kind'] == 'quote' and len(refs) != 1:
        problems['数值引用非唯一来源'].append((cid, refs, text))

    # 4. 文本期间 与 所引事实期间 是否矛盾
    if '上期' in text and '本期' not in text:
        for x in refs:
            f = fact_by_id.get(x)
            if f and f['period'] == '本期':
                problems['期间疑似矛盾'].append((cid, text, x, f['period']))
    if '本期' in text and '上期' not in text:
        for x in refs:
            f = fact_by_id.get(x)
            if f and f['period'] == '上期':
                problems['期间疑似矛盾'].append((cid, text, x, f['period']))

    # 5. 漏判歧义：所引事实的 (指标,期间) 在事实表里存在多口径
    for x in refs:
        f = fact_by_id.get(x)
        if not f:
            continue
        same = by_metric_period[(f['metric'], f['period'])]
        if len(same) > 1:
            others = [y['id'] for y in same if y['id'] != x]
            # 只有当文本没有把口径说清楚时才算漏判
            if not any(y['scope'] in text or y['subject'] in text for y in same if y['id'] != x):
                problems['可能漏判歧义'].append((cid, f['metric'], f['period'], r['category'], text,
                                                 [y['id'] for y in same]))

print('\n' + '=' * 76)
print(f'论断类型: {dict(kinds)}')
print(f'gold_action: {dict(actions)}')
print(f'category: {dict(cats)}')
print('=' * 76)

for label in ['引用不存在的事实', '双子智能体分歧', '增长率引用数不为2', '排名引用不足2个',
              '数值引用非唯一来源', '期间疑似矛盾', '可能漏判歧义']:
    items = problems[label]
    print(f'\n[{label}] {len(items)} 条')
    for it in items[:12]:
        print('   ', it)
    if len(items) > 12:
        print(f'    ...另有 {len(items)-12} 条，详见输出的 CSV')
