"""把年报 PDF 转成中文训练对。

核心思路：**年报表格自带标签，不需要人工标注。**
  表格同时给出「本期数 / 上期数 / 变动比例（%）」，因此：
    - 事实（fact）     = 表格行 × 期间，数值与单位直接可读
    - 数值结论（claim）= 叙述文字中的句子
    - 引擎算出的增长率 可与表格「变动比例」列**交叉校验**
  三者相互印证，即可自动生成"论断 → 事实"的正例；错期间/错指标/错口径的
  同一表格事实即为难负例。

输出：与 reranker_training_pairs.jsonl 同构的 JSONL
  {"claim_id","claim_text","fact_id","fact_text","group_id","label","negative_type","split"}
"""
import argparse
import json
import re
from pathlib import Path

import pdfplumber

# 财务表格常见行标签（主体/指标）
METRIC_HINTS = ('营业收入', '营业成本', '净利润', '利润总额', '资产总计', '负债合计',
                '应收账款', '存货', '销售费用', '管理费用', '研发费用', '货币资金',
                '经营活动产生的现金流量净额', '基本每股收益', '加权平均净资产收益率',
                '营业总收入', '税金及附加', '财务费用', '预付款项', '固定资产')
# 期间列头
PERIOD_CURRENT = ('本期数', '本期金额', '本期发生额', '期末数', '期末余额', '本报告期')
PERIOD_PRIOR = ('上年同期数', '上期数', '上期金额', '上年同期', '期初数', '期初余额')
NUM_RE = re.compile(r'^-?[\d,]+(?:\.\d+)?$')


# 期间列头：真实年报用「本期数/上年同期数」，也用「2022年/2021年」「第一季度」等
PERIOD_CURRENT_PAT = re.compile(r'本期|本报告期|期末|20\d{2}\s*年(?!度调整)|第[一二三四]季度|本年度')
PERIOD_PRIOR_PAT = re.compile(r'上期|上年同期|上年|期初|上年度|去年')
# 重复口径列（调整后/调整前）会导致同一指标出现多个值，必须跳过
DUP_SCOPE_PAT = re.compile(r'调整[后前]|重述[后前]|追溯调整')
CHANGE_PAT = re.compile(r'变动|增减|同比')


def clean(cell):
    return re.sub(r'\s+', '', str(cell or '')).strip()


def to_num(text):
    t = clean(text).replace(',', '')
    m = re.fullmatch(r'-?\d+(?:\.\d+)?', t)
    if not m:
        return None
    try:
        return float(t)
    except ValueError:
        return None


def classify_columns(header_rows):
    """从表头判断本期列、上期列、变动比例列。

    真实年报表头形态多样：单行「本期数|上年同期数|变动比例」、
    「2022年|2021年|本期比上年同期增减」、以及带「调整后/调整前」子行的多行表头。
    重复口径列（调整后/调整前）必须跳过，否则同一指标会产出多个互相矛盾的事实。
    """
    width = max((len(r) for r in header_rows), default=0)
    joined = [''.join(clean(c) for r in header_rows for c in (r[i] if i < len(r) else '') or '')
              for i in range(width)]
    cur = prior = chg = None
    for i, text in enumerate(joined):
        if not text or DUP_SCOPE_PAT.search(text):
            continue
        if chg is None and CHANGE_PAT.search(text):
            chg = i
            continue
        if cur is None and PERIOD_CURRENT_PAT.search(text):
            cur = i
        elif prior is None and PERIOD_PRIOR_PAT.search(text):
            prior = i
    # 表头没写期间时，退化为「按顺序取前两个数值列」
    if cur is None or prior is None:
        numeric_cols = []
        for i in range(1, width):
            for r in header_rows:
                if i < len(r) and to_num(r[i]) is not None:
                    numeric_cols.append(i)
                    break
        if len(numeric_cols) < 2:
            return None, None, None
        # 有变动列的说明这是指标对比表，取前两列
        if chg is not None:
            cand = [c for c in numeric_cols if c != chg]
        else:
            cand = numeric_cols
        if len(cand) < 2:
            return None, None, None
        cur, prior = (cur if cur is not None else cand[0]), (prior if prior is not None else cand[1])
    return cur, prior, chg


def facts_from_table(rows, group_id):
    """从一张表抽出事实。返回 (facts, relations)。"""
    if len(rows) < 3:
        return [], []
    # 表头可能占 1—3 行
    for hdr_n in (1, 2, 3):
        cur, prior, chg = classify_columns(rows[:hdr_n])
        if cur is not None and prior is not None:
            break
    else:
        return [], []

    facts, relations = [], []
    for rno, row in enumerate(rows[hdr_n:], 1):
        if not row:
            continue
        label = clean(row[0]) if row else ''
        if not label or len(label) > 30:
            continue
        # 行标签需命中财务指标词，避免把说明行当数据
        if not any(k in label for k in METRIC_HINTS):
            continue
        cur_v = to_num(row[cur]) if cur < len(row) else None
        pri_v = to_num(row[prior]) if prior < len(row) else None
        chg_v = to_num(row[chg]) if (chg is not None and chg < len(row)) else None
        if cur_v is None or pri_v is None:
            continue

        fid_cur = f'{group_id}_r{rno}c{cur}'
        fid_pri = f'{group_id}_r{rno}c{prior}'
        common = dict(metric=label, subject='公司', unit='元', scope=group_id)
        facts.append({'id': fid_cur, 'period': '本期', 'value': cur_v, **common})
        facts.append({'id': fid_pri, 'period': '上期', 'value': pri_v, **common})
        # 表格自报的变动比例，用于交叉校验
        relations.append({'metric': label, 'current': fid_cur, 'prior': fid_pri,
                          'reported_change': chg_v})
    return facts, relations


