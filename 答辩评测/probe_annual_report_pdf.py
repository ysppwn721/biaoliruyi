"""实测中文年报 PDF 的文本与表格抽取可行性。

决定性问题：
  1. PDF 是否含文本层（否则要 OCR）
  2. 表格能否被结构性抽取（而非一串乱码）
  3. 抽取出的数值结论是否可用引擎识别
"""
import sys
import time
import re
from pathlib import Path

import pdfplumber

pdf = Path(sys.argv[1])
print(f'文件: {pdf.name}  ({pdf.stat().st_size/1024/1024:.2f} MB)')
print('=' * 74)

t0 = time.perf_counter()
with pdfplumber.open(pdf) as doc:
    n_pages = len(doc.pages)
    print(f'页数: {n_pages}   打开耗时: {time.perf_counter()-t0:.2f}s')

    # 1. 文本层检测（抽样前 5 页 + 中间 5 页）
    probes = list(range(min(5, n_pages))) + list(range(n_pages//2, min(n_pages//2+5, n_pages)))
    char_counts = []
    for i in probes:
        t = doc.pages[i].extract_text() or ''
        char_counts.append(len(t))
    total_chars = sum(char_counts)
    print(f'\n[1] 文本层检测（抽样 {len(probes)} 页）')
    print(f'    抽样页字符数: {char_counts}')
    print(f'    合计 {total_chars} 字符 -> ' +
          ('✅ 有文本层，无需 OCR' if total_chars > 500 else '❌ 疑似扫描件，需 OCR'))

    # 2. 找含关键财务词的页（定位"主要会计数据"表）
    print(f'\n[2] 定位财务内容（前 60 页）')
    hits = []
    for i in range(min(60, n_pages)):
        t = doc.pages[i].extract_text() or ''
        score = sum(1 for k in ('营业收入', '归属于上市公司股东', '总资产', '经营活动产生的现金流量') if k in t)
        if score >= 2:
            hits.append((i, score, len(t)))
    print(f'    命中页: {[(p, f"score={s}") for p, s, _ in hits[:10]]}')

    if not hits:
        print('    未找到财务关键页，扩大扫描范围')
        for i in range(min(120, n_pages)):
            t = doc.pages[i].extract_text() or ''
            if '营业收入' in t and '总资产' in t:
                hits.append((i, 2, len(t)))
        print(f'    扩大后命中页: {[p for p, _, _ in hits[:10]]}')

    # 3. 表格抽取实测
    print(f'\n[3] 表格抽取实测（对命中页试抽）')
    ok_tables = 0
    for page_no, _, _ in hits[:4]:
        page = doc.pages[page_no]
        tables = page.extract_tables()
        print(f'    第 {page_no+1} 页: 抽出 {len(tables)} 个表')
        for ti, tb in enumerate(tables[:2]):
            rows = len(tb)
            cols = len(tb[0]) if tb else 0
            nonempty = sum(1 for r in tb for c in r if c and str(c).strip())
            print(f'      表{ti+1}: {rows} 行 × {cols} 列，非空单元格 {nonempty}')
            # 打印前 3 行看结构是否可用
            for r in tb[:3]:
                cells = [(str(c).replace('\n', ' ')[:18] if c else '') for c in r[:5]]
                print(f'        | {" | ".join(cells)}')
            if nonempty > 10:
                ok_tables += 1
    print(f'    可用表格数: {ok_tables}')

    # 4. 文本中的数值结论（交给引擎识别的原料）
    print(f'\n[4] 数值结论句抽样（用于构造论断）')
    pat = re.compile(r'[^。；\n]{0,30}(较上年|同比|增长|下降)[^。；\n]{0,25}[。；]?')
    samples = []
    for i in probes + [p for p, _, _ in hits[:3]]:
        if i >= n_pages:
            continue
        t = doc.pages[i].extract_text() or ''
        for m in pat.finditer(t):
            s = m.group().strip()
            if 8 < len(s) < 60:
                samples.append(s)
    for s in samples[:8]:
        print(f'    · {s}')
    print(f'    合计命中增长率表述 {len(samples)} 条（仅抽样页）')

print('=' * 74)
print(f'结论: ' +
      ('文本与表格均可结构化抽取，可行' if total_chars > 500 and ok_tables > 0
       else '需进一步验证或改用 OCR 路线'))
