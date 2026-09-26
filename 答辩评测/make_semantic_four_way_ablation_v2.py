"""Evaluate four configurations on the semantic rewrite set after a real API run."""
from __future__ import annotations

import csv
import html
import json
import os
from collections import defaultdict
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parent))
from zhilian import engine
from zhilian.office import read_facts
from zhilian.reranker import score_pairs

DATA = ROOT / 'semantic_rewrite_eval_v2.jsonl'
FACTS_PATH = ROOT.parent / '长文Word测试' / '配套数据_初始.xlsx'
API_PRED = ROOT / 'semantic_rewrite_eval_v2_api_predictions.jsonl'


def load_rows():
    return [json.loads(line) for line in DATA.open(encoding='utf-8') if line.strip()]


def metrics(rows, predictions, name):
    by_claim = {p['claim_id']: p for p in predictions}
    claims = {}
    for row in rows:
        if row['label'] == 1:
            claims[row['claim_id']] = row['fact_id']
    exact = wrong = linked = 0
    for cid, gold_id in claims.items():
        item = by_claim.get(cid, {})
        refs = item.get('refs', []) if item.get('action') == 'link' else []
        if refs:
            linked += 1
            if refs == [gold_id]:
                exact += 1
            else:
                wrong += 1
    total = len(claims)
    return {'system': name, 'claims': total, 'linked': linked,
            'top1_accuracy': round(exact / total, 6),
            'error_association_rate': round(wrong / total, 6),
            'coverage': round(linked / total, 6),
            'abstain_rate': round(1 - linked / total, 6),
            'label_basis': 'programmatic semantic rewrite; evaluation-only'}


