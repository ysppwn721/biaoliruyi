"""Fast, fully local Chinese reranker baseline for deadline experiments."""
from __future__ import annotations

import csv
import json
from collections import defaultdict
from pathlib import Path

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import SGDClassifier
from sklearn.metrics import log_loss


ROOT = Path(__file__).resolve().parent
DATA = ROOT / "cn_finetune"
OUT = ROOT / "char_reranker_results"


def load(path: Path):
    return [json.loads(line) for line in path.open(encoding="utf-8") if line.strip()]


def text(row):
    return row["claim_text"] + " [SEP] " + row["fact_text"]


def metrics(rows, scores):
    grouped = defaultdict(list)
    for row, score in zip(rows, scores):
        grouped[row["claim_id"]].append((float(score), int(row["label"])))
    top1 = sum(max(items)[1] == 1 for items in grouped.values()) / max(1, len(grouped))
    return {"claims": len(grouped), "top1_accuracy": round(top1, 6),
            "error_association_rate": round(1 - top1, 6)}


def main():
    train, dev, test = (load(DATA / name) for name in ("train.jsonl", "dev.jsonl", "final_test.jsonl"))
    vectorizer = TfidfVectorizer(analyzer="char", ngram_range=(2, 5), min_df=1,
                                 max_features=60000, sublinear_tf=True)
    X_train = vectorizer.fit_transform([text(r) for r in train])
    X_dev = vectorizer.transform([text(r) for r in dev])
    X_test = vectorizer.transform([text(r) for r in test])
    y_train = np.array([int(r["label"]) for r in train])
    y_dev = np.array([int(r["label"]) for r in dev])
    y_test = np.array([int(r["label"]) for r in test])
    model = SGDClassifier(loss="log_loss", class_weight=None, random_state=42,
                          alpha=2e-5, penalty="l2", learning_rate="optimal")
    history = []
    for epoch in range(1, 11):
        order = np.random.default_rng(100 + epoch).permutation(len(train))
        ordered_y = y_train[order]
        # Pair data is intentionally hard-negative heavy (roughly 1:4).
        # Weight positives so the classifier does not learn the majority class.
        sample_weight = np.where(ordered_y == 1, 4.0, 1.0)
        model.partial_fit(X_train[order], ordered_y, classes=np.array([0, 1]),
                          sample_weight=sample_weight)
        dev_prob = model.predict_proba(X_dev)[:, 1]
        test_prob = model.predict_proba(X_test)[:, 1]
        row = {"epoch": epoch, "train_loss": float(log_loss(y_train, model.predict_proba(X_train))),
               "dev_loss": float(log_loss(y_dev, dev_prob)), "test_loss": float(log_loss(y_test, test_prob)),
               "dev": metrics(dev, dev_prob), "test": metrics(test, test_prob)}
        history.append(row)
        print(json.dumps(row, ensure_ascii=False))
    OUT.mkdir(parents=True, exist_ok=True)
    import joblib
    joblib.dump({"vectorizer": vectorizer, "model": model}, OUT / "char_reranker.joblib")
    (OUT / "metrics.json").write_text(json.dumps({"history": history}, ensure_ascii=False, indent=2), encoding="utf-8")
    with (OUT / "metrics.csv").open("w", newline="", encoding="utf-8-sig") as stream:
        writer = csv.writer(stream)
        writer.writerow(["epoch", "train_loss", "dev_loss", "test_loss", "dev_top1", "test_top1", "dev_error", "test_error"])
        for row in history:
            writer.writerow([row["epoch"], row["train_loss"], row["dev_loss"], row["test_loss"],
                             row["dev"]["top1_accuracy"], row["test"]["top1_accuracy"],
                             row["dev"]["error_association_rate"], row["test"]["error_association_rate"]])


if __name__ == "__main__":
    main()
