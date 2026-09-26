"""Evaluate the production routing policy without making model/API calls.

The script replays already captured predictions on the frozen evaluation set.
It keeps compound claims on the deterministic path, sends multi-candidate
single-source claims to the local reranker, and uses the API prediction only
for local abstentions or zero-candidate claims.  The output is suitable for a
defense slide and records the request count implied by 40-claim batching.
"""
from __future__ import annotations

import csv
import json
import math
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from zhilian.engine import best_facts
from evaluate_predictions import evaluate

ROOT = Path(__file__).resolve().parent


def load_jsonl(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as stream:
        return [json.loads(line) for line in stream if line.strip()]


def load_predictions(path: Path) -> dict[str, dict]:
    return {row["claim_id"]: row for row in load_jsonl(path)}


def pred(row: dict, source: dict[str, dict]) -> dict:
    item = source.get(row["claim_id"], {})
    refs = item.get("refs", []) if isinstance(item.get("refs", []), list) else []
    action = item.get("action", "abstain")
    return {"claim_id": row["claim_id"], "action": action,
            "refs": list(dict.fromkeys(refs)) if action == "link" else []}


def routing(rows: list[dict], rule: dict[str, dict], local: dict[str, dict],
            api: dict[str, dict]) -> tuple[list[dict], dict]:
    output = []
    counts = {"unique_rule": 0, "multi_local": 0, "multi_api_fallback": 0,
              "zero_api": 0, "manual_abstain": 0}
    for row in rows:
        rule_item = pred(row, rule)
        candidates = best_facts(row["claim_text"], row["facts"])
        # Typed compound claims already have a deterministic source set. They
        # must never be split into independent pairwise reranker decisions.
        deterministic = row["kind"] in {"growth", "rank", "ranking", "threshold", "chart"}
        if deterministic or len(candidates) == 1:
            chosen, source = rule_item, "rule"
            counts["unique_rule"] += 1
        elif len(candidates) > 1:
            local_item = pred(row, local)
            if local_item["action"] == "link":
                chosen, source = local_item, "local-reranker"
                counts["multi_local"] += 1
            else:
                api_item = pred(row, api)
                # Remote suggestions are displayed as an additional option;
                # the state machine still keeps a multi-candidate claim behind
                # the human decision gate. Do not score a suggestion as an
                # automatic association.
                chosen = {"claim_id": row["claim_id"], "action": "abstain", "refs": [],
                          "suggested_refs": api_item["refs"]}
                source = "api-fallback-human-review"
                counts["multi_api_fallback"] += 1
        else:
            chosen, source = pred(row, api), "api-zero-candidate"
            counts["zero_api"] += 1
        if chosen["action"] != "link":
            counts["manual_abstain"] += 1
        output.append({**chosen, "source": source, "candidate_count": len(candidates)})
    fallback = counts["multi_api_fallback"] + counts["zero_api"]
    counts.update({"rows": len(rows), "api_fallback_claims": fallback,
                   "api_batches_at_40_theoretical_lower_bound": math.ceil(fallback / 40) if fallback else 0,
                   "local_pairs": sum(row["candidate_count"] for row in output
                                      if row["source"] == "local-reranker")})
    return output, counts


def metrics(dataset: list[dict], predictions: list[dict], split: str) -> dict:
    return evaluate(dataset, predictions, split)


def chart(rows: list[dict]) -> str:
    """Small dependency-free SVG for the PPT handoff."""
    all_rows = [row for row in rows if row["split"] == "all"]
    width, height = 1120, 650
    left, right, top, bottom = 110, 40, 92, 115
    x0, x1, y0, y1 = left, width - right, height - bottom, top
    groups = ["rule-only", "local-reranker-all", "api-all", "routed-rule-local-api"]
    labels = {"rule-only": "纯规则", "local-reranker-all": "全量 reranker",
              "api-all": "全量 API", "routed-rule-local-api": "分层路由"}
    colors = {"top1_accuracy": "#0b6e99", "error_link_rate": "#d86555",
              "ambiguity_abstain_rate": "#0b8a72"}
    metrics_to_plot = [("top1_accuracy", "Top-1 正确率"),
                       ("error_link_rate", "错误关联率"),
                       ("ambiguity_abstain_rate", "歧义拒答率")]
    group_width = (x1 - x0) / len(groups)
    bar_width = 52
    def y(value: float) -> float:
        return y0 - value * (y0 - y1)
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
             '<title>规则、模型与分层路由对照</title>',
             '<desc>夹具评测：分层路由保留规则确定性，模型只处理困难样本并保留人工确认闸门。</desc>',
             '<rect width="100%" height="100%" fill="#fbfcfe"/>',
             '<text x="110" y="42" font-family="Microsoft YaHei, sans-serif" font-size="26" font-weight="600" fill="#172033">模型调用范围决定系统可靠性</text>',
             '<text x="110" y="68" font-family="Microsoft YaHei, sans-serif" font-size="14" fill="#536174">180 个程序化夹具决策点 · 结果用于验证路由策略，不等同于人工行业真值</text>']
    for tick in range(6):
        value = tick / 5
        yy = y(value)
        parts += [f'<line x1="{x0}" y1="{yy:.1f}" x2="{x1}" y2="{yy:.1f}" stroke="#dfe5ed"/>',
                  f'<text x="{x0-12}" y="{yy+5:.1f}" text-anchor="end" font-family="Arial" font-size="13" fill="#536174">{value:.0%}</text>']
    for gi, group in enumerate(groups):
        center = x0 + group_width * (gi + .5)
        row = next(item for item in all_rows if item["system"] == group)
        for mi, (key, _) in enumerate(metrics_to_plot):
            value = float(row[key])
            xx = center + (mi - 1) * (bar_width + 8) - bar_width / 2
            yy = y(value)
            parts += [f'<rect x="{xx:.1f}" y="{yy:.1f}" width="{bar_width}" height="{y0-yy:.1f}" fill="{colors[key]}"/>',
                      f'<text x="{xx+bar_width/2:.1f}" y="{yy-8:.1f}" text-anchor="middle" font-family="Arial" font-size="12" fill="#172033">{value:.0%}</text>']
        parts.append(f'<text x="{center:.1f}" y="{y0+28}" text-anchor="middle" font-family="Microsoft YaHei, sans-serif" font-size="14" fill="#172033">{labels[group]}</text>')
    for i, (key, label) in enumerate(metrics_to_plot):
        xx = 160 + i * 260
        parts += [f'<rect x="{xx}" y="{height-52}" width="16" height="16" fill="{colors[key]}"/>',
                  f'<text x="{xx+24}" y="{height-38}" font-family="Microsoft YaHei, sans-serif" font-size="14" fill="#536174">{label}</text>']
    parts += [f'<text x="25" y="{(y0+y1)/2:.1f}" transform="rotate(-90 25 {(y0+y1)/2:.1f})" text-anchor="middle" font-family="Microsoft YaHei, sans-serif" font-size="15" fill="#172033">比例</text>',
              '<text x="110" y="590" font-family="Microsoft YaHei, sans-serif" font-size="14" fill="#536174">结论：唯一候选走规则；多候选先走本地排序；低置信和零候选才升级 API，最终仍由人工确认。</text>',
              '</svg>']
    return "\n".join(parts)


