"""Render dependency-free SVG charts for the semantic model evaluation."""
from __future__ import annotations

import html
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
RESULT = json.loads((ROOT / "semantic_rewrite_eval_v2_results.json").read_text(encoding="utf-8"))
COLORS = {"规则词面": "#7a8796", "BGE ONNX": "#0b6e99", "中文 BERT v1": "#c85a54", "中文 BERT v2": "#f08c46"}


def esc(value):
    return html.escape(str(value))


def svg_start(width, height, title, subtitle):
    return [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
            '<rect width="100%" height="100%" fill="#fbfcfe"/>',
            '<style>text{font-family:"Microsoft YaHei","Noto Sans CJK SC",Arial,sans-serif}.grid{stroke:#d8e0e8;stroke-width:1}.axis{stroke:#8291a3;stroke-width:1.2}.muted{fill:#536174}.title{fill:#172033;font-size:24px;font-weight:700}.small{font-size:12px}.label{fill:#26364a;font-size:13px}</style>',
            f'<text x="50" y="38" class="title">{esc(title)}</text>',
            f'<text x="50" y="63" class="muted small">{esc(subtitle)}</text>']


def save(lines, name):
    lines.append('</svg>')
    (ROOT / name).write_text('\n'.join(lines), encoding='utf-8')


def y_grid(lines, left, top, width, height):
    for value in range(0, 101, 20):
        y = top + height - value / 100 * height
        lines.append(f'<line x1="{left}" y1="{y:.1f}" x2="{left+width}" y2="{y:.1f}" class="grid"/>')
        lines.append(f'<text x="{left-10}" y="{y+4:.1f}" text-anchor="end" class="muted small">{value}%</text>')


def comparison():
    models = [x['model'] for x in RESULT['models']]
    vals = [x['top1_accuracy'] * 100 for x in RESULT['models']]
    errors = [x['error_association_rate'] * 100 for x in RESULT['models']]
    W, H = 1200, 620
    lines = svg_start(W, H, '知链语义来源关联：独立改写集多模型对比', '72 条中文改写论断 · 432 个候选对 · 6 类场景 · 程序化 gold · 仅作评测，不进入训练集')
    panels = [(70, 'Top-1 正确率', vals), (650, '错误关联率', errors)]
    for left, title, values in panels:
        top, width, height = 115, 470, 365
        lines.append(f'<text x="{left}" y="96" class="label" font-weight="700">{title}</text>')
        y_grid(lines, left, top, width, height)
        lines.append(f'<line x1="{left}" y1="{top+height}" x2="{left+width}" y2="{top+height}" class="axis"/>')
        step = width / len(models)
        for i, (model, value) in enumerate(zip(models, values)):
            x = left + step * i + step * .19; bar_w = step * .62
            bar_h = value / 100 * height; y = top + height - bar_h
            lines.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{bar_w:.1f}" height="{bar_h:.1f}" rx="4" fill="{COLORS[model]}"/>')
            lines.append(f'<text x="{x+bar_w/2:.1f}" y="{max(top-4,y-8):.1f}" text-anchor="middle" class="label">{value:.1f}%</text>')
            lines.append(f'<text x="{x+bar_w/2:.1f}" y="{top+height+24}" text-anchor="middle" class="muted small" transform="rotate(18 {x+bar_w/2:.1f} {top+height+24})">{esc(model)}</text>')
    lines.append('<text x="650" y="565" class="muted small">BGE/BERT 覆盖率 100%；规则无候选时保留为人工待确认</text>')
    save(lines, '语义模型对比_v2.svg')


def threshold():
    W, H = 980, 600; left, top, width, height = 95, 115, 790, 370
    lines = svg_start(W, H, '置信度阈值曲线：覆盖率与准确率的权衡', '阈值扫描用于分流校准；低置信候选应转人工或 API，不能直接写回文件')
    y_grid(lines, left, top, width, height)
    for value in range(0, 101, 20):
        x = left + value / 100 * width
        lines.append(f'<line x1="{x:.1f}" y1="{top}" x2="{x:.1f}" y2="{top+height}" class="grid"/>')
        lines.append(f'<text x="{x:.1f}" y="{top+height+23}" text-anchor="middle" class="muted small">{value}%</text>')
    lines.append(f'<line x1="{left}" y1="{top+height}" x2="{left+width}" y2="{top+height}" class="axis"/>')
    lines.append(f'<text x="{left+width/2}" y="{top+height+52}" text-anchor="middle" class="label">接受覆盖率</text>')
    lines.append(f'<text x="25" y="{top+height/2}" text-anchor="middle" class="label" transform="rotate(-90 25 {top+height/2})">接受样本 Top-1</text>')
    for model in ('BGE ONNX', '中文 BERT v2'):
        rows = sorted((x for x in RESULT['thresholds'] if x['model'] == model), key=lambda x: x['coverage'])
        points = ' '.join(f'{left+r["coverage"]*width:.1f},{top+height-r["precision"]*height:.1f}' for r in rows)
        color = COLORS[model]
        lines.append(f'<polyline points="{points}" fill="none" stroke="{color}" stroke-width="3"/>')
        for row in rows:
            x = left + row['coverage'] * width; y = top + height - row['precision'] * height
            lines.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="4" fill="{color}"/>')
    lines.append(f'<line x1="650" y1="70" x2="680" y2="70" stroke="{COLORS["BGE ONNX"]}" stroke-width="3"/><text x="688" y="74" class="label">BGE ONNX</text>')
    lines.append(f'<line x1="790" y1="70" x2="820" y2="70" stroke="{COLORS["中文 BERT v2"]}" stroke-width="3"/><text x="828" y="74" class="label">中文 BERT v2</text>')
    save(lines, '语义模型阈值曲线_v2.svg')


def heatmap():
    categories = list(dict.fromkeys(x['category'] for x in RESULT['categories']))
    labels = ['本期收入', '上期收入', 'A产品销量', 'B产品销量', '支出', '预算']
    models = [x['model'] for x in RESULT['models']]
    matrix = [[next(x['top1_accuracy'] for x in RESULT['categories'] if x['category'] == c and x['model'] == m) * 100 for m in models] for c in categories]
    W, H = 1050, 570; left, top, cell_w, cell_h = 250, 120, 175, 52
    lines = svg_start(W, H, '不同语义改写类别的模型 Top-1', '每类 12 条改写；观察同义表达、期间改写和业务词替换下的稳定性')
    for j, model in enumerate(models):
        x = left + j*cell_w + cell_w/2
        lines.append(f'<text x="{x}" y="{top-18}" text-anchor="middle" class="label" transform="rotate(15 {x} {top-18})">{esc(model)}</text>')
    for i, (label, row) in enumerate(zip(labels, matrix)):
        y = top + i * cell_h
        lines.append(f'<text x="{left-18}" y="{y+cell_h/2+5}" text-anchor="end" class="label">{label}</text>')
        for j, value in enumerate(row):
            x = left + j * cell_w; shade = int(240 - value * 1.55)
            fill = f'rgb({max(20, shade-55)},{max(80, shade-20)},{min(245, shade+5)})'
            lines.append(f'<rect x="{x+2}" y="{y+2}" width="{cell_w-4}" height="{cell_h-4}" rx="5" fill="{fill}"/>')
            lines.append(f'<text x="{x+cell_w/2}" y="{y+cell_h/2+5}" text-anchor="middle" class="label" font-weight="700">{value:.0f}%</text>')
    save(lines, '语义模型类别热力图_v2.svg')


if __name__ == '__main__':
    comparison(); threshold(); heatmap(); print('wrote semantic evaluation SVG charts')
