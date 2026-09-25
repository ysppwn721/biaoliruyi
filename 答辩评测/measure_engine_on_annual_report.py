"""在真实年报上测量引擎识别率（改规则前 vs 改规则后的可比数字）。"""
import sys
import re
from pathlib import Path
import pdfplumber

sys.path.insert(0, r'C:\Users\Administrator\Desktop\华北五省设计')
from zhilian.engine import extract_claims

pdf = Path(sys.argv[1])
START, END = int(sys.argv[2]), int(sys.argv[3])

with pdfplumber.open(pdf) as doc:
    pages = [(i, doc.pages[i].extract_text() or '') for i in range(START, min(END, len(doc.pages)))]

all_text = '\n'.join(t for _, t in pages)
print(f'文件: {pdf.name}')
print(f'抽取页: {START+1}—{min(END, len(doc.pages))}   共 {len(all_text)} 字符')

# 客观分母：含数字的句子数（不依赖任何规则）
sentences = [s.strip() for s in re.split(r'[。；\n]', all_text) if s.strip()]
with_num = [s for s in sentences if re.search(r'\d', s)]
print(f'句子总数: {len(sentences)}   含数字句子: {len(with_num)}')
print('=' * 74)

# 逐句喂引擎，统计识别率
recognized = []
for s in with_num:
    claims = extract_claims({'file_id': 'F', 'location': ['p', 0], 'label': 't', 'text': s}, [])
    if claims:
        recognized.append((s, [c['kind'] for c in claims]))

print(f'\n引擎识别出论断的句子: {len(recognized)} / {len(with_num)}  '
      f'= {len(recognized)/len(with_num)*100:.1f}%')

kinds = {}
for _, ks in recognized:
    for k in ks:
        kinds[k] = kinds.get(k, 0) + 1
print(f'论断类型分布: {kinds}')

print(f'\n已识别样例（前 12 条）:')
seen = set()
for s, ks in recognized:
    key = s[:18]
    if key in seen:
        continue
    seen.add(key)
    print(f'  [{",".join(ks):16}] {s[:66]}')
    if len(seen) >= 12:
        break

# 未识别但明显含数值结论的（抽样，用于说明剩余缺口）
print(f'\n未识别但含明显数值结论的样例（前 8 条）:')
gap_pat = re.compile(r'(增长|下降|增加|减少|上升|占比|超过|低于|高于).{0,20}\d')
n = 0
for s in with_num:
    if any(s == r[0] for r in recognized):
        continue
    if gap_pat.search(s) and 12 < len(s) < 90:
        print(f'  · {s[:76]}')
        n += 1
        if n >= 8:
            break
