"""Evaluate rule, local BGE and Chinese BERT rerankers on rewrite-v2.

Outputs one auditable JSON/CSV bundle plus threshold data used by the chart
generator.  The dataset is independent evaluation data, not a training split.
"""
from __future__ import annotations

import csv
import json
import os
import sys
import time
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parent))

DATA = ROOT / "semantic_rewrite_eval_v2.jsonl"
FACTS_PATH = ROOT.parent / "长文Word测试" / "配套数据_初始.xlsx"


def load_rows():
    return [json.loads(line) for line in DATA.open(encoding="utf-8") if line.strip()]


def groups(rows, scores):
    out = defaultdict(list)
    for row, score in zip(rows, scores):
        out[row["claim_id"]].append((float(score), int(row["label"]), row["fact_id"], row))
    return out


def summarize(rows, scores, name, abstain_when_all_zero=False):
    grouped = groups(rows, scores)
    correct = 0
    accepted = 0
    for items in grouped.values():
        if abstain_when_all_zero and max(item[0] for item in items) <= 0:
            continue
        best = max(items, key=lambda item: item[0])
        accepted += 1
        correct += best[1]
    top1 = correct / max(1, len(grouped))
    return {"model": name, "claims": len(grouped), "rows": len(rows),
            "top1_accuracy": round(top1, 6),
            "error_association_rate": round(1 - top1, 6),
            "coverage": round(accepted / max(1, len(grouped)), 6),
            "abstain_rate": round(1 - accepted / max(1, len(grouped)), 6),
            "label_basis": "programmatic semantic rewrite; evaluation-only"}


def score_bge(rows):
    os.environ["ZHILIAN_LOCAL_RERANKER_ENABLED"] = "1"
    os.environ["ZHILIAN_LOCAL_RERANKER_PATH"] = str(ROOT.parent / "models" / "bge-reranker-v2-m3-onnx-int8")
    os.environ["ZHILIAN_LOCAL_RERANKER_DEVICE"] = "cpu"
    from zhilian.reranker import score_pairs
    from zhilian.office import read_facts

    facts = read_facts(FACTS_PATH, "facts")
    by_id = {fact["id"]: fact for fact in facts}
    scores = []
    for claim_id, items in _claim_rows(rows):
        claim = items[0]["claim_text"]
        result = score_pairs(claim, [by_id[item["fact_id"]] for item in items], batch_size=16)
        by_fact = {item["fact_id"]: item["raw_score"] for item in result}
        scores.extend(by_fact[row["fact_id"]] for row in items)
    return scores


def score_bert(rows, model_dir):
    import torch
    from transformers import AutoModelForSequenceClassification, AutoTokenizer

    torch.set_num_threads(min(8, torch.get_num_threads()))
    tokenizer = AutoTokenizer.from_pretrained(model_dir)
    model = AutoModelForSequenceClassification.from_pretrained(model_dir)
    model.eval()
    scores = []
    with torch.no_grad():
        for start in range(0, len(rows), 32):
            batch = rows[start:start + 32]
            encoded = tokenizer([r["claim_text"] for r in batch], [r["fact_text"] for r in batch],
                                padding=True, truncation=True, max_length=128, return_tensors="pt")
            logits = model(**encoded).logits
            if logits.shape[1] >= 2:
                scores.extend((logits[:, 1] - logits[:, 0]).tolist())
            else:
                scores.extend(logits.reshape(-1).tolist())
    return scores


def score_rule(rows):
    from zhilian import engine, office

    facts = office.read_facts(FACTS_PATH, "facts")
    by_id = {fact["id"]: fact for fact in facts}
    scores = []
    # A score of 1 is used for rule candidates and 0 otherwise.  Ties are
    # resolved by file order, which is exactly why this is a baseline only.
    for row in rows:
        picked = {fact["id"] for fact in engine.best_facts(row["claim_text"], facts)}
        scores.append(1.0 if row["fact_id"] in picked else 0.0)
    return scores


def _claim_rows(rows):
    current = None
    bucket = []
    for row in rows:
        if current is not None and row["claim_id"] != current:
            yield current, bucket
            bucket = []
        current = row["claim_id"]
        bucket.append(row)
    if current is not None:
        yield current, bucket


def threshold_rows(rows, scores, model):
    grouped = groups(rows, scores)
    values = []
    thresholds = sorted({round(min(scores) + i * (max(scores) - min(scores)) / 20, 6) for i in range(21)})
    for threshold in thresholds:
        accepted = correct = 0
        for items in grouped.values():
            top = max(items, key=lambda item: item[0])
            if top[0] >= threshold:
                accepted += 1
                correct += top[1]
        values.append({"model": model, "threshold": threshold, "accepted": accepted,
                       "claims": len(grouped), "coverage": round(accepted / max(1, len(grouped)), 6),
                       "precision": round(correct / max(1, accepted), 6),
                       "abstain_rate": round(1 - accepted / max(1, len(grouped)), 6)})
    return values


def main():
    rows = load_rows()
    model_scores = {
        "规则词面": score_rule(rows),
        "BGE ONNX": score_bge(rows),
        "中文 BERT v1": score_bert(rows, ROOT.parent / "models" / "zh_reranker_bert_ft"),
        "中文 BERT v2": score_bert(rows, ROOT.parent / "models" / "zh_reranker_bert_ft_v2"),
    }
    summaries = [summarize(rows, scores, name, abstain_when_all_zero=name == "规则词面")
                 for name, scores in model_scores.items()]
    curves = []
    curves.extend(threshold_rows(rows, model_scores["BGE ONNX"], "BGE ONNX"))
    curves.extend(threshold_rows(rows, model_scores["中文 BERT v2"], "中文 BERT v2"))
    categories = []
    by_category = defaultdict(list)
    for row in rows:
        by_category[row["category"]].append(row)
    for category, subset in by_category.items():
        indices = {id(row): i for i, row in enumerate(rows)}
        for name, scores in model_scores.items():
            selected = [scores[indices[id(row)]] for row in subset]
            categories.append({"category": category, **summarize(subset, selected, name,
                                                                   abstain_when_all_zero=name == "规则词面")})
    result = {"dataset": str(DATA), "stats": {"claims": len({r['claim_id'] for r in rows}),
              "rows": len(rows), "groups": len({r['group_id'] for r in rows}),
              "label_basis": "programmatic semantic rewrite; evaluation-only"},
              "models": summaries, "categories": categories, "thresholds": curves}
    (ROOT / "semantic_rewrite_eval_v2_results.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    with (ROOT / "semantic_rewrite_eval_v2_models.csv").open("w", newline="", encoding="utf-8-sig") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(summaries[0]))
        writer.writeheader(); writer.writerows(summaries)
    with (ROOT / "semantic_rewrite_eval_v2_thresholds.csv").open("w", newline="", encoding="utf-8-sig") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(curves[0]))
        writer.writeheader(); writer.writerows(curves)
    print(json.dumps(summaries, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
