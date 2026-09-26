"""Extract a small programmatic holdout from text-layer annual reports.

PyMuPDF preserves the Chinese font mapping in these PDFs, while pdfplumber
returned mojibake. Labels are derived from adjacent report table values and
are therefore programmatic, not human annotations.
"""
from __future__ import annotations
import json,re
from pathlib import Path
import pymupdf

ROOT=Path(__file__).resolve().parent
reports=[('002097_2023年年度报告全文更新后.pdf','山河智能'),('002413_2023年年度报告更新后.pdf','雷科防务'),('603839_安正时尚集团股份有限公司2023年年度报告更正后.pdf','安正时尚'),('688152_麒麟信安2023年年度报告更正后.pdf','麒麟信安'),('836263_2023年年度报告更正后.pdf','中航泰达')]
metric_terms=['营业收入','归属于上市公司股东的净利润','经营活动产生的现金流量净额','基本每股收益','总资产','归属于上市公司股东的净资产','研发费用','销售费用','管理费用','资产总计','负债合计']
num=re.compile(r'^[-−]?[\d,]+(?:\.\d+)?%?$')
def clean(s): return re.sub(r'\s+','',s or '')
def parse(pdf,company):
    doc=pymupdf.open(pdf); rows=[]
    for page_no,page in enumerate(doc,1):
        lines=[clean(x) for x in page.get_text().splitlines() if clean(x)]
        for i,line in enumerate(lines):
            metric=next((m for m in metric_terms if m in line),None)
            if not metric: continue
            vals=[]
            for x in lines[i+1:i+5]:
                if num.fullmatch(x.replace('−','-')): vals.append(x.replace('−','-'))
            if len(vals)<2: continue
            unit='%' if '率' in metric or '收益率' in metric else ('元/股' if '每股' in metric else '元')
            current,prior=vals[:2]; change=next((v for v in vals[2:] if v.endswith('%')),None)
            rows.append({'company':company,'metric':metric,'unit':unit,'current':current,'prior':prior,'change':change,'page':page_no})
    # Keep first occurrence per metric, avoiding repeated note tables.
    seen=set(); out=[]
    for r in rows:
        if r['metric'] in seen: continue
        seen.add(r['metric']); out.append(r)
    return out
rows=[]
for fname,company in reports:
    facts=parse(ROOT/'cn_reports'/fname,company)
    gid='external-'+company
    for j,r in enumerate(facts[:6],1):
        current={'id':f'{gid}-m{j}-current','subject':company,'metric':r['metric'],'period':'2023年','unit':r['unit'],'scope':'合并口径'}
        prior={'id':f'{gid}-m{j}-prior','subject':company,'metric':r['metric'],'period':'2022年','unit':r['unit'],'scope':'合并口径'}
        other={'id':f'{gid}-m{j}-wrongperiod','subject':company,'metric':r['metric'],'period':'2021年','unit':r['unit'],'scope':'合并口径'}
        facts_text=lambda f:'；'.join(f'{k}={f[k]}' for k in ('subject','metric','period','unit','scope'))
        claims=[(f'{company}2023年{r["metric"]}为{r["current"]}{r["unit"]}',[current['id']]),(f'{company}2023年{r["metric"]}较上年变化{r["change"] or ""}',[current['id'],prior['id']])]
        for ci,(claim,gold) in enumerate(claims,1):
            for f in (current,prior,other):
                rows.append({'claim_id':f'{gid}-m{j}-c{ci}','claim_text':claim,'fact_id':f['id'],'fact_text':facts_text(f),'group_id':gid,'label':int(f['id'] in gold),'negative_type':'positive' if f['id'] in gold else 'hard_negative','source_file':fname,'source_page':r['page'],'programmatic':True})
out=ROOT/'external_programmatic_holdout.jsonl'
with out.open('w',encoding='utf-8') as stream:
    for row in rows: stream.write(json.dumps(row,ensure_ascii=False)+'\n')
(ROOT/'external_programmatic_holdout_stats.json').write_text(json.dumps({'rows':len(rows),'claims':len({r['claim_id'] for r in rows}),'groups':len({r['group_id'] for r in rows}),'reports':len(reports),'programmatic':True},ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({'rows':len(rows),'claims':len({r['claim_id'] for r in rows}),'groups':len({r['group_id'] for r in rows})},ensure_ascii=False))
