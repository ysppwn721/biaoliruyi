"""Fast batched evaluation for the PDF programmatic holdout.

The regular product path scores one narrow candidate list at a time.  This
utility batches the complete offline benchmark so a deadline run does not
spend minutes creating one ONNX session call per claim.
"""
from __future__ import annotations

import argparse
import json
import math
from collections import defaultdict
from pathlib import Path


def load_rows(path: Path):
    return [json.loads(line) for line in path.open(encoding="utf-8") if line.strip()]


def summarize(rows, scores, model: str):
    groups = defaultdict(list)
    for row, score in zip(rows, scores):
        groups[row["claim_id"]].append((float(score), int(row["label"])))
    correct = sum(1 for items in groups.values() if max(items, key=lambda x: x[0])[1] == 1)
    result = {
        "model": model,
        "programmatic": True,
        "file": str(Path(args.dataset)),
        "groups": len({r["group_id"] for r in rows}),
        "claims": len(groups),
        "rows": len(rows),
        "top1_accuracy": round(correct / len(groups), 6) if groups else 0.0,
        "error_association_rate": round(1 - correct / len(groups), 6) if groups else 0.0,
    }
    out = Path(args.output) if args.output else Path(args.dataset).with_name(Path(args.dataset).stem + f"_{model}_metrics.json")
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False))


def score_bge(rows, batch_size: int):
    import numpy as np
    import onnxruntime as ort
    from tokenizers import Tokenizer

    model_dir = Path("models/bge-reranker-v2-m3-onnx-int8")
    model = model_dir / "onnx/model_int8.onnx"
    tokenizer = Tokenizer.from_file(str(model_dir / "tokenizer.json"))
    tokenizer.enable_truncation(max_length=512)
    tokenizer.enable_padding(pad_id=0, pad_token="<pad>")
    session = ort.InferenceSession(str(model), providers=["CPUExecutionProvider"])
    names = {item.name for item in session.get_inputs()}
    pairs = [(r["claim_text"], r["fact_text"]) for r in rows]
    scores = []
    for start in range(0, len(pairs), batch_size):
        enc = tokenizer.encode_batch(pairs[start:start + batch_size])
        arrays = {
            "input_ids": np.asarray([e.ids for e in enc], dtype=np.int64),
            "attention_mask": np.asarray([e.attention_mask for e in enc], dtype=np.int64),
        }
        if "token_type_ids" in names:
            arrays["token_type_ids"] = np.asarray([e.type_ids for e in enc], dtype=np.int64)
        output = session.run(None, {k: v for k, v in arrays.items() if k in names})[0]
        scores.extend(output.reshape(-1).tolist())
    return scores


def score_bert(rows, batch_size: int, model_dir: Path):
    import torch
    from transformers import AutoModelForSequenceClassification, AutoTokenizer

    torch.set_num_threads(min(8, torch.get_num_threads()))
    tokenizer = AutoTokenizer.from_pretrained(model_dir)
    model = AutoModelForSequenceClassification.from_pretrained(model_dir)
    model.eval()
    scores = []
    with torch.no_grad():
        for start in range(0, len(rows), batch_size):
            batch = rows[start:start + batch_size]
            encoded = tokenizer([r["claim_text"] for r in batch], [r["fact_text"] for r in batch],
                                padding=True, truncation=True, max_length=128, return_tensors="pt")
            logits = model(**encoded).logits
            scores.extend((logits[:, 1] - logits[:, 0]).tolist())
    return scores


parser = argparse.ArgumentParser()
parser.add_argument("--dataset", default="答辩评测/external_programmatic_holdout_all.jsonl")
parser.add_argument("--model", choices=("bge", "bert"), required=True)
parser.add_argument("--batch-size", type=int, default=64)
parser.add_argument("--output")
args = parser.parse_args()
rows = load_rows(Path(args.dataset))
if args.model == "bge":
    values = score_bge(rows, args.batch_size)
    summarize(rows, values, "bge-reranker-v2-m3-onnx-int8")
else:
    values = score_bert(rows, args.batch_size, Path("models/zh_reranker_bert_ft_v2"))
    summarize(rows, values, "zh_reranker_bert_ft_v2")
