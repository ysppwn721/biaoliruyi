"""Build a separate synthetic Chinese generalization check.

This is explicitly marked synthetic. It must not be presented as a human or
industry evaluation set; it only checks whether the trained model handles new
subjects, metrics, periods, units and scopes outside the training groups.
"""
from __future__ import annotations
import json
from pathlib import Path

OUT = Path(__file__).resolve().parent / 'independent_synthetic_eval.jsonl'
groups = [
    ('独立组%02d' % i, subject, metric, unit, scope, amount)
    for i, (subject, metric, unit, scope, amount) in enumerate([
        ('北辰能源', '发电量', '万千瓦时', '华北区域', 318),
        ('江城物流', '货运量', '万吨', '年度经营', 427),
        ('云岭制造', '研发投入', '万元', '合并口径', 860),
        ('滨海港口', '吞吐量', '万吨', '港区合计', 512),
        ('中原水务', '供水量', '万立方米', '城市供水', 276),
        ('西部交通', '客运量', '万人次', '全路网', 645),
        ('华东材料', '产量', '吨', '主营产品', 391),
        ('南方农业', '播种面积', '万亩', '粮食作物', 228),
        ('北方医药', '研发项目数', '项', '创新药业务', 47),
        ('海河环保', '处理量', '万吨', '污水处理', 189),
        ('长江电商', '订单量', '万单', '平台业务', 733),
        ('天山旅游', '接待人数', '万人次', '景区合计', 154),
    ], start=1)]

def fact(fid, subject, metric, period, unit, scope):
    return {'id': fid, 'subject': subject, 'metric': metric, 'period': period,
            'unit': unit, 'scope': scope}

def ft(f):
    return '；'.join(f'{k}={f[k]}' for k in ('subject','metric','period','unit','scope'))

rows = []
for idx, (gid, subject, metric, unit, scope, amount) in enumerate(groups, 1):
    facts = [
        fact('target', subject, metric, '2025年', unit, scope),
        fact('prev', subject, metric, '2024年', unit, scope),
        fact('other_metric', subject, '成本', '2025年', '万元', scope),
        fact('other_subject', '区域合计', metric, '2025年', unit, scope),
        fact('other_unit', subject, metric, '2025年', '亿元' if unit != '亿元' else '万元', scope),
        fact('other_scope', subject, metric, '2025年', unit, '分部口径'),
    ]
    claims = [
        (f'{subject}2025年{metric}为{amount}{unit}', {'target'}),
        (f'{subject}2025年{metric}达到{amount}{unit}', {'target'}),
        (f'{subject}2025年{metric}较2024年有所变化', {'target','prev'}),
        (f'2025年{subject}的{metric}为{amount}{unit}', {'target'}),
        (f'{subject}在2025年完成了{metric}指标', {'target'}),
    ]
    for ci, (claim, gold) in enumerate(claims, 1):
        cid = f'{gid}-c{ci:02d}'
        for f in facts:
            rows.append({'claim_id': cid, 'claim_text': claim, 'fact_id': f['id'],
                         'fact_text': ft(f), 'group_id': gid,
                         'label': int(f['id'] in gold),
                         'negative_type': 'positive' if f['id'] in gold else 'hard_negative',
                         'split': 'synthetic_eval', 'synthetic': True})
with OUT.open('w', encoding='utf-8') as stream:
    for row in rows:
        stream.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + '\n')
print(json.dumps({'rows': len(rows), 'claims': len({r['claim_id'] for r in rows}),
                  'groups': len(groups), 'output': str(OUT), 'synthetic': True}, ensure_ascii=False))
