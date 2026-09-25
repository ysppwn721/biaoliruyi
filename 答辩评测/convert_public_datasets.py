"""Convert licensed public table QA data into metadata-only reranker pairs."""
from __future__ import annotations

import json
import random
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PUBLIC = ROOT / "public_data"
OUT = ROOT / "public_reranker_pairs.jsonl"
SEED = 20260925


def fact_text(fact: dict) -> str:
    return "；".join(f"{key}={fact.get(key, '')}" for key in
                     ("subject", "metric", "period", "unit", "scope"))


def finqa_rows(split: str) -> list[dict]:
    path = PUBLIC / "FinQA" / "dataset" / f"{split}.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    output = []
    for item in data:
        table_obj = item.get("table") or {}
        table = table_obj.get("table", table_obj) if isinstance(table_obj, dict) else table_obj
        if len(table) < 2:
            continue
        headers = table[0]
        facts = []
        for row_index, row in enumerate(table[1:], 1):
            if not row:
                continue
            subject = row[0]
            for col_index, value in enumerate(row[1:], 1):
                period = headers[col_index] if col_index < len(headers) else f"column_{col_index}"
                facts.append({"id": f"r{row_index}c{col_index}", "subject": subject,
                              "metric": subject, "period": period, "unit": "", "scope": "FinQA"})
        row_ids = {index: [fact["id"] for fact in facts if fact["id"].startswith(f"r{index}c")]
                   for index in range(1, len(table))}
        positives = [fact_id for index in (item.get("qa", {}).get("ann_table_rows") or [])
                     for fact_id in row_ids.get(index, [])]
        if not positives:
            continue
        question = item.get("qa", {}).get("question", "")
        output.append({"source": "FinQA", "source_id": item.get("id", item.get("filename", "")),
                       "source_split": split, "group_id": f"FinQA:{item.get('id', item.get('filename', ''))}",
                       "claim_text": question, "facts": facts, "positive_refs": positives})
    return output


def tatqa_rows(split: str) -> list[dict]:
    path = PUBLIC / "TAT-QA" / "dataset_raw" / f"tatqa_dataset_{split}.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    output = []
    for item in data:
        table_obj = item.get("table") or {}
        table = table_obj.get("table", table_obj) if isinstance(table_obj, dict) else table_obj
        if len(table) < 2:
            continue
        headers = table[0]
        facts = []
        for row_index, row in enumerate(table[1:], 1):
            if not row:
                continue
            subject = row[0]
            for col_index, value in enumerate(row[1:], 1):
                period = headers[col_index] if col_index < len(headers) else f"column_{col_index}"
                facts.append({"id": f"r{row_index}c{col_index}", "subject": subject,
                              "metric": subject, "period": period, "unit": item.get("questions", [{}])[0].get("scale", ""),
                              "scope": "TAT-QA"})
        for question in item.get("questions", []):
            if question.get("answer_from") not in {"table", "table-text"}:
                continue
            answer = question.get("answer")
            answers = answer if isinstance(answer, list) else [answer]
            positives = []
            for fact in facts:
                # Values are used only to locate the public annotation. They
                # are omitted from the emitted fact_text below.
                if any(str(value) in fact["id"] for value in []):
                    positives.append(fact["id"])
            # TAT-QA has no universal cell annotation in the raw file. Use
            # deterministic row/value matching only when the answer is a cell
            # value; otherwise skip rather than inventing labels.
            for row_index, row in enumerate(table[1:], 1):
                for col_index, value in enumerate(row[1:], 1):
                    if any(str(value).strip() == str(candidate).strip() for candidate in answers):
                        positives.append(f"r{row_index}c{col_index}")
            positives = list(dict.fromkeys(positives))
            if not positives:
                continue
            output.append({"source": "TAT-QA", "source_id": item.get("table", {}).get("uid", ""),
                           "source_split": split, "group_id": f"TAT-QA:{item.get('table', {}).get('uid', '')}",
                           "claim_text": question.get("question", ""), "facts": facts,
                           "positive_refs": positives})
    return output


def pairs(records: list[dict]) -> list[dict]:
    output = []
    seen = set()
    for record in records:
        positives = set(record["positive_refs"])
        by_id = {fact["id"]: fact for fact in record["facts"]}
        for fact_id in positives:
            if fact_id not in by_id:
                continue
            item = {"source": record["source"], "source_id": record["source_id"],
                           "group_id": record["group_id"], "split": record["source_split"],
                           "claim_text": record["claim_text"], "fact_id": fact_id,
                           "fact_text": fact_text(by_id[fact_id]), "label": 1}
            key = (item["source"], item["source_id"], item["claim_text"], item["fact_id"], item["label"])
            if key not in seen:
                output.append(item)
                seen.add(key)
            for negative in record["facts"]:
                if negative["id"] in positives:
                    continue
                if negative.get("metric") == by_id[fact_id].get("metric") or negative.get("period") == by_id[fact_id].get("period"):
                    item = {"source": record["source"], "source_id": record["source_id"],
                                   "group_id": record["group_id"], "split": record["source_split"],
                                   "claim_text": record["claim_text"], "fact_id": negative["id"],
                                   "fact_text": fact_text(negative), "label": 0,
                                   "negative_type": "hard_negative"}
                    key = (item["source"], item["source_id"], item["claim_text"], item["fact_id"], item["label"])
                    if key not in seen:
                        output.append(item)
                        seen.add(key)
    return output


def main() -> None:
    random.seed(SEED)
    records = finqa_rows("train") + finqa_rows("dev") + tatqa_rows("train") + tatqa_rows("dev")
    result = pairs(records)
    random.shuffle(result)
    with OUT.open("w", encoding="utf-8") as stream:
        for row in result:
            stream.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
    print(json.dumps({"records": len(records), "pairs": len(result),
                      "positive": sum(row["label"] == 1 for row in result),
                      "negative": sum(row["label"] == 0 for row in result),
                      "sources": {source: sum(row["source"] == source for row in result)
                                  for source in ("FinQA", "TAT-QA")},
                      "output": str(OUT)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
