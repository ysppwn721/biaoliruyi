from pathlib import Path
import json

ROOT=Path(__file__).resolve().parent
out=ROOT/'cn_finetune_v2'; out.mkdir(exist_ok=True)
sources={
 'train':[ROOT/'cn_finetune'/'train.jsonl',ROOT/'cn_synthetic_v2'/'train.jsonl'],
 'dev':[ROOT/'cn_synthetic_v2'/'dev.jsonl'],
 'final_test':[ROOT/'cn_finetune'/'final_test.jsonl'],
}
groups={}
for split,paths in sources.items():
    rows=[]
    for path in paths:
        rows.extend(json.loads(line) for line in path.open(encoding='utf-8') if line.strip())
    with (out/f'{split}.jsonl').open('w',encoding='utf-8') as stream:
        for row in rows: stream.write(json.dumps(row,ensure_ascii=False,sort_keys=True)+'\n')
    groups[split]=sorted({row['group_id'] for row in rows})
assert not (set(groups['train']) & set(groups['dev']))
assert not (set(groups['train']) & set(groups['final_test']))
assert not (set(groups['dev']) & set(groups['final_test']))
manifest={'rows':{split:sum(1 for _ in (out/f'{split}.jsonl').open(encoding='utf-8')) for split in sources},'groups':{k:len(v) for k,v in groups.items()},'note':'v2 adds controlled synthetic Chinese groups; final_test remains original frozen test'}
(out/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(manifest,ensure_ascii=False))
