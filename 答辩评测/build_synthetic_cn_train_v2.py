"""Create additional synthetic Chinese training groups.

This data is clearly marked synthetic and is kept separate from all human
evaluation files and the previous independent generalization check.
"""
from __future__ import annotations
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OUT = ROOT / 'cn_synthetic_v2'
subjects = ['华北能源','东港物流','云岭制造','中原水务','滨海材料','西部交通','江南农业','海河环保','北辰医药','长江电商']
metrics = [('营业收入','万元'),('研发投入','万元'),('产量','吨'),('订单量','万单'),('处理量','万吨'),('客运量','万人次'),('库存量','吨'),('项目数','项'),('发电量','万千瓦时')]
scopes = ['合并口径','主营业务','区域合计','年度经营','核心业务','全口径']
templates = [
    '{subject}在2025年的{metric}为{amount}{unit}。',
    '报告期内，{subject}{metric}达到{amount}{unit}。',
    '2025年{subject}实现{metric}{amount}{unit}。',
    '{subject}的{metric}较2024年发生变化。',
    '从年度数据看，{subject}2025年{metric}为{amount}{unit}。',
    '{subject}在{scope}下的{metric}达到{amount}{unit}。',
]

def fact(fid, subject, metric, period, unit, scope):
    return {'id': fid, 'subject': subject, 'metric': metric, 'period': period, 'unit': unit, 'scope': scope}

def fact_text(f):
    return '；'.join(f'{k}={f[k]}' for k in ('subject','metric','period','unit','scope'))

rows=[]
for gi in range(1, 61):
    gid=f'synth-v2-{gi:03d}'
    subject=subjects[(gi-1)%len(subjects)] + f'{gi:02d}号'
    metric, unit=metrics[(gi*3)%len(metrics)]
    scope=scopes[(gi*2)%len(scopes)]
    amount=100 + gi*7
    facts=[
        fact('current',subject,metric,'2025年',unit,scope),
        fact('previous',subject,metric,'2024年',unit,scope),
        fact('other_metric',subject,metrics[(gi*3+1)%len(metrics)][0], '2025年', metrics[(gi*3+1)%len(metrics)][1],scope),
        fact('other_subject','行业合计',metric,'2025年',unit,scope),
        fact('other_unit',subject,metric,'2025年','亿元' if unit!='亿元' else '万元',scope),
        fact('other_scope',subject,metric,'2025年',unit,'分部口径'),
    ]
    claims=[
        (templates[gi%len(templates)].format(subject=subject,metric=metric,amount=amount,unit=unit,scope=scope), {'current'}),
        (templates[(gi+1)%len(templates)].format(subject=subject,metric=metric,amount=amount,unit=unit,scope=scope), {'current'}),
        (f'{subject}2025年的{metric}高于上一年度。', {'current','previous'}),
        (f'{subject}在2025年完成了{metric}指标。', {'current'}),
        (f'{subject}的{metric}统计口径为{scope}。', {'current'}),
        (f'2025年{subject}{metric}使用的单位是{unit}。', {'current'}),
    ]
    split='dev' if gi>48 else 'train'
    for ci,(claim,gold) in enumerate(claims,1):
        cid=f'{gid}-c{ci:02d}'
        for f in facts:
            rows.append({'claim_id':cid,'claim_text':claim,'fact_id':f['id'],'fact_text':fact_text(f),
                         'group_id':gid,'label':int(f['id'] in gold),
                         'negative_type':'positive' if f['id'] in gold else 'hard_negative',
                         'split':split,'synthetic':True,'source':'controlled_fact_expansion_v2'})
OUT.mkdir(exist_ok=True)
for split in ('train','dev'):
    with (OUT/f'{split}.jsonl').open('w',encoding='utf-8') as stream:
        for row in rows:
            if row['split']==split: stream.write(json.dumps(row,ensure_ascii=False,sort_keys=True)+'\n')
manifest={'train_rows':sum(r['split']=='train' for r in rows),'dev_rows':sum(r['split']=='dev' for r in rows),
          'train_groups':48,'dev_groups':12,'synthetic':True,'note':'not human labeled; never use as final industry evaluation'}
(OUT/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(manifest,ensure_ascii=False))
