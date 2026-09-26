import json
from pathlib import Path

OUT=Path(__file__).resolve().parent/'stress_eval.jsonl'
specs=[('极地冷链','冷链周转量','万吨公里','全国口径',812),('星河平台','用户留存率','%','活跃用户',68),('青原矿业','矿石处理量','万吨','生产基地',934),('海岳文旅','游客满意度','分','游客调查',91),('晨曦通信','基站建设数','座','网络工程',276),('绿洲水厂','再生水利用率','%','循环水业务',74),('北斗航空','航班准点率','%','国内航线',87),('远景教育','培训人次','万人次','职业教育',53)]
def ft(f): return '；'.join(f'{k}={f[k]}' for k in ('subject','metric','period','unit','scope'))
rows=[]
for i,(s,m,u,sc,a) in enumerate(specs,1):
    gid=f'stress-{i:02d}'
    facts=[
      {'id':'target','subject':s,'metric':m,'period':'2025年度','unit':u,'scope':sc},
      {'id':'prev','subject':s,'metric':m,'period':'2024年度','unit':u,'scope':sc},
      {'id':'metric2','subject':s,'metric':'运营成本','period':'2025年度','unit':'万元','scope':sc},
      {'id':'subject2','subject':'全行业','metric':m,'period':'2025年度','unit':u,'scope':sc},
      {'id':'scope2','subject':s,'metric':m,'period':'2025年度','unit':u,'scope':'试点口径'},
      {'id':'unit2','subject':s,'metric':m,'period':'2025年度','unit':'亿元' if u!='亿元' else '万元','scope':sc},]
    claims=[(f'截至2025年度，{s}的{m}记录为{a}{u}。',{'target'}),(f'从报告期口径看，{s}在{sc}下{m}达到{a}{u}。',{'target'}),(f'{s}{m}较上一年度发生变化。',{'target','prev'}),(f'{s}发布的2025年度{m}指标为{a}{u}。',{'target'}),(f'该单位的{m}采用{sc}统计。',{'target'})]
    for ci,(claim,gold) in enumerate(claims,1):
      for f in facts:
        rows.append({'claim_id':f'{gid}-c{ci:02d}','claim_text':claim,'fact_id':f['id'],'fact_text':ft(f),'group_id':gid,'label':int(f['id'] in gold),'synthetic':True})
with OUT.open('w',encoding='utf-8') as out:
  for r in rows: out.write(json.dumps(r,ensure_ascii=False)+'\n')
print(json.dumps({'rows':len(rows),'claims':len({r['claim_id'] for r in rows}),'groups':len(specs)},ensure_ascii=False))
