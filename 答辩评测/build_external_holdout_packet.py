from __future__ import annotations
import csv, json
from pathlib import Path

ROOT=Path(__file__).resolve().parent
out=ROOT/'external_holdout_packet'; out.mkdir(exist_ok=True)
reports=[
 {'file':'002097_2023年年度报告全文更新后.pdf','company':'山河智能','url':'https://www.cninfo.com.cn/'},
 {'file':'002413_2023年年度报告更新后.pdf','company':'雷科防务','url':'https://www.cninfo.com.cn/'},
 {'file':'603839_安正时尚集团股份有限公司2023年年度报告更正后.pdf','company':'安正时尚','url':'https://www.cninfo.com.cn/'},
 {'file':'688152_麒麟信安2023年年度报告更正后.pdf','company':'麒麟信安','url':'https://www.cninfo.com.cn/'},
 {'file':'836263_2023年年度报告更正后.pdf','company':'中航泰达','url':'https://www.cninfo.com.cn/'},
]
manifest=[]
for item in reports:
 path=ROOT/'cn_reports'/item['file']
 manifest.append({**item,'local_path':str(path),'exists':path.exists(),'license_note':'公开披露年报；提交前核对来源条款'})
(out/'report_manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
fields=['sample_id','report_file','company','page','claim_text','fact_id_A','fact_text_A','label_A','fact_id_B','fact_text_B','label_B','adjudicated_label','note']
with (out/'annotation_template.csv').open('w',newline='',encoding='utf-8-sig') as stream:
    writer=csv.DictWriter(stream,fieldnames=fields); writer.writeheader()
    for i in range(1,31):
        report=reports[(i-1)%len(reports)]
        writer.writerow({'sample_id':f'ext-{i:03d}','report_file':report['file'],'company':report['company']})
(out/'README.md').write_text('''# 外部中文 holdout 复核包\n\n目的：从未参与训练的真实年报中人工抽取 30 条“正文论断—事实元数据”样本。\n\n每条样本由两位标注者独立填写 claim_text、page、候选事实、label_A/B；label=1 表示该事实是论断来源，0 表示不是。最后填写 adjudicated_label 和分歧说明。\n\n注意：本包只作为外部泛化验证，不得回填到训练集；PDF 仅作人工查看素材，提交包不应直接包含原始 PDF。\n''',encoding='utf-8')
print(out)
