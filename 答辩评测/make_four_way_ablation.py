"""Compare the four requested routing configurations on one frozen replay set.

Configurations:
  1. rule-only
  2. local-only (BGE prediction for every item)
  3. rule + local (zero candidates abstain; multi candidates use local)
  4. rule + local + API (production fallback replay)

The predictions are historical offline replays on the 180-decision programmatic
fixture.  No API call is made by this script and no frozen dataset is modified.
"""
from __future__ import annotations

import csv
import html
import json
import math
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parent))
from zhilian.engine import best_facts
from evaluate_model_routing import load_jsonl, load_predictions, pred, routing
from evaluate_predictions import evaluate

DATASET = ROOT / "eval_dataset.jsonl"


def rule_local(rows, rule, local):
    output = []
    for row in rows:
        rule_item = pred(row, rule)
        candidates = best_facts(row["claim_text"], row["facts"])
        deterministic = row["kind"] in {"growth", "rank", "ranking", "threshold", "chart"}
        if deterministic or len(candidates) == 1:
            chosen = rule_item
        elif len(candidates) > 1:
            chosen = pred(row, local)
        else:
            chosen = {"claim_id": row["claim_id"], "action": "abstain", "refs": []}
        output.append({**chosen, "candidate_count": len(candidates)})
    return output


def metrics(dataset, predictions):
    return evaluate(dataset, predictions, "all")


def chart(rows):
    W, H = 1240, 670; left, top, width, height = 105, 110, 1040, 405
    labels = {"rule-only": "纯规则", "local-only": "单独本地模型", "rule-local": "规则+本地模型", "rule-local-api": "规则+本地模型+API"}
    colors = {"top1_accuracy": "#0b6e99", "error_link_rate": "#d86555", "ambiguity_abstain_rate": "#0b8a72", "false_abstain_rate": "#f08c46"}
    metrics_to_plot = [("top1_accuracy", "Top-1"), ("error_link_rate", "错误关联"),
                       ("ambiguity_abstain_rate", "歧义拒答"), ("false_abstain_rate", "误拒答")]
    groups = ["rule-only", "local-only", "rule-local", "rule-local-api"]
    def esc(value): return html.escape(str(value))
    def y(value): return top + height - value * height
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">',
           '<rect width="100%" height="100%" fill="#fbfcfe"/>',
           '<style>text{font-family:"Microsoft YaHei",Arial,sans-serif}.title{font-size:26px;font-weight:700;fill:#172033}.muted{font-size:13px;fill:#536174}.axis{stroke:#8291a3}.grid{stroke:#dfe5ed}.label{font-size:14px;fill:#172033}</style>',
           '<text x="105" y="42" class="title">四档配置消融：规则与本地模型如何协同</text>',
           '<text x="105" y="69" class="muted">180 个程序化决策点 · 同一批离线预测重放 · 指标不等于人工行业真值</text>']
    for tick in range(6):
        value = tick / 5; yy = y(value)
        out += [f'<line x1="{left}" y1="{yy:.1f}" x2="{left+width}" y2="{yy:.1f}" class="grid"/>',
                f'<text x="{left-12}" y="{yy+5:.1f}" text-anchor="end" class="muted">{value:.0%}</text>']
    out.append(f'<line x1="{left}" y1="{top+height}" x2="{left+width}" y2="{top+height}" class="axis"/>')
    group_width = width / len(groups); bar_width = 42
    for gi, group in enumerate(groups):
        row = next(r for r in rows if r["system"] == group)
        center = left + group_width * (gi + .5)
        for mi, (key, _) in enumerate(metrics_to_plot):
            value = float(row[key]); xx = center + (mi - 1.5) * (bar_width + 5) - bar_width / 2; yy = y(value)
            out += [f'<rect x="{xx:.1f}" y="{yy:.1f}" width="{bar_width}" height="{top+height-yy:.1f}" fill="{colors[key]}"/>',
                    f'<text x="{xx+bar_width/2:.1f}" y="{max(top+12,yy-7):.1f}" text-anchor="middle" class="muted">{value:.0%}</text>']
        out.append(f'<text x="{center:.1f}" y="{top+height+30}" text-anchor="middle" class="label">{labels[group]}</text>')
    for i, (key, label) in enumerate(metrics_to_plot):
        xx = 155 + i * 240
        out += [f'<rect x="{xx}" y="{H-65}" width="16" height="16" fill="{colors[key]}"/>',
                f'<text x="{xx+24}" y="{H-51}" class="muted">{label}</text>']
    out += ['<text x="105" y="610" class="muted">解释：规则唯一候选直接通过；规则多候选交本地模型；零候选或低置信度才交 API；最终仍需人工确认。</text>', '</svg>']
    return '\n'.join(out)


def main():
    dataset = load_jsonl(DATASET)
    rule = load_predictions(ROOT / "predictions_rule.jsonl")
    local = load_predictions(ROOT / "predictions_local_reranker.jsonl")
    api = load_predictions(ROOT / "predictions_api.jsonl")
    routed, counts = routing(dataset, rule, local, api)
    configurations = {
        "rule-only": [pred(row, rule) for row in dataset],
        "local-only": [pred(row, local) for row in dataset],
        "rule-local": rule_local(dataset, rule, local),
        "rule-local-api": routed,
    }
    output = []
    for name, predictions in configurations.items():
        output.append({"system": name, **metrics(dataset, predictions)})
    (ROOT / "four_way_ablation_report.json").write_text(json.dumps({
        "dataset": str(DATASET), "configurations": output, "routing_counts": counts,
        "caveat": "历史预测离线重放；180条为程序化夹具，未调用API。"}, ensure_ascii=False, indent=2), encoding="utf-8")
    with (ROOT / "four_way_ablation_metrics.csv").open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(output[0])); writer.writeheader(); writer.writerows(output)
    (ROOT / "four_way_ablation_comparison.svg").write_text(chart(output), encoding="utf-8")
    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
