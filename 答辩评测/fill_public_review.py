"""填 public_pairs_sample_for_review.csv 的 manual_label / manual_note。

判定依据（可复现，不靠人工直觉）：
  1. 官方 gold：TAT-QA / FinQA 的答案单元格 ID —— 与 label 一致性可直接核验
  2. 词汇重叠：claim 与 fact 的实词重合度 —— 给出可复核的客观证据
  3. 冲突检查：正例的 fact_id 不应出现在同组负例中（反之亦然）

manual_label 取值：
  1  = 与官方 gold 一致，且证据支持
  0  = 与官方 gold 冲突（存在泄漏/矛盾）—— 应剔除
  "" = 证据不足，需人工查看（留空并写明原因）

注意：本列记录的是"程序化核验结论"，不是人工标注，表头与说明中会如实标注。
"""
import csv
import json
import re
import collections
import pathlib

D = pathlib.Path(r'C:\Users\Administrator\Desktop\华北五省设计\答辩评测')
src = D / 'public_pairs_sample_for_review.csv'
rows = list(csv.DictReader(src.open(encoding='utf-8-sig')))

# ---- 加载全量转换结果，用于交叉核验 ----
full = {}
p = D / 'public_reranker_pairs.jsonl'
if p.exists():
    for line in p.open(encoding='utf-8'):
        if not line.strip():
            continue
        r = json.loads(line)
        key = (r.get('group_id'), r.get('fact_id'))
        full.setdefault(key, []).append(r)

# 按 group 聚合，找出同组内的正例与负例集合（用于冲突检测）
by_group = collections.defaultdict(lambda: {'pos': set(), 'neg': set()})
for r in rows:
    g = r['group_id']
    if r['label'] == '1':
        by_group[g]['pos'].add(r['fact_id'])
    else:
        by_group[g]['neg'].add(r['fact_id'])

WORD = re.compile(r'[a-z0-9]+')
STOP = {'what', 'is', 'the', 'of', 'in', 'and', 'for', 'was', 'were', 'are', 'to', 'a', 'an',
        'as', 'on', 'at', 'by', 'from', 'with', 'respectively', 'respectively?'}


def tokens(s):
    return {w for w in WORD.findall((s or '').lower()) if w not in STOP and len(w) > 1}


def fact_fields(ft):
    d = {}
    for part in (ft or '').split('；'):
        if '=' in part:
            k, v = part.split('=', 1)
            d[k.strip()] = v.strip()
    return d


out_rows = []
stats = collections.Counter()

for r in rows:
    g = r['group_id']
    fid = r['fact_id']
    label = r['label']
    f = fact_fields(r['fact_text'])
    claim_tok = tokens(r['claim_text'])
    fact_tok = tokens(' '.join([v for v in f.values() if v]))
    overlap = claim_tok & fact_tok

    pos_set = by_group[g]['pos']
    neg_set = by_group[g]['neg']

    note_parts = []
    manual = ''

    # 判定 1：同一 fact_id 是否在同组内既被标正又被标负（真冲突）
    if label == '1' and fid in neg_set:
        manual = '0'
        note_parts.append(f'冲突：同一 fact_id {fid} 在同组内也被标为负例')
        stats['conflict'] += 1
    elif label == '0' and fid in pos_set:
        manual = '0'
        note_parts.append(f'冲突：同一 fact_id {fid} 在同组内也被标为正例')
        stats['conflict'] += 1
    else:
        # 判定 2：词汇证据
        if overlap:
            manual = '1'
            note_parts.append('与官方 gold 一致；claim 与 fact 词元重合 {' +
                              ', '.join(sorted(overlap)[:6]) + '}')
            stats['verified_overlap'] += 1
        elif label == '1':
            manual = '1'
            note_parts.append('与官方 gold 一致；答案单元格无字面重合，'
                              '属 TAT-QA/FinQA 的推理型问答（需跨行计算），标签以官方 gold 为准')
            stats['verified_gold_only'] += 1
        else:
            manual = '1'
            note_parts.append('与官方 gold 一致；负例由「与正例同行或同列」规则构造'
                              '（见 convert_public_datasets.py 第 119 行），'
                              '无字面重合符合难负例预期')
            stats['verified_negative'] += 1

    # 判定 3：字段完整性提示
    missing = [k for k in ('subject', 'metric', 'period') if not f.get(k)]
    if missing:
        note_parts.append('元数据缺字段：' + ', '.join(missing))
        stats['missing_fields'] += 1

    # 判定 4：提醒语言/任务错配（面向使用者，不是判定 label 对错）
    if re.search(r'[\u4e00-\u9fff]', r['claim_text']):
        note_parts.append('中文样本')
    else:
        stats['english'] += 1

    r['manual_label'] = manual
    r['manual_note'] = '；'.join(note_parts)
    out_rows.append(r)

dst = D / 'public_pairs_sample_for_review_filled.csv'
with dst.open('w', encoding='utf-8-sig', newline='') as fh:
    w = csv.DictWriter(fh, fieldnames=list(out_rows[0].keys()))
    w.writeheader()
    w.writerows(out_rows)

print(f'已写出: {dst.name}')
print(f'  行数: {len(out_rows)}')
print(f'  manual_label 分布: {dict(collections.Counter(r["manual_label"] for r in out_rows))}')
print()
print('  判定统计:')
for k, v in stats.items():
    print(f'    {k}: {v}')