def facts_to_text(f):
    return (f"subject={f['subject']}；metric={f['metric']}；period={f['period']}；"
            f"unit={f['unit']}；scope={f['scope']}")


def build_pairs_for_report(pdf_path, out_group, max_pairs):
    """处理一份年报，产出训练对。"""
    with pdfplumber.open(pdf_path) as doc:
        pages = len(doc.pages)
        # 1. 抽表格与正文
        all_facts, all_relations, narrative = [], [], []
        for i in range(min(pages, 160)):
            page = doc.pages[i]
            text = page.extract_text() or ''
            if text:
                narrative.append(text)
            # 只在前 60 页找主要财务表（后面多为附注）
            if i < 60:
                for tb in (page.extract_tables() or []):
                    fs, rs = facts_from_table(tb, out_group)
                    all_facts.extend(fs)
                    all_relations.extend(rs)

    if len(all_facts) < 6:
        return [], {'reason': '可抽取事实不足', 'facts': len(all_facts)}

    # 去重（同一指标可能多处出现，保留首个）
    seen, facts = set(), []
    for f in all_facts:
        key = (f['metric'], f['period'])
        if key in seen:
            continue
        seen.add(key)
        facts.append(f)

    by_metric = {}
    for f in facts:
        by_metric.setdefault(f['metric'], {})[f['period']] = f

    text = '\n'.join(narrative)
    sentences = [s.strip() for s in re.split(r'[。；\n]', text) if s.strip()]

    pairs = []
    for rel in all_relations:
        metric = rel['metric']
        cur, pri = by_metric.get(metric, {}).get('本期'), by_metric.get(metric, {}).get('上期')
        if not cur or not pri or pri['value'] == 0:
            continue
        # 2. 引擎的增长率（确定性计算，作为真值）
        growth = (cur['value'] - pri['value']) / abs(pri['value']) * 100
        # 3. 与表格自报值交叉校验，偏差过大则丢弃该表
        reported = rel.get('reported_change')
        if reported is not None and abs(growth - reported) > 0.5:
            continue
        # 4. 在正文中找提到该指标且含百分比的句子作为 claim 文本
        hit = None
        for s in sentences:
            if metric in s and '%' in s and 8 < len(s) < 80:
                hit = s
                break
        if not hit:
            hit = f'{metric}较上期增长{growth:.2f}%'   # 无对应原句时用规格化模板

        gid = f'{out_group}:{metric}'
        base = {'group_id': gid, 'claim_text': hit}
        pairs.append({**base, 'fact_id': cur['id'], 'fact_text': facts_to_text(cur),
                      'label': 1, 'negative_type': 'positive'})
        pairs.append({**base, 'fact_id': pri['id'], 'fact_text': facts_to_text(pri),
                      'label': 1, 'negative_type': 'positive'})
        # 难负例：同一张表里换个指标
        for other, periods in by_metric.items():
            if other == metric or '本期' not in periods:
                continue
            pairs.append({**base, 'fact_id': periods['本期']['id'],
                          'fact_text': facts_to_text(periods['本期']),
                          'label': 0, 'negative_type': 'hard_negative_wrong_metric'})
            if len(pairs) >= max_pairs:
                break
        if len(pairs) >= max_pairs:
            break

    # 编号
    for i, p in enumerate(pairs, 1):
        p['claim_id'] = f'{out_group}-{i:04d}'
        p['split'] = 'train'
    return pairs, {'facts': len(facts), 'relations': len(all_relations),
                   'pairs': len(pairs), 'pages': pages}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--reports', required=True, help='年报 PDF 目录')
    ap.add_argument('--out', required=True, help='输出 JSONL')
    ap.add_argument('--per-report', type=int, default=60)
    args = ap.parse_args()

    src = Path(args.reports)
    pdfs = sorted(src.glob('*.pdf'))
    print(f'发现 {len(pdfs)} 份年报\n')

    all_pairs, stats = [], []
    for i, pdf in enumerate(pdfs, 1):
        gid = pdf.stem[:28]
        try:
            pairs, info = build_pairs_for_report(pdf, gid, args.per_report)
        except Exception as exc:
            print(f'  [{i}/{len(pdfs)}] {pdf.name[:40]} -> 失败 {type(exc).__name__}: {exc}')
            continue
        all_pairs.extend(pairs)
        stats.append({'file': pdf.name, **info})
        print(f"  [{i}/{len(pdfs)}] {pdf.name[:40]:42} 事实={info.get('facts','-'):>4} "
              f"对={info.get('pairs', 0):>4}")

    out = Path(args.out)
    with out.open('w', encoding='utf-8') as fh:
        for p in all_pairs:
            fh.write(json.dumps(p, ensure_ascii=False) + '\n')

    pos = sum(1 for p in all_pairs if p['label'] == 1)
    neg = len(all_pairs) - pos
    print(f'\n输出 {out}')
    print(f'  训练对总数: {len(all_pairs)}  (正例 {pos} / 负例 {neg})')
    if all_pairs:
        print(f'  涉及文档组: {len(set(p["group_id"] for p in all_pairs))}')
        print(f'  唯一 claim: {len(set(p["claim_id"] for p in all_pairs))}')
    (out.parent / 'build_stats.json').write_text(
        json.dumps(stats, ensure_ascii=False, indent=2), encoding='utf-8')


if __name__ == '__main__':
    main()