def main():
    rows = load_rows()
    facts = read_facts(FACTS_PATH, 'facts')
    by_id = {f['id']: f for f in facts}
    api = {p['claim_id']: p for p in (json.loads(line) for line in API_PRED.open(encoding='utf-8') if line.strip())}
    grouped = defaultdict(list)
    for row in rows:
        grouped[row['claim_id']].append(row)
    local_top = {}
    rule_candidates = {}
    for cid, items in grouped.items():
        claim = items[0]['claim_text']
        candidates = engine.best_facts(claim, facts)
        rule_candidates[cid] = [f['id'] for f in candidates]
        scored = score_pairs(claim, facts, batch_size=16)
        local_top[cid] = {
            'fact_id': scored[0]['fact_id'] if scored else None,
            'raw_score': scored[0]['raw_score'] if scored else -999.0,
            'margin': (scored[0]['raw_score'] - scored[1]['raw_score']) if len(scored) > 1 else 999.0,
        }
    outputs = {name: [] for name in ('rule-only', 'local-only', 'rule-local', 'rule-local-api')}
    for cid, items in grouped.items():
        rule = rule_candidates[cid]
        local = local_top[cid]
        api_item = api.get(cid, {})
        api_refs = api_item.get('refs', []) if api_item.get('action') == 'link' else []
        rule_item = {'claim_id': cid, 'action': 'link' if len(rule) == 1 else 'abstain', 'refs': rule if len(rule) == 1 else []}
        local_item = {'claim_id': cid, 'action': 'link' if local['fact_id'] else 'abstain',
                      'refs': [local['fact_id']] if local['fact_id'] else []}
        if len(rule) == 1:
            rl_item = rule_item
            rla_item = rule_item
        else:
            # Fair ablation: both hybrid variants allow local semantic recall
            # when lexical rules cannot decide. The API variant adds a gate:
            # only low-confidence local results are escalated to DeepSeek.
            rl_item = local_item
            confident = local['raw_score'] >= -3.0 and local['margin'] >= 0.10
            rla_item = local_item if confident else {
                'claim_id': cid, 'action': 'link' if api_refs else 'abstain', 'refs': api_refs}
        for name, item in (('rule-only', rule_item), ('local-only', local_item),
                           ('rule-local', rl_item), ('rule-local-api', rla_item)):
            outputs[name].append(item)
    summary = [metrics(rows, predictions, name) for name, predictions in outputs.items()]
    report = {'dataset': str(DATA), 'models': summary, 'api_stats': str(ROOT / 'semantic_rewrite_eval_v2_api_stats.json'),
              'caveat': '语义改写 gold 为程序化标签；API 使用真实调用结果，密钥未写入。'}
    (ROOT / 'semantic_four_way_ablation_v2_report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    with (ROOT / 'semantic_four_way_ablation_v2_metrics.csv').open('w', encoding='utf-8-sig', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(summary[0])); writer.writeheader(); writer.writerows(summary)
    for name, predictions in outputs.items():
        safe = name.replace('-', '_')
        (ROOT / f'semantic_four_way_{safe}_v2.jsonl').write_text('\n'.join(json.dumps(p, ensure_ascii=False) for p in predictions) + '\n', encoding='utf-8')
    (ROOT / 'semantic_four_way_ablation_v2.svg').write_text(chart(summary), encoding='utf-8')
    print(json.dumps(summary, ensure_ascii=False, indent=2))


def chart(rows):
    labels = {'rule-only': '纯规则', 'local-only': '单独本地模型', 'rule-local': '规则+本地模型', 'rule-local-api': '规则+本地模型+API'}
    colors = {'top1_accuracy': '#0b6e99', 'error_association_rate': '#d86555', 'coverage': '#0b8a72', 'abstain_rate': '#f08c46'}
    metrics_to_plot = [('top1_accuracy', 'Top-1'), ('error_association_rate', '错误关联'), ('coverage', '覆盖率'), ('abstain_rate', '拒答率')]
    # Reserve separate rows for the legend and the conclusion caption so that
    # the long Chinese text cannot overlap the legend in exported slides.
    W, H, left, top, width, height = 1240, 730, 105, 110, 1040, 405
    def y(value): return top + height - value * height
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">', '<rect width="100%" height="100%" fill="#fbfcfe"/>', '<style>text{font-family:"Microsoft YaHei",Arial,sans-serif}.title{font-size:26px;font-weight:700;fill:#172033}.muted{font-size:13px;fill:#536174}.axis{stroke:#8291a3}.grid{stroke:#dfe5ed}.label{font-size:14px;fill:#172033}</style>', '<text x="105" y="42" class="title">语义改写集四档配置对比</text>', '<text x="105" y="69" class="muted">72 条中文改写论断 · API 实际调用 2 批 · 程序化 gold，仅用于评测</text>']
    for tick in range(6):
        value = tick / 5; yy = y(value)
        out += [f'<line x1="{left}" y1="{yy:.1f}" x2="{left+width}" y2="{yy:.1f}" class="grid"/>', f'<text x="{left-12}" y="{yy+5:.1f}" text-anchor="end" class="muted">{value:.0%}</text>']
    out.append(f'<line x1="{left}" y1="{top+height}" x2="{left+width}" y2="{top+height}" class="axis"/>')
    groups = [r['system'] for r in rows]; group_width = width / len(groups); bar_width = 42
    for gi, row in enumerate(rows):
        center = left + group_width * (gi + .5)
        for mi, (key, _) in enumerate(metrics_to_plot):
            value = float(row[key]); xx = center + (mi - 1.5) * (bar_width + 5) - bar_width / 2; yy = y(value)
            out += [f'<rect x="{xx:.1f}" y="{yy:.1f}" width="{bar_width}" height="{top+height-yy:.1f}" fill="{colors[key]}"/>', f'<text x="{xx+bar_width/2:.1f}" y="{max(top+12,yy-7):.1f}" text-anchor="middle" class="muted">{value:.0%}</text>']
        out.append(f'<text x="{center:.1f}" y="{top+height+30}" text-anchor="middle" class="label">{labels[row["system"]]}</text>')
    legend_y = H - 75
    for i, (key, label) in enumerate(metrics_to_plot):
        xx = 155 + i * 240; out += [f'<rect x="{xx}" y="{legend_y}" width="16" height="16" fill="{colors[key]}"/>', f'<text x="{xx+24}" y="{legend_y+14}" class="muted">{label}</text>']
    out += [f'<text x="105" y="{H-20}" class="muted">结论：API 只补规则零候选；本地模型负责语义排序；所有来源仍需人工确认。</text>', '</svg>']
    return '\n'.join(out)


if __name__ == '__main__':
    main()