def main() -> None:
    dataset = load_jsonl(ROOT / "eval_dataset.jsonl")
    rule = load_predictions(ROOT / "predictions_rule.jsonl")
    local = load_predictions(ROOT / "predictions_local_reranker.jsonl")
    api = load_predictions(ROOT / "predictions_api.jsonl")
    routed, counts = routing(dataset, rule, local, api)
    out_jsonl = ROOT / "predictions_routed.jsonl"
    with out_jsonl.open("w", encoding="utf-8") as stream:
        for row in routed:
            stream.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
    rows = [{"system": "routed-rule-local-api", **metrics(dataset, routed, split)}
            for split in ("dev", "test", "all")]
    comparison = []
    for name, source in (("rule-only", rule), ("local-reranker-all", local),
                         ("api-all", api)):
        predictions = [{**pred(row, source)} for row in dataset]
        comparison.extend({"system": name, **metrics(dataset, predictions, split)}
                          for split in ("dev", "test", "all"))
    comparison.extend(rows)
    out_csv = ROOT / "model_routing_metrics.csv"
    with out_csv.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(comparison)
    report = {"policy": "rule unique/compound -> local multi -> API fallback zero/local abstain",
              "counts": counts, "metrics": comparison,
              "caveat": "历史预测离线重放，不是新路由实测。标签只用于打分。批次数是忽略文档组/事实表隔离的理论下限，不是实际调用数或耗时。"}
    (ROOT / "model_routing_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    (ROOT / "model_routing_comparison.svg").write_text(chart(comparison), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
